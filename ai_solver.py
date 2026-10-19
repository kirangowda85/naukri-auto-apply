import os
import re
from typing import Dict, Any, List, Optional
from db_logger import DatabaseLogger

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class QuestionSolver:
    """Intelligent Question Solver with Self-Learning Local Memory & Gemini AI."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db = DatabaseLogger()
        self.api_key = config.get("gemini_api_key", "").strip()
        self.client = None

        if HAS_GENAI and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[AI Solver] Gemini client initialization error: {e}")

    def solve_rule_based(self, question_text: str, options: Optional[List[str]] = None) -> Optional[str]:
        """Try matching common standard Naukri recruiter screening questions."""
        q_lower = question_text.lower().strip()
        candidate_skills = [s.lower().strip() for s in self.config.get("skills", [])]
        total_exp = float(self.config.get("total_experience_years", 3.0))

        def fmt_num(val: float) -> str:
            return str(int(val)) if val.is_integer() else str(val)

        # Notice period questions
        if any(term in q_lower for term in ["notice period", "notice", "how soon can you join", "joining time", "serving notice"]):
            np_days = int(self.config.get("notice_period_days", 0))
            if "serving" in q_lower:
                return "Yes" if np_days == 0 else "No"
            if np_days == 0:
                return "Immediate"
            elif np_days <= 15:
                return "15 days"
            elif np_days <= 30:
                return "1 Month"
            elif np_days <= 60:
                return "2 Months"
            else:
                return f"{np_days} days"

        # Current CTC questions
        if any(term in q_lower for term in ["current ctc", "present ctc", "current salary", "present salary", "current fixed ctc"]):
            curr_ctc = float(self.config.get("current_ctc_lakhs", 0.0))
            return fmt_num(curr_ctc)

        # Expected CTC questions
        if any(term in q_lower for term in ["expected ctc", "expected salary", "expectation"]):
            exp_ctc = float(self.config.get("expected_ctc_lakhs", 6.0))
            return fmt_num(exp_ctc)

        # Total Experience questions
        if any(term in q_lower for term in ["total experience", "overall experience", "total years"]):
            return fmt_num(total_exp)

        # Skill-specific experience questions (e.g. "How many years of experience do you have in Python?")
        for skill in candidate_skills:
            if skill in q_lower:
                if any(phrase in q_lower for phrase in ["how many years", "years of experience", "experience in"]):
                    return fmt_num(total_exp)
                if any(phrase in q_lower for phrase in ["do you have experience", "hands-on experience", "hands on", "knowledge of", "familiar with"]):
                    return "Yes"

        # Location & Relocation
        if any(term in q_lower for term in ["current location", "where are you located", "current city", "residing in"]):
            return str(self.config.get("current_location", "Bengaluru"))

        if "relocat" in q_lower:
            return "Yes" if self.config.get("willing_to_relocate", True) else "No"

        # Work Mode / Shifts / Onsite / Hybrid
        if any(term in q_lower for term in ["hybrid", "wfo", "work from office", "willing to travel", "rotational shift", "night shift", "comfortable working"]):
            return "Yes"

        # Education & Qualification
        if any(term in q_lower for term in ["highest qualification", "degree", "education", "graduation"]):
            return str(self.config.get("education", "B.E. Information Science and Engineering"))

        # Gender
        if "gender" in q_lower:
            return str(self.config.get("gender", "Male"))

        # Backlogs / Gaps
        if any(term in q_lower for term in ["backlog", "standing arrears", "active backlogs"]):
            return "No"

        if any(term in q_lower for term in ["gap", "career gap"]):
            return "No"

        # Background check / Police verification / Drug test
        if any(term in q_lower for term in ["background check", "bgv", "verification", "drug"]):
            return "Yes"

        return None

    def find_best_option(self, raw_ans: str, options: List[str], question_text: str = "") -> str:
        """Intelligently map a raw candidate profile answer to one of recruiter's given options."""
        if not options:
            return raw_ans

        q_lower = question_text.lower() if question_text else ""
        ans_lower = raw_ans.lower().strip()

        # 1. Exact match (case-insensitive)
        for opt in options:
            if opt.lower().strip() == ans_lower:
                return opt

        # 2. Boolean (Yes / No)
        if ans_lower in ("yes", "y", "true"):
            for opt in options:
                if "yes" in opt.lower() or opt.lower() in ("y", "agree", "positive"):
                    return opt
        elif ans_lower in ("no", "n", "false"):
            for opt in options:
                if "no" in opt.lower() and "notice" not in opt.lower():
                    return opt

        # 3. Notice Period Special Mapping
        if any(term in q_lower for term in ["notice", "joining", "join"]):
            np_days = int(self.config.get("notice_period_days", 0))
            if np_days <= 15:
                for opt in options:
                    ol = opt.lower()
                    if any(term in ol for term in ["immediate", "0-15", "0 to 15", "15 days", "15 days or less", "serving"]):
                        return opt
            elif np_days <= 30:
                for opt in options:
                    ol = opt.lower()
                    if any(term in ol for term in ["1 month", "30 days", "15-30", "15 to 30", "30"]):
                        return opt
            elif np_days <= 60:
                for opt in options:
                    ol = opt.lower()
                    if any(term in ol for term in ["2 month", "60 days", "30-60", "45-60"]):
                        return opt

        # 4. Numeric Range Mapping (Experience, Salary/CTC, Years)
        num_match = re.search(r'(\d+(?:\.\d+)?)', raw_ans)
        if num_match:
            val = float(num_match.group(1))
            for opt in options:
                opt_l = opt.lower()
                # Fresher match
                if val == 0 and ("fresher" in opt_l or "0 year" in opt_l or "0-1" in opt_l or "0 to 1" in opt_l):
                    return opt
                # Range pattern: e.g. "0-1", "1 to 2", "3 - 5"
                range_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)', opt)
                if range_match:
                    low = float(range_match.group(1))
                    high = float(range_match.group(2))
                    if low <= val <= high:
                        return opt
                # Below / Less than
                if any(w in opt_l for w in ["below", "less than", "<"]):
                    bound = re.search(r'(\d+(?:\.\d+)?)', opt)
                    if bound and val <= float(bound.group(1)):
                        return opt
                # Above / More than / Plus: e.g. "3+ Years", "5+ LPA"
                if any(w in opt_l for w in ["above", "more than", ">", "+"]):
                    bound = re.search(r'(\d+(?:\.\d+)?)', opt)
                    if bound and val >= float(bound.group(1)):
                        return opt

        # 5. Substring containment
        for opt in options:
            if ans_lower in opt.lower() or opt.lower() in ans_lower:
                return opt

        # 6. Word-level overlap
        ans_words = set(re.findall(r'\w+', ans_lower))
        if ans_words:
            best_opt = None
            best_overlap = 0
            for opt in options:
                opt_words = set(re.findall(r'\w+', opt.lower()))
                overlap = len(ans_words.intersection(opt_words))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_opt = opt
            if best_opt and best_overlap > 0:
                return best_opt

        # Fallback to the first option
        return options[0]

    def solve_with_gemini(self, question_text: str, options: Optional[List[str]] = None) -> str:
        """Use Gemini model to answer recruiter questions based on profile details."""
        if not self.client:
            return ""

        skills_str = ", ".join(self.config.get("skills", []))
        profile_summary = (
            f"Role/Headline: {self.config.get('headline')}\n"
            f"Total Experience: {self.config.get('total_experience_years')} years\n"
            f"Current CTC: {self.config.get('current_ctc_lakhs')} LPA\n"
            f"Expected CTC: {self.config.get('expected_ctc_lakhs')} LPA\n"
            f"Notice Period: {self.config.get('notice_period_days')} days\n"
            f"Location: {self.config.get('current_location')}\n"
            f"Key Skills: {skills_str}\n"
            f"Education: {self.config.get('education', 'B.Tech')}\n"
            f"Gender: {self.config.get('gender', 'Male')}\n"
            f"Portfolio: {self.config.get('portfolio_url', '')}\n"
        )

        prompt = (
            f"You are applying for a job on behalf of a job candidate with the following profile:\n{profile_summary}\n\n"
            f"The recruiter asks this screening question:\n'{question_text}'\n\n"
        )

        if options:
            prompt += f"Choose the single BEST matching option from this exact list:\n{options}\n"
            prompt += "Respond ONLY with the exact text of the chosen option, nothing else."
        else:
            prompt += "Provide a concise, professional answer (1-2 sentences max or direct number if numeric)."

        # Try gemini-2.5-flash with fallback to gemini-2.0-flash / gemini-1.5-flash
        for model_name in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                ans = response.text.strip()
                ans = re.sub(r'^["\']|["\']$', '', ans)
                if ans:
                    return ans
            except Exception as e:
                continue
        return ""

    def answer_question(self, question_text: str, options: Optional[List[str]] = None) -> str:
        """Main entry point to obtain an answer. Reuses learned answers from local memory without calling Gemini."""
        if not question_text:
            return options[0] if options else "Yes"

        # --- STEP 1: Self-Learning Local Memory Check ---
        learned_ans = self.db.get_learned_answer(question_text, options)
        if learned_ans:
            final_learned = self.find_best_option(learned_ans, options, question_text) if options else learned_ans
            print(f"[AI Solver Memory] Reused learned answer from local memory (0 Gemini API calls): '{final_learned}' for question: '{question_text[:40]}'")
            return final_learned

        # --- STEP 2: Profile Rule-based Heuristics ---
        rule_ans = self.solve_rule_based(question_text, options)
        if rule_ans:
            final_rule_ans = self.find_best_option(rule_ans, options, question_text) if options else rule_ans
            # Learn rule answer so future exact queries hit Step 1 memory directly
            self.db.save_learned_answer(question_text, final_rule_ans, options, source="rule")
            return final_rule_ans

        # --- STEP 3: Gemini AI Model Call & Auto-Learn ---
        if self.client:
            ai_ans = self.solve_with_gemini(question_text, options)
            if ai_ans:
                final_ai_ans = self.find_best_option(ai_ans, options, question_text) if options else ai_ans
                # Store Gemini answer into local SQLite memory for future ZERO-API reuse!
                self.db.save_learned_answer(question_text, final_ai_ans, options, source="gemini")
                print(f"[AI Solver Self-Learned] Learned & saved new Gemini answer: '{final_ai_ans}' for question: '{question_text[:40]}'")
                return final_ai_ans

        # --- STEP 4: Default Safety Fallback ---
        fallback_ans = "Yes"
        if options:
            fallback_ans = options[0]
        else:
            q_lower = question_text.lower()
            if "ctc" in q_lower or "salary" in q_lower or "lakh" in q_lower:
                fallback_ans = str(int(self.config.get("expected_ctc_lakhs", 4.0)))
            elif "experience" in q_lower or "year" in q_lower:
                fallback_ans = str(int(self.config.get("total_experience_years", 1.0)))

        # Learn fallback choice so user can review or edit in memory tab
        self.db.save_learned_answer(question_text, fallback_ans, options, source="fallback")
        return fallback_ans

