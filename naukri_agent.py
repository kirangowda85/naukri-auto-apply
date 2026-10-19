import asyncio
import sys
import os
import re
import json
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import ConfigManager
from db_logger import DatabaseLogger
from ai_solver import QuestionSolver

LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "agent_run.log")


class NaukriAutoApplyAgent:
    """
    Automated Naukri.com Job Application Agent - Perfected Production Version.
    - Intelligent Job Card Matcher with multi-keyword scoring & strict experience checks.
    - Fast Card-Level Pre-Filtering (skips external ATS redirects directly from search results).
    - Dual Apply Pipeline: Instant 1-Click Apply detection + Multi-step Screening Chatbot Drawer.
    - Self-learning Q&A memory + Gemini AI solver for recruiter questions.
    - Zero duplicate applications via persistent SQLite tracking.
    """

    def __init__(self, config: Dict[str, Any], logger_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.db = DatabaseLogger()
        self.solver = QuestionSolver(config)

        self._log_buffer: List[str] = []
        self._ext_log_cb = logger_callback

        self.stopped = False
        self.applied_count = 0
        self.skipped_count = 0
        self.failed_count = 0

    def log(self, message: str):
        """Thread-safe and file-backed logging to ensure live logs in Streamlit UI."""
        self._log_buffer.append(message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        try:
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass
        try:
            print(f"[NaukriAgent] {message}", flush=True)
        except UnicodeEncodeError:
            safe = message.encode("ascii", "replace").decode("ascii")
            print(f"[NaukriAgent] {safe}", flush=True)
        if self._ext_log_cb:
            try:
                self._ext_log_cb(message)
            except Exception:
                pass

    def stop(self):
        self.stopped = True
        self.log("🛑 Stop requested by user.")

    # ──────────────────────────────────────────────────────────────────────────
    # URL Construction
    # ──────────────────────────────────────────────────────────────────────────
    def construct_search_url(self, keyword: str, location: str, page_num: int = 1) -> str:
        kw_slug = re.sub(r'[^a-zA-Z0-9]+', '-', keyword.strip().lower()).strip('-')
        loc_slug = re.sub(r'[^a-zA-Z0-9]+', '-', location.strip().lower()).strip('-')

        if loc_slug and loc_slug != "remote":
            base_url = f"https://www.naukri.com/{kw_slug}-jobs-in-{loc_slug}"
        else:
            base_url = f"https://www.naukri.com/{kw_slug}-jobs"

        params = {
            "k": keyword,
        }
        if location and location.lower() != "remote":
            params["l"] = location
        freshness = self.config.get("freshness_days")
        if freshness:
            params["jobAge"] = freshness
        if page_num > 1:
            params["pageNo"] = page_num

        return f"{base_url}?{urllib.parse.urlencode(params)}"

    # ──────────────────────────────────────────────────────────────────────────
    # Job ID extraction from card or URL
    # ──────────────────────────────────────────────────────────────────────────
    async def extract_job_id(self, card_element, href: str) -> str:
        job_id = ""
        try:
            job_id = await card_element.get_attribute("data-job-id")
            if not job_id:
                job_id = await card_element.get_attribute("job-id")
        except Exception:
            pass
        if not job_id and href:
            match = re.search(r'-(\d{9,15})(?:\b|$)', href)
            if match:
                job_id = match.group(1)
        if not job_id and href:
            job_id = str(abs(hash(href)))
        return job_id or ""

    # ──────────────────────────────────────────────────────────────────────────
    # INTELLIGENT "WHAT TO APPLY" JOB EVALUATION & SCORING
    # ──────────────────────────────────────────────────────────────────────────
    def evaluate_job_card(self, title: str, company: str, exp_text: str, loc_text: str, tags_text: str = "") -> tuple[bool, str, int]:
        """
        Intelligently evaluates a job posting against user criteria to decide 'What to Apply'.
        Returns: (should_apply: bool, reason: str, match_score: int)
        """
        title_lower = title.lower().strip()
        company_lower = company.lower().strip()
        tags_lower = tags_text.lower()
        combined_text = f"{title_lower} {tags_lower} {loc_text.lower()} {company_lower}"

        # 1. Negative / Blacklisted Keywords Filter
        neg_keywords = [k.strip().lower() for k in self.config.get("negative_keywords", []) if k.strip()]
        for neg in neg_keywords:
            if re.search(r'\b' + re.escape(neg) + r'\b', title_lower):
                return False, f"Matches negative keyword: '{neg}'", 0

        # 2. Blacklisted Companies Filter
        blacklisted_cos = [c.strip().lower() for c in self.config.get("blacklisted_companies", []) if c.strip()]
        for b_co in blacklisted_cos:
            if b_co and b_co in company_lower:
                return False, f"Company '{company}' is blacklisted", 0

        # 3. Strict Experience Range Filter
        candidate_min = float(self.config.get("min_experience", 0))
        candidate_max = float(self.config.get("max_experience", 2))
        is_strict_exp = self.config.get("strict_experience_filter", True)

        job_min_exp = None
        job_max_exp = None
        if exp_text:
            exp_match = re.search(r'(\d+)\s*-\s*(\d+)', exp_text)
            if exp_match:
                job_min_exp = float(exp_match.group(1))
                job_max_exp = float(exp_match.group(2))
            else:
                single_match = re.search(r'(\d+)\+?\s*yr', exp_text, re.IGNORECASE)
                if single_match:
                    job_min_exp = float(single_match.group(1))
                    job_max_exp = job_min_exp + 2.0
                elif "fresher" in exp_text.lower():
                    job_min_exp = 0.0
                    job_max_exp = 1.0

        if is_strict_exp and job_min_exp is not None:
            # If job requires more experience than candidate's upper bound (e.g. requires 4-8 yrs, candidate max is 2 yrs)
            if job_min_exp > candidate_max:
                return False, f"Job requires {exp_text} (exceeds candidate max {candidate_max} yrs)", 0
            if candidate_max <= 2.0 and job_min_exp >= 3.0:
                return False, f"Senior role requires {exp_text} (candidate is entry-level)", 0

        # 4. Relevance & Match Score Calculation (0 - 100)
        score = 0
        keywords = [k.strip().lower() for k in self.config.get("keywords", []) if k.strip()]
        candidate_skills = [s.strip().lower() for s in self.config.get("skills", []) if s.strip()]

        # A. Keyword Matching (Check all keywords, find the best match)
        best_kw_score = 0
        for kw in keywords:
            # Exact phrase match in title (e.g. "Automation Engineer" in title)
            if kw in title_lower:
                best_kw_score = max(best_kw_score, 50)
                break
            # Word-level overlap
            kw_words = [w for w in re.split(r'[^a-z0-9]+', kw) if len(w) > 3 and w not in ('developer', 'engineer')]
            if kw_words:
                matched_words = [w for w in kw_words if re.search(r'\b' + re.escape(w) + r'\b', title_lower)]
                if len(matched_words) == len(kw_words):
                    best_kw_score = max(best_kw_score, 45)
                elif matched_words:
                    best_kw_score = max(best_kw_score, 30)

        # Fallback keyword match: generic role words like developer / engineer / analyst
        if best_kw_score == 0:
            if any(role_word in title_lower for role_word in ['developer', 'engineer', 'programmer', 'software']):
                best_kw_score = 20

        score += best_kw_score

        # B. Skills Match in Title & Card Tags (Up to 35 points)
        matched_skills_count = 0
        for skill in candidate_skills:
            if re.search(r'\b' + re.escape(skill) + r'\b', combined_text):
                matched_skills_count += 1
        score += min(matched_skills_count * 8, 35)

        # C. Location Match (15 points)
        target_locations = [l.strip().lower() for l in self.config.get("locations", []) if l.strip()]
        for loc in target_locations:
            if loc in loc_text.lower() or loc in combined_text or "remote" in loc_text.lower() or "hybrid" in loc_text.lower():
                score += 15
                break

        # D. Experience Fit Bonus (10 points)
        if job_min_exp is not None and job_max_exp is not None:
            total_exp = float(self.config.get("total_experience_years", 1.0))
            if job_min_exp <= total_exp <= job_max_exp or (total_exp <= 1.0 and job_min_exp == 0):
                score += 10

        min_score = int(self.config.get("min_match_score", 35))
        final_score = min(max(score, 0), 100)

        if final_score < min_score:
            return False, f"Match score {final_score}% below threshold {min_score}%", final_score

        return True, f"Relevance score {final_score}%", final_score

    # ──────────────────────────────────────────────────────────────────────────
    # Chatbot / Screening Question Drawer Handler
    # Handles radio options, dropdowns, checkboxes, and text inputs
    # ──────────────────────────────────────────────────────────────────────────
    async def handle_screening_drawer(self, page: Page) -> bool:
        self.log("Inspecting screening question drawer...")
        await asyncio.sleep(1.5)

        MAX_STEPS = 12
        last_question = ""
        repeated_q_count = 0
        for step in range(MAX_STEPS):
            if self.stopped:
                return False

            # Check for immediate success signals
            current_url = page.url.lower()
            current_title = ""
            try:
                current_title = (await page.title()).lower()
            except Exception:
                pass

            if "saveapply" in current_url or "apply confirmation" in current_title or "success" in current_url:
                self.log(f"[SUCCESS SIGNAL] Application confirmation URL detected: {page.url[:60]}")
                return True

            success_loc = page.locator(
                ".applied-msg, "
                ".application-status, "
                "button:has-text('Already Applied'), "
                "span:has-text('Already Applied'), "
                ":has-text('successfully applied'), "
                ":has-text('Applied successfully'), "
                ":has-text('application has been submitted'), "
                "span.already-applied"
            )
            try:
                if await success_loc.count() > 0 and await success_loc.first.is_visible():
                    txt = (await success_loc.first.inner_text()).strip()[:60]
                    self.log(f"[SUCCESS] Confirmation detected: '{txt}'")
                    return True
            except Exception:
                pass

            # Target the real Naukri Easy Apply chatbot drawer
            drawer = page.locator(
                ".chatbot_Drawer, "
                "div[class*='chatbot_Drawer'], "
                "div[class*='chatbot-drawer'], "
                "div.apply-drawer, "
                "div.drawer-wrapper"
            ).first

            try:
                drawer_visible = await drawer.is_visible()
            except Exception:
                drawer_visible = False

            if not drawer_visible:
                # Check if drawer was never opened or just closed after submission
                if step > 0:
                    self.log(f"Screening drawer closed after step {step}. Verifying completion...")
                break

            # Verify that this is an actual screening questionnaire, not a generic support widget
            has_questions = drawer.locator(
                ".bot-msg, .chat-text, .question-wrap, .question-title, "
                "label.radio-label, input[type='radio'], input[type='checkbox'], "
                "input[type='text'], input[type='number'], select"
            )
            try:
                if await has_questions.count() == 0:
                    # Check if drawer shows applied message
                    d_text = (await drawer.inner_text()).lower()
                    if any(term in d_text for term in ["applied", "submitted", "sent your application", "thank you"]):
                        self.log(f"[SUCCESS] Drawer confirms submission: '{d_text[:60]}'")
                        return True
                    self.log(f"Drawer has no pending questions at step {step + 1}. Completing...")
                    break
            except Exception:
                break

            self.log(f"Screening drawer step {step + 1} in progress...")

            # Extract question text accurately
            q_text = "recruiter screening question"
            q_locs = drawer.locator(
                ".botMsg, div[class*='botMsg'], .bot-msg, div[class*='bot-message'], "
                ".msgText, .msg-text, [class*='chatText'], .chat-text, .msg-bubble, "
                ".question-title, .question-wrap, .question, h4, h5"
            )
            try:
                count_q = await q_locs.count()
                for qi in range(count_q - 1, -1, -1):
                    cand_q = (await q_locs.nth(qi).inner_text()).strip()
                    # Skip generic greeting messages
                    if cand_q and len(cand_q) > 4 and not cand_q.lower().startswith("hi ") and "answer all" not in cand_q.lower():
                        q_text = cand_q
                        break
            except Exception:
                pass

            # Smart text fallback from drawer lines if selectors didn't match
            if q_text == "recruiter screening question":
                try:
                    drawer_txt = await drawer.inner_text()
                    lines = [ln.strip() for ln in drawer_txt.splitlines() if ln.strip()]
                    for ln in reversed(lines):
                        if "?" in ln or any(kw in ln.lower() for kw in ["experience", "ctc", "salary", "notice", "location", "relocate", "years", "skill", "qualification"]):
                            if len(ln) > 6 and not ln.lower().startswith("hi "):
                                q_text = ln
                                break
                except Exception:
                    pass

            # Repeated question loop protection
            if q_text == last_question and step > 0:
                repeated_q_count += 1
                if repeated_q_count >= 2:
                    self.log(f"Question '{q_text[:35]}' already answered. Checking completion...")
                    break
            else:
                repeated_q_count = 0
            last_question = q_text

            action_taken = False

            # ── 1. Radio Options & Reply Chips ────────────────────────────────
            radio_labels = drawer.locator(
                "li.chip, div.chip, span.chip, div[class*='chip'], div[class*='bot-option'], "
                "button[class*='chip'], label.radio-label, label, [class*='option'], li[class*='item']"
            )
            try:
                opt_count = await radio_labels.count()
            except Exception:
                opt_count = 0

            if opt_count > 0:
                options_text = []
                for i in range(min(opt_count, 12)):
                    try:
                        txt = (await radio_labels.nth(i).inner_text()).strip()
                        if txt and len(txt) < 80:
                            options_text.append(txt)
                    except Exception:
                        pass

                if options_text:
                    chosen = self.solver.answer_question(q_text, options_text)
                    self.log(f"Q: '{q_text[:40]}' -> Selected Option: '{chosen}'")

                    for i, opt_t in enumerate(options_text):
                        if chosen.lower() in opt_t.lower() or opt_t.lower() in chosen.lower():
                            try:
                                await radio_labels.nth(i).click(timeout=3500)
                                action_taken = True
                                await asyncio.sleep(1.5)
                                try:
                                    d_text = (await drawer.inner_text()).lower()
                                    if any(phrase in d_text for phrase in [
                                        "applied", "submitted", "sent your application", "application sent",
                                        "application received", "successfully", "we have sent", "thank you"
                                    ]):
                                        self.log(f"[SUCCESS] Drawer confirmed: '{d_text[:60]}'")
                                        return True
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            break

            # ── 2. Native <select> Dropdowns ──────────────────────────────────
            select_els = drawer.locator("select")
            try:
                sel_count = await select_els.count()
            except Exception:
                sel_count = 0

            for si in range(sel_count):
                try:
                    s_el = select_els.nth(si)
                    if await s_el.is_visible():
                        opts = await s_el.locator("option").all_inner_texts()
                        opts = [o.strip() for o in opts if o.strip() and not o.lower().startswith("select")]
                        if opts:
                            chosen = self.solver.answer_question(q_text, opts)
                            await s_el.select_option(label=chosen, timeout=3000)
                            self.log(f"Dropdown: '{q_text[:30]}' -> '{chosen}'")
                            action_taken = True
                            await asyncio.sleep(0.5)
                except Exception:
                    pass

            # ── 3. Custom Dropdowns ───────────────────────────────────────────
            custom_dds = drawer.locator(
                "div[class*='dropdown'], div[class*='select-wrapper'], div[class*='customSelect']"
            )
            try:
                cdd_count = await custom_dds.count()
            except Exception:
                cdd_count = 0

            for cdi in range(cdd_count):
                try:
                    dd = custom_dds.nth(cdi)
                    if await dd.is_visible():
                        await dd.click(timeout=3000)
                        await asyncio.sleep(0.5)
                        dd_opts = dd.locator("li, div[class*='option'], span[class*='option']")
                        dd_texts = [
                            (await dd_opts.nth(doi).inner_text()).strip()
                            for doi in range(await dd_opts.count())
                        ]
                        dd_texts = [t for t in dd_texts if t and len(t) < 80]
                        if dd_texts:
                            chosen = self.solver.answer_question(q_text, dd_texts)
                            for doi, opt_t in enumerate(dd_texts):
                                if chosen.lower() in opt_t.lower() or opt_t.lower() in chosen.lower():
                                    await dd_opts.nth(doi).click(timeout=3000)
                                    self.log(f"Custom dropdown '{q_text[:30]}' -> '{chosen}'")
                                    action_taken = True
                                    await asyncio.sleep(0.5)
                                    break
                except Exception:
                    pass

            # ── 4. Checkboxes ─────────────────────────────────────────────────
            checkboxes = drawer.locator("input[type='checkbox']")
            try:
                chk_count = await checkboxes.count()
            except Exception:
                chk_count = 0

            for ci in range(chk_count):
                try:
                    chk = checkboxes.nth(ci)
                    if not await chk.is_checked():
                        await chk.check(timeout=3000)
                        action_taken = True
                        await asyncio.sleep(0.3)
                except Exception:
                    pass

            # ── 5. Text / Number Inputs ───────────────────────────────────────
            text_inputs = drawer.locator("input[type='text'], input[type='number'], textarea")
            try:
                inp_count = await text_inputs.count()
            except Exception:
                inp_count = 0

            for i in range(inp_count):
                try:
                    inp = text_inputs.nth(i)
                    if await inp.is_visible() and not await inp.input_value():
                        placeholder = await inp.get_attribute("placeholder") or ""
                        inp_id = await inp.get_attribute("id") or ""
                        label_el = drawer.locator(f"label[for='{inp_id}']")
                        label_text = ""
                        if await label_el.count() > 0:
                            label_text = await label_el.inner_text()
                        q_label = label_text or placeholder or q_text
                        ans = self.solver.answer_question(q_label)
                        self.log(f"Input '{q_label[:30]}' -> '{ans}'")
                        await inp.fill(str(ans), timeout=3000)
                        action_taken = True
                        await asyncio.sleep(0.3)
                        try:
                            await inp.press("Enter", timeout=2000)
                        except Exception:
                            pass
                except Exception:
                    pass

            # Click send button if present in chat-mode drawer
            send_btn = drawer.locator(
                "button.send-btn, button[class*='send'], .send-icon, button:has-text('Send'), svg[class*='send'], span[class*='send']"
            ).first
            try:
                if await send_btn.count() > 0 and await send_btn.is_visible():
                    await send_btn.click(timeout=3000)
                    action_taken = True
                    await asyncio.sleep(1.0)
            except Exception:
                pass

            # ── 6. Save / Next / Submit Button ────────────────────────────────
            save_btn = drawer.locator(
                "button:has-text('Save'), "
                "button:has-text('Next'), "
                "button:has-text('Submit'), "
                "button:has-text('Apply'), "
                "button:has-text('Continue'), "
                "button:has-text('Submit and Apply'), "
                "[class*='save-btn'], "
                "[class*='submit-btn'], "
                "[role='button']:has-text('Save'), "
                "[role='button']:has-text('Submit')"
            ).first

            try:
                if await save_btn.is_visible():
                    btn_text = (await save_btn.inner_text()).strip()
                    await save_btn.click(timeout=4000)
                    self.log(f"Clicked '{btn_text}' at step {step + 1}")
                    await asyncio.sleep(2.0)
                else:
                    if not action_taken:
                        self.log("No further actions or buttons in drawer. Checking completion...")
                        break
                    await asyncio.sleep(1.5)
            except Exception as btn_err:
                self.log(f"Button click note at step {step + 1}: {btn_err}")
                break

        # Verification after questionnaire completion
        await asyncio.sleep(2)
        try:
            curr_url = page.url.lower()
            curr_title = (await page.title()).lower()
            if "saveapply" in curr_url or "apply confirmation" in curr_title:
                return True

            applied_btn = page.locator("button:has-text('Applied'), span.already-applied, .applied-msg").first
            if await applied_btn.count() > 0 and await applied_btn.is_visible():
                return True

            body_txt = (await page.inner_text("body")).lower()
            if any(term in body_txt for term in ["successfully applied", "application has been submitted", "applied to this job"]):
                return True
        except Exception:
            pass

        return False

    # ──────────────────────────────────────────────────────────────────────────
    # Apply to a single job page
    # ──────────────────────────────────────────────────────────────────────────
    async def apply_to_job(self, page: Page, job_url: str, job_title: str, company: str, location: str, job_id: str) -> str:
        try:
            if not job_url or not job_url.startswith("http"):
                self.log(f"Invalid URL for '{job_title}': '{job_url}'")
                return "skipped"

            # Wait for job page to load
            if "naukri.com" in page.url and page.url != "about:blank":
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)
                except Exception:
                    pass
            else:
                try:
                    await page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
                except PlaywrightTimeout:
                    self.log(f"Timeout loading job page for '{job_title}'")
                    return "failed"

            await asyncio.sleep(2.0)

            # Check for anti-bot block
            try:
                page_title = await page.title()
                if any(x in page_title.lower() for x in ["access denied", "blocked", "403", "captcha"]):
                    self.log(f"Anti-bot block detected for '{job_title}' - skipping")
                    return "failed"
            except Exception:
                pass

            # Check if already applied
            already_applied = page.locator(
                "button:has-text('Already Applied'), "
                "span:has-text('Already Applied'), "
                "div:has-text('You have already applied'), "
                "button:text-is('Applied'), "
                ".already-applied"
            )
            try:
                if await already_applied.count() > 0 and await already_applied.first.is_visible():
                    self.log(f"Already applied previously: '{job_title}' at {company}")
                    self.db.log_application(job_id, job_title, company, location, job_url, "already_applied")
                    return "already_applied"
            except Exception:
                pass

            # ── Easy Apply Button Detection ──────────────────────────────────
            EXTERNAL_KEYWORDS = [
                "company site", "on website", "on company", "apply on company",
                "login to apply", "sign in to apply", "external", "on recruiter"
            ]

            apply_selectors = [
                "button#apply-button",
                "button.apply-button",
                "button:has-text('Easy Apply')",
                "button:has-text('Quick Apply')",
                "[class*='apply-button-container'] button",
                "[class*='jhc__apply'] button",
                "button:has-text('Apply')",
                "a.apply-button",
                "a:has-text('Apply')",
                "button[class*='apply']",
            ]

            apply_btn = None
            for sel in apply_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        btn_text = (await loc.inner_text()).strip().lower()
                        if any(kw in btn_text for kw in EXTERNAL_KEYWORDS):
                            self.log(f"External redirect button found: '{btn_text[:40]}' -> skipping '{job_title}'")
                            self.db.log_application(job_id, job_title, company, location, job_url, "skipped_external")
                            return "skipped"
                        if "apply" not in btn_text:
                            continue
                        apply_btn = loc
                        self.log(f"Found apply button [{sel}]: '{btn_text[:30]}'")
                        break
                except Exception:
                    continue

            if not apply_btn:
                self.log(f"No Easy Apply button found for '{job_title}' (external ATS only).")
                self.db.log_application(job_id, job_title, company, location, job_url, "skipped_external")
                return "skipped"

            # Scroll button into view and click
            try:
                await apply_btn.scroll_into_view_if_needed()
            except Exception:
                pass
            await asyncio.sleep(0.5)

            self.log(f"👉 Clicking Apply: '{job_title}' at {company} [{location}]")
            try:
                await apply_btn.click(timeout=10000)
            except Exception as e:
                self.log(f"Apply button click failed: {e}")
                return "failed"

            await asyncio.sleep(3.0)

            # ── CHECK 1: Immediate 1-Click Instant Apply ──────────────────────
            # Many Naukri Easy Apply jobs complete in 1-click using saved resume
            instant_success = False
            try:
                url_now = page.url.lower()
                title_now = (await page.title()).lower()
                if "saveapply" in url_now or "apply confirmation" in title_now or "success" in url_now:
                    instant_success = True

                # Check if apply button changed to 'Applied'
                status_badge = page.locator(
                    "button#already-applied, "
                    "button:has-text('Already Applied'), "
                    "button:text-is('Applied'), "
                    "span.already-applied, "
                    "span:has-text('Applied successfully'), "
                    ":has-text('successfully applied'), "
                    "div.applied-msg"
                ).first
                if await status_badge.count() > 0 and await status_badge.is_visible():
                    instant_success = True

                # Check for toast notification
                toast = page.locator("div.toaster, div.toast-container, div[class*='toast']").first
                if await toast.count() > 0 and await toast.is_visible():
                    t_text = (await toast.inner_text()).lower()
                    if "applied" in t_text or "success" in t_text:
                        instant_success = True
            except Exception:
                pass

            if instant_success:
                self.log(f"[✓ APPLIED (1-Click Instant)] '{job_title}' at {company}")
                self.db.log_application(job_id, job_title, company, location, job_url, "applied")
                return "applied"

            # ── CHECK 2: Screening Question Drawer ───────────────────────────
            drawer_success = await self.handle_screening_drawer(page)
            if drawer_success:
                self.log(f"[✓ APPLIED via Screening Drawer] '{job_title}' at {company}")
                self.db.log_application(job_id, job_title, company, location, job_url, "applied")
                return "applied"

            # Final verification after drawer handling
            try:
                final_url = page.url.lower()
                final_title = (await page.title()).lower()
                if "saveapply" in final_url or "apply confirmation" in final_title:
                    self.log(f"[✓ APPLIED via URL] '{job_title}' at {company}")
                    self.db.log_application(job_id, job_title, company, location, job_url, "applied")
                    return "applied"

                applied_badge = page.locator(
                    "button:text-is('Applied'), "
                    "button:has-text('Already Applied'), "
                    "span:has-text('Applied successfully'), "
                    ":has-text('successfully applied')"
                ).first
                if await applied_badge.count() > 0 and await applied_badge.is_visible():
                    self.log(f"[✓ APPLIED via status badge] '{job_title}' at {company}")
                    self.db.log_application(job_id, job_title, company, location, job_url, "applied")
                    return "applied"
            except Exception:
                pass

            self.log(f"[✗ UNCONFIRMED] Application not confirmed for '{job_title}'.")
            self.db.log_application(job_id, job_title, company, location, job_url, "failed_unconfirmed")
            return "failed"

        except Exception as e:
            self.log(f"Error applying to '{job_title}': {e}")
            self.db.log_application(job_id, job_title, company, location, job_url, "failed_error", str(e))
            return "failed"

    # ──────────────────────────────────────────────────────────────────────────
    # Process all cards on one search results page
    # ──────────────────────────────────────────────────────────────────────────
    async def process_search_page(self, context: BrowserContext, main_page: Page, loc: str, max_apps: int) -> None:
        try:
            await main_page.wait_for_selector(
                "div.srp-jobtuple-wrapper, div.cust-job-tuple, [data-job-id]",
                timeout=12000
            )
        except Exception:
            pass
        await asyncio.sleep(1.5)

        # Select job cards: Prioritize top wrapper to prevent nested duplicate elements
        cards = main_page.locator("div.srp-jobtuple-wrapper")
        try:
            card_count = await cards.count()
        except Exception:
            card_count = 0

        if card_count == 0:
            cards = main_page.locator("article.jobTuple, div.cust-job-tuple, div[class*='jobTuple']")
            try:
                card_count = await cards.count()
            except Exception:
                card_count = 0

        self.log(f"Found {card_count} job cards on this page.")

        if card_count == 0:
            self.log("No job cards found on this page.")
            return

        seen_job_urls = set()
        seen_job_signatures = set()

        for i in range(card_count):
            if self.stopped or self.applied_count >= max_apps:
                break

            try:
                card = cards.nth(i)

                # FAST FILTER: Skip external-only cards directly from search list
                ext_badge = card.locator(
                    "span:has-text('Apply on company site'), "
                    "a:has-text('Apply on company site'), "
                    "button:has-text('Apply on company')"
                ).first
                try:
                    if await ext_badge.count() > 0 and await ext_badge.is_visible():
                        self.log(f"Card {i+1}: External ATS only — skipped from search results.")
                        self.skipped_count += 1
                        continue
                except Exception:
                    pass

                # Extract title and URL
                title_elem = card.locator("a.title, a.job-title, a[class*='title']").first
                try:
                    if not await title_elem.is_visible():
                        continue
                    job_title = (await title_elem.inner_text()).strip()
                    job_url = await title_elem.get_attribute("href") or ""
                    if job_url.startswith("/"):
                        job_url = "https://www.naukri.com" + job_url
                except Exception:
                    continue

                # Extract company
                company_elem = card.locator("a.comp-name, div.companyInfo a, a[class*='comp']").first
                try:
                    company = (await company_elem.inner_text()).strip() if await company_elem.is_visible() else "Unknown"
                except Exception:
                    company = "Unknown"

                # Deduplicate identical cards on current search page
                if job_url and job_url in seen_job_urls:
                    continue
                sig = (job_title.lower(), company.lower())
                if sig in seen_job_signatures:
                    continue
                if job_url:
                    seen_job_urls.add(job_url)
                seen_job_signatures.add(sig)

                # Extract location
                loc_elem = card.locator("span.loc-wrap, span.locWn, span[class*='loc']").first
                try:
                    job_loc = (await loc_elem.inner_text()).strip() if await loc_elem.is_visible() else loc
                except Exception:
                    job_loc = loc

                # Extract experience
                exp_elem = card.locator("span.exp-wrap, span.exp, span[class*='exp'], span.experience").first
                exp_text = ""
                try:
                    if await exp_elem.is_visible():
                        exp_text = (await exp_elem.inner_text()).strip()
                except Exception:
                    pass

                # Extract tags / skills
                tags_elem = card.locator("ul.tags-gt, .row5, div.ellipsis, [class*='tags']").first
                tags_text = ""
                try:
                    if await tags_elem.is_visible():
                        tags_text = (await tags_elem.inner_text()).strip()
                except Exception:
                    pass

                # Check card text for external site markers
                try:
                    c_text = (await card.inner_text()).lower()
                    if "apply on company site" in c_text:
                        self.log(f"Card {i+1}: External site job skipped: '{job_title}' ({company})")
                        self.skipped_count += 1
                        continue
                except Exception:
                    pass

                # ── INTELLIGENT "WHAT TO APPLY" EVALUATION ────────────────────
                should_apply, eval_reason, match_score = self.evaluate_job_card(
                    job_title, company, exp_text, job_loc, tags_text
                )
                if not should_apply:
                    self.log(f"Card {i+1}: Skipped '{job_title}' ({company}) — {eval_reason}")
                    self.skipped_count += 1
                    continue

                job_id = await self.extract_job_id(card, job_url)

                # Check duplicate in DB
                if self.db.is_already_applied(job_id):
                    self.log(f"Card {i+1}: Already applied in database: '{job_title}'")
                    self.skipped_count += 1
                    continue

                self.log(f"\n[{i+1}/{card_count}] Selected: '{job_title}' ({match_score}% fit) — {company} — {exp_text or 'Exp N/A'} — {job_loc}")

                # ── RELIABLE TAB NAVIGATION TO JOB PAGE ───────────────────────
                job_page = await context.new_page()
                result = "failed"
                try:
                    await job_page.bring_to_front()
                    result = await self.apply_to_job(job_page, job_url, job_title, company, job_loc, job_id)
                finally:
                    try:
                        await job_page.close()
                    except Exception:
                        pass

                if result == "applied":
                    self.applied_count += 1
                elif result in ("skipped", "already_applied", "skipped_external"):
                    self.skipped_count += 1
                else:
                    self.failed_count += 1

                self.log(
                    f"Progress -> Applied: {self.applied_count}/{max_apps} | "
                    f"Skipped: {self.skipped_count} | Failed: {self.failed_count}"
                )
                await asyncio.sleep(2.0)

            except Exception as card_err:
                self.log(f"Error processing card {i+1}: {card_err}")
                continue

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN RUN LOOP
    # ──────────────────────────────────────────────────────────────────────────
    async def run(self):
        keywords = self.config.get("keywords", ["Python Developer"])
        locations = self.config.get("locations", ["Bengaluru"])
        max_apps = int(self.config.get("max_applications_per_run", 25))
        user_data_dir = self.config.get("user_data_dir", "naukri_browser_session")
        headless = bool(self.config.get("headless", False))
        max_pages = int(self.config.get("max_search_pages", 3))

        self.log("=" * 60)
        self.log("🚀 Naukri Easy-Apply Agent — PERFECTED ENGINE")
        self.log(f"Keywords: {keywords}")
        self.log(f"Locations: {locations}")
        self.log(f"Target Applications: {max_apps} | Max Pages/Search: {max_pages}")
        if headless:
            self.log("Browser Mode: HEADLESS (Running in background)")
        else:
            self.log("Browser Mode: VISIBLE (Live Chrome Window on screen)")
        self.log("=" * 60)

        abs_u_dir = os.path.abspath(user_data_dir)

        # ── Self-healing: Clean any stale zombie Chrome processes from previous runs ──
        try:
            import subprocess
            clean_cmd = 'Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*naukri_browser*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'
            subprocess.run(['powershell', '-Command', clean_cmd], capture_output=True, timeout=5)
            # Remove stale lock files if left behind
            for lock_f in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
                lp = os.path.join(abs_u_dir, lock_f)
                if os.path.exists(lp):
                    try:
                        os.remove(lp)
                    except Exception:
                        pass
        except Exception:
            pass

        # Allow Windows to bring new browser window to the active foreground
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass

        async with async_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-position=0,0",
            ]
            context = None
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=abs_u_dir,
                    headless=headless,
                    args=launch_args,
                    no_viewport=True,
                )
                if not headless:
                    self.log("🖥️ [SCREEN] Browser window is now OPEN and visible on your screen!")
                else:
                    self.log("[Browser] Running in background (Headless mode).")
            except Exception as e1:
                self.log(f"[Browser] Launch attempt note: {e1}. Retrying with clean session...")
                try:
                    await asyncio.sleep(1.5)
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=abs_u_dir,
                        headless=headless,
                        args=launch_args,
                        no_viewport=True,
                    )
                    self.log("🖥️ [SCREEN] Browser launched successfully on retry!")
                except Exception as fatal_e:
                    self.log(f"[FATAL] Could not launch browser: {fatal_e}")
                    return

            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            main_page = await context.new_page()
            try:
                await main_page.bring_to_front()
            except Exception:
                pass

            # Verify Naukri Login
            self.log("Checking Naukri login session...")
            try:
                await main_page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=45000)
            except Exception:
                try:
                    await main_page.goto("https://www.naukri.com/", wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    pass

            await asyncio.sleep(2.5)

            is_logged_in = False
            curr_u = main_page.url.lower()
            if "nlogin" not in curr_u and "login" not in curr_u:
                user_indicators = main_page.locator(
                    ".nI-gNb-drawer__user-name, .nI-gNb-header__user-name, .user-name, a[href*='mnjuser/profile'], .view-profile-wrapper"
                )
                try:
                    if await user_indicators.count() > 0 or "profile" in curr_u:
                        is_logged_in = True
                except Exception:
                    is_logged_in = "profile" in curr_u

            if not is_logged_in:
                self.log("\n" + "=" * 50)
                self.log("[!] NOT LOGGED IN TO NAUKRI!")
                self.log("Navigating to login page...")
                try:
                    if "nlogin" not in main_page.url:
                        await main_page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=45000)
                    await main_page.bring_to_front()
                except Exception:
                    pass

                email = self.config.get("naukri_email", "").strip()
                password = self.config.get("naukri_password", "").strip()

                if email and password:
                    self.log(f"Attempting automatic login for: {email[:4]}***")
                    try:
                        await main_page.wait_for_selector("input#usernameField, input[placeholder*='Email']", timeout=15000)
                        u_field = main_page.locator("input#usernameField, input[placeholder*='Email']").first
                        p_field = main_page.locator("input#passwordField, input[type='password']").first
                        await u_field.click()
                        await u_field.fill(email)
                        await asyncio.sleep(0.5)
                        await p_field.click()
                        await p_field.fill(password)
                        await asyncio.sleep(1.0)
                        login_btn = main_page.locator("button[type='submit']:has-text('Login')").first
                        await login_btn.click()
                        self.log("Login form submitted. Waiting for authentication...")
                        await asyncio.sleep(5)
                    except Exception as auto_login_err:
                        self.log(f"Auto-login notice: {auto_login_err}")

                self.log("Waiting up to 180 seconds for login verification (or manual OTP in browser)...")
                self.log("=" * 50 + "\n")

                logged_in_success = False
                otp_notified = False
                for sec in range(180):
                    if self.stopped:
                        break
                    try:
                        u = main_page.url.lower()
                        if "nlogin" not in u and "naukri.com" in u and "login" not in u:
                            self.log(f"[OK] Login detected successfully! URL: {main_page.url[:50]}")
                            logged_in_success = True
                            await asyncio.sleep(2)
                            break

                        if not otp_notified:
                            otp_elem = main_page.locator("input[placeholder*='OTP'], input.otp-input, :has-text('Enter OTP')").first
                            if await otp_elem.count() > 0 and await otp_elem.is_visible():
                                self.log("\n>>> [ACTION REQUIRED] Please enter the OTP in the opened Chrome window. <<<\n")
                                otp_notified = True
                    except Exception:
                        pass
                    if sec > 0 and sec % 15 == 0:
                        self.log(f"Waiting for login... ({180 - sec}s remaining)")
                    await asyncio.sleep(1)

                if not logged_in_success:
                    self.log("[ERROR] Login timeout reached without detecting session. Aborting run.")
                    await context.close()
                    return
            else:
                self.log("[OK] Logged into Naukri successfully!")

            # ── Main Search & Apply Loop ──────────────────────────────────────
            for kw in keywords:
                if self.stopped or self.applied_count >= max_apps:
                    break

                for loc_name in locations:
                    if self.stopped or self.applied_count >= max_apps:
                        break

                    for page_num in range(1, max_pages + 1):
                        if self.stopped or self.applied_count >= max_apps:
                            break

                        search_url = self.construct_search_url(kw, loc_name, page_num)
                        self.log(f"\n🔍 Searching: '{kw}' in '{loc_name}' — Page {page_num}/{max_pages}")
                        self.log(f"   URL: {search_url}")

                        try:
                            await main_page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                        except PlaywrightTimeout:
                            self.log(f"Timeout loading search page for '{kw}' in '{loc_name}' — skipping.")
                            continue

                        await self.process_search_page(context, main_page, loc_name, max_apps)

                        # Check if next page exists
                        if page_num < max_pages:
                            try:
                                next_btn = main_page.locator(
                                    f"a[href*='pageNo={page_num + 1}'], a.fright:has-text('Next'), a:has-text('{page_num + 1}')"
                                ).first
                                if await next_btn.count() == 0 or not await next_btn.is_visible():
                                    self.log(f"No further pages available for '{kw}' in '{loc_name}'.")
                                    break
                            except Exception:
                                break

            self.log("\n" + "=" * 60)
            self.log("🏁 Run Complete!")
            self.log(f"Total Applied: {self.applied_count} | Skipped: {self.skipped_count} | Failed: {self.failed_count}")
            self.log("=" * 60)

            try:
                await context.close()
            except Exception:
                pass


def run_agent_cli():
    cfg = ConfigManager.load_config()
    agent = NaukriAutoApplyAgent(cfg)
    asyncio.run(agent.run())


if __name__ == "__main__":
    run_agent_cli()
