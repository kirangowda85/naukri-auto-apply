import streamlit as st
import pandas as pd
import asyncio
import os
import threading
import time
import queue
import re
import html
from datetime import datetime

from config import ConfigManager
from db_logger import DatabaseLogger
from naukri_agent import NaukriAutoApplyAgent
from profile_booster import ProfileBooster
from resume_parser import ResumeParser
from ai_solver import QuestionSolver
import subprocess

# Cloud environment bootstrap: install Playwright chromium on Streamlit Cloud if missing
if os.name != "nt":
    try:
        pw_cache = os.path.expanduser("~/.cache/ms-playwright")
        if not os.path.exists(pw_cache):
            subprocess.run(["playwright", "install", "chromium"], check=False)
    except Exception:
        pass

# ──────────────────────────────────────────────────────────────────────────────
# Page Configuration
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Naukri Auto-Apply AI Studio",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ──────────────────────────────────────────────────────────────────────────────
# Ultra-Modern Dark & Glassmorphism Design System
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Main Container Styling */
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    /* Header Styling */
    .hero-title {
        font-size: 2.3rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38BDF8 0%, #818CF8 50%, #C084FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.03em;
        margin-bottom: 0.2rem;
    }

    .hero-subtitle {
        font-size: 1rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
        font-weight: 400;
    }

    /* Glass Cards */
    .glass-card {
        background: rgba(18, 24, 38, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 1.3rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(12px);
        margin-bottom: 1.2rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .glass-card:hover {
        border-color: rgba(56, 189, 248, 0.3);
    }

    /* Status Indicators */
    .status-running {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.4);
        color: #34D399;
        padding: 6px 14px;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .status-running .pulse-dot {
        width: 8px;
        height: 8px;
        background-color: #10B981;
        border-radius: 50%;
        box-shadow: 0 0 10px #10B981;
        animation: pulseAnimation 1.5s infinite;
    }
    @keyframes pulseAnimation {
        0% { transform: scale(0.95); opacity: 0.7; }
        50% { transform: scale(1.3); opacity: 1; }
        100% { transform: scale(0.95); opacity: 0.7; }
    }

    .status-idle {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(59, 130, 246, 0.1);
        border: 1px solid rgba(59, 130, 246, 0.3);
        color: #60A5FA;
        padding: 6px 14px;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
    }

    /* Terminal Console — auto-scrolling */
    .cyber-terminal {
        background-color: #0B0F19;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 1.2rem;
        color: #38BDF8;
        font-family: 'JetBrains Mono', 'Consolas', monospace;
        font-size: 0.82rem;
        height: 440px;
        overflow-y: auto;
        white-space: pre-wrap;
        line-height: 1.6;
        box-shadow: inset 0 2px 10px rgba(0,0,0,0.6);
        scroll-behavior: smooth;
    }
    .cyber-terminal::-webkit-scrollbar {
        width: 8px;
    }
    .cyber-terminal::-webkit-scrollbar-thumb {
        background: #1E293B;
        border-radius: 4px;
    }

    /* Log line coloring */
    .log-success { color: #34D399; }
    .log-error { color: #F87171; }
    .log-warning { color: #FBBF24; }
    .log-info { color: #60A5FA; }
    .log-action { color: #C084FC; }
    .log-separator { color: #475569; }

    /* Feature Badge & Tags */
    .badge-chip {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .badge-match {
        background: rgba(16, 185, 129, 0.2);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-neg {
        background: rgba(239, 68, 68, 0.2);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* Highlight Banner */
    .banner-ready {
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.05));
        border-left: 4px solid #10B981;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 1.2rem;
    }
    .banner-warning {
        background: linear-gradient(90deg, rgba(245, 158, 11, 0.15), rgba(217, 119, 6, 0.05));
        border-left: 4px solid #F59E0B;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 1.2rem;
    }

    /* Stat Cards */
    .stat-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        text-align: center;
    }
    .stat-value {
        font-size: 1.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38BDF8, #818CF8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .stat-label {
        font-size: 0.78rem;
        color: #94A3B8;
        margin-top: 4px;
        font-weight: 500;
    }

    /* Score Bar */
    .score-bar-track {
        background: rgba(255,255,255,0.06);
        border-radius: 6px;
        height: 10px;
        overflow: hidden;
        margin-top: 6px;
    }
    .score-bar-fill {
        height: 100%;
        border-radius: 6px;
        transition: width 0.4s ease;
    }
    .score-green { background: linear-gradient(90deg, #10B981, #34D399); }
    .score-yellow { background: linear-gradient(90deg, #F59E0B, #FBBF24); }
    .score-red { background: linear-gradient(90deg, #EF4444, #F87171); }
</style>
""", unsafe_allow_html=True)

LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "agent_run.log")
_log_queue: queue.Queue = queue.Queue()
_ACTIVE_AGENT = None

# Initialize Session State
if "running" not in st.session_state:
    st.session_state["running"] = False

def append_log(msg: str):
    """Queue-backed log handler for UI notifications."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    _log_queue.put(log_entry)
    print(log_entry)

def colorize_log_line(line: str) -> str:
    """Add color classes to log lines for the terminal."""
    escaped = html.escape(line)
    if any(kw in line for kw in ["[SUCCESS", "[✓ APPLIED", "[OK]", "APPLIED", "successfully"]):
        return f'<span class="log-success">{escaped}</span>'
    elif any(kw in line for kw in ["[ERROR", "[FATAL", "Error", "failed", "FAILED", "[✗"]):
        return f'<span class="log-error">{escaped}</span>'
    elif any(kw in line for kw in ["[WARNING", "Skipping", "Filtered", "Skip", "SKIP", "[!]"]):
        return f'<span class="log-warning">{escaped}</span>'
    elif any(kw in line for kw in ["Selected:", "Clicking Apply", "Progress →", "Found apply", "SCREEN"]):
        return f'<span class="log-action">{escaped}</span>'
    elif line.strip().startswith("===") or line.strip().startswith("---"):
        return f'<span class="log-separator">{escaped}</span>'
    else:
        return escaped

def get_latest_status_message() -> str:
    """Return the most recent meaningful action line from the log."""
    if not os.path.exists(LOG_FILE_PATH):
        return "Agent standby. Click 'Launch Auto-Apply Agent' to start."
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("===")]
            if not lines:
                return "Agent standby. Click 'Launch Auto-Apply Agent' to start."
            for l in reversed(lines):
                if any(k in l for k in ["Progress", "Searching:", "Selected:", "Clicking Apply", "APPLIED", "Checking Naukri", "Run Complete", "SCREEN"]):
                    return re.sub(r'\[\d{2}:\d{2}:\d{2}\]\s*', '', l)
            return lines[-1]
    except Exception:
        return "Agent active..."

def get_live_logs(max_lines: int = 150, newest_first: bool = True) -> str:
    """Read recent logs directly from agent_run.log file with colorized output."""
    if not os.path.exists(LOG_FILE_PATH):
        return '<div class="log-line log-info">Agent standby. Click \'Launch Auto-Apply Agent\' to start.</div>'
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            if not lines:
                return '<div class="log-line log-info">Agent standby. Click \'Launch Auto-Apply Agent\' to start.</div>'
            recent = lines[-max_lines:]
            if newest_first:
                recent = list(reversed(recent))
            colored_lines = [f'<div style="margin-bottom: 2px;">{colorize_log_line(line)}</div>' for line in recent]
            return "\n".join(colored_lines)
    except Exception:
        return '<div class="log-line log-info">Loading live logs...</div>'

def drain_log_queue():
    """Flush queue to update running status."""
    while not _log_queue.empty():
        try:
            entry = _log_queue.get_nowait()
            if entry == "__AGENT_DONE__":
                st.session_state["running"] = False
        except queue.Empty:
            break

drain_log_queue()

# Load Configuration and DB
config = ConfigManager.load_config()
db = DatabaseLogger()

# ──────────────────────────────────────────────────────────────────────────────
# Top Hero Banner
# ──────────────────────────────────────────────────────────────────────────────
col_header_left, col_header_right = st.columns([3, 1])
with col_header_left:
    st.markdown('<div class="hero-title">💼 Naukri Auto-Apply & Booster Studio</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">Intelligent Job Selection • Rule-Based Screening Solver • Zero Duplicate Applications • Profile Rank Bumping</div>', unsafe_allow_html=True)

with col_header_right:
    if st.session_state.get("running"):
        st.markdown('''
        <div style="text-align: right; margin-top: 10px;">
            <div class="status-running">
                <span class="pulse-dot"></span> Agent Active & Applying
            </div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.markdown('''
        <div style="text-align: right; margin-top: 10px;">
            <div class="status-idle">
                ● Ready / Standby
            </div>
        </div>
        ''', unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar: Settings & Execution Controls
# ──────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown("### ⚙️ Quick Agent Controls")

# Visual Headless Toggle — FIXED: Properly ensures visible browser
headless_toggle = st.sidebar.toggle(
    "🖥️ Run in Visible Browser (See on Screen)",
    value=not bool(config.get("headless", False)),
    help="When ON, Playwright opens a live Google Chrome window right on your screen so you can observe actions in real time!"
)
# Show clear status of browser visibility
if headless_toggle:
    st.sidebar.success("✅ Browser will open **visibly on your screen**")
else:
    st.sidebar.info("🔲 Browser runs in background (headless mode)")

max_apps_slider = st.sidebar.slider(
    "Max Applications Limit",
    min_value=5,
    max_value=100,
    value=int(config.get("max_applications_per_run", 25)),
    step=5
)

freshness_slider = st.sidebar.select_slider(
    "Job Freshness Filter",
    options=[1, 3, 7, 15, 30],
    value=int(config.get("freshness_days", 7)),
    format_func=lambda x: f"Posted last {x} days"
)

# Auto-refresh rate while running
refresh_rate = st.sidebar.slider(
    "Live Log Refresh Rate (seconds)",
    min_value=1,
    max_value=10,
    value=3,
    step=1,
    help="How often the terminal refreshes while the agent is running"
)

st.sidebar.divider()

# Credentials section
with st.sidebar.expander("🔐 Naukri Account Credentials", expanded=False):
    st.caption("Saved locally in encrypted session. Used for automatic login.")
    n_email = st.text_input("Naukri Email", value=str(config.get("naukri_email", "")))
    n_pass = st.text_input("Naukri Password", value=str(config.get("naukri_password", "")), type="password")
    gemini_key = st.text_input("Gemini API Key (Optional AI Backup)", value=str(config.get("gemini_api_key", "")), type="password")

if st.sidebar.button("💾 Save Quick Controls", use_container_width=True, type="primary"):
    upd = config.copy()
    upd.update({
        "headless": not headless_toggle,
        "max_applications_per_run": max_apps_slider,
        "freshness_days": freshness_slider,
        "naukri_email": n_email,
        "naukri_password": n_pass,
        "gemini_api_key": gemini_key,
    })
    ConfigManager.save_config(upd)
    config = upd
    st.sidebar.success("Settings saved!")

# ──────────────────────────────────────────────────────────────────────────────
# Main Tab Layout
# ──────────────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "🚀 Mission Control",
    "🎯 'What to Apply' Studio",
    "👤 Candidate Profile & Resume",
    "🧠 Q&A Memory & AI Sandbox",
    "📊 Application Analytics",
    "ℹ️ How It Works"
])

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1: MISSION CONTROL
# ──────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    stats = db.get_stats()
    qna_stats = db.get_qna_stats()

    # Metric Row
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Total Applied", stats["total_applied"], delta=f"+{stats['today_applied']} today")
    with m2:
        st.metric("Applied Today", stats["today_applied"], delta="Target 25-50/day")
    with m3:
        st.metric("Filtered / Skipped", stats["total_failed"], help="Excluded due to experience, negative keywords, or external site redirects")
    with m4:
        st.metric("Learned Q&A Rules", qna_stats["total_learned"], delta=f"{qna_stats['total_uses']} answers served")
    with m5:
        st.metric("Gemini API Calls Saved", qna_stats["api_calls_saved"], delta="100% Free Local Memory")

    st.write("")

    # Action Buttons Row
    c_btn_apply, c_btn_stop, c_btn_boost, c_btn_clear, c_btn_refresh = st.columns([2.2, 1.8, 2.2, 1.2, 1.2])

    with c_btn_apply:
        if st.button("🚀 Launch Auto-Apply Agent", use_container_width=True, type="primary", disabled=st.session_state["running"]):
            st.session_state["running"] = True

            # Clear old logs for fresh run
            try:
                with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception:
                pass

            append_log(f"Starting Auto-Apply Agent [Target: {max_apps_slider} jobs]...")
            if not config.get("headless", False):
                append_log("Browser mode: VISIBLE (Opening Chrome on your screen)")
            else:
                append_log("Browser mode: HEADLESS (Background)")

            def run_agent_bg():
                global _ACTIVE_AGENT
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cur_cfg = ConfigManager.load_config()
                # Apply current sidebar controls directly
                cur_cfg["headless"] = not headless_toggle
                cur_cfg["max_applications_per_run"] = max_apps_slider
                cur_cfg["freshness_days"] = freshness_slider
                ConfigManager.save_config(cur_cfg)
                agent = NaukriAutoApplyAgent(cur_cfg, logger_callback=append_log)
                _ACTIVE_AGENT = agent
                try:
                    loop.run_until_complete(agent.run())
                except Exception as e:
                    append_log(f"[ERROR] Agent run error: {e}")
                finally:
                    _ACTIVE_AGENT = None
                    _log_queue.put("__AGENT_DONE__")

            t = threading.Thread(target=run_agent_bg, daemon=True)
            t.start()
            st.rerun()

    with c_btn_stop:
        if st.button("🛑 Stop Agent", use_container_width=True, disabled=not st.session_state["running"]):
            if _ACTIVE_AGENT:
                _ACTIVE_AGENT.stop()
            st.session_state["running"] = False
            append_log("[STOPPED] Stop requested by user.")
            st.rerun()

    with c_btn_boost:
        if st.button("⚡ Boost Profile Rank (Naukri Bumper)", use_container_width=True, disabled=st.session_state["running"]):
            st.session_state["running"] = True
            append_log("Initializing Profile Booster to refresh 'Recently Updated' rank...")

            def run_booster_bg():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cur_cfg = ConfigManager.load_config()
                booster = ProfileBooster(cur_cfg)
                try:
                    res = loop.run_until_complete(booster.boost_profile())
                    if res:
                        append_log("[SUCCESS] Profile headline bumped! Recruiter search rank refreshed.")
                    else:
                        append_log("[WARNING] Profile booster finished with warnings.")
                except Exception as e:
                    append_log(f"[ERROR] Booster failed: {e}")
                finally:
                    _log_queue.put("__AGENT_DONE__")

            t = threading.Thread(target=run_booster_bg, daemon=True)
            t.start()
            st.rerun()

    with c_btn_clear:
        if st.button("🧹 Clear Logs", use_container_width=True):
            try:
                with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception:
                pass
            st.rerun()

    with c_btn_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    # Terminal Log Box — colorized & live
    col_t_title, col_t_ctrl = st.columns([3, 2])
    with col_t_title:
        st.subheader("🖥️ Live Execution Terminal")
    with col_t_ctrl:
        order_choice = st.radio(
            "Sort Order:",
            options=["🔽 Newest on Top (Live)", "🔼 Chronological"],
            horizontal=True,
            index=0,
            help="When 'Newest on Top' is selected, the freshest real-time step is always right at the top of the terminal."
        )
    newest_first = "Newest" in order_choice

    latest_msg = get_latest_status_message()
    st.markdown(f'''
    <div style="background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 10px 16px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
            <span style="color: #38BDF8; font-weight: 700; font-size: 0.85rem;">⚡ CURRENT STEP:</span>
            <span style="color: #F8FAFC; font-family: monospace; font-size: 0.85rem; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">{html.escape(latest_msg)}</span>
        </div>
        <div style="flex-shrink: 0; margin-left: 12px;">
            <span style="font-size: 0.75rem; color: #34D399; font-weight: 600; background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.3); padding: 3px 10px; border-radius: 9999px;">● Live Stream</span>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    log_content = get_live_logs(max_lines=150, newest_first=newest_first)
    st.markdown(
        f'<div id="cyber-terminal-box" class="cyber-terminal">{log_content}</div>',
        unsafe_allow_html=True
    )

    # Auto refresh loop if running — uses configurable refresh rate
    if st.session_state.get("running"):
        time.sleep(refresh_rate)
        drain_log_queue()
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2: "WHAT TO APPLY" INTELLIGENCE STUDIO
# ──────────────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("🎯 'What to Apply' Precision Filtering Studio")
    st.write("Control exactly which jobs the agent selects and which jobs it skips. Prevents applying to senior roles, internships, sales, or wrong tech stacks.")

    with st.form("what_to_apply_form"):
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            st.markdown("#### ✅ Target Roles & Positive Match")
            kw_val = st.text_area(
                "Target Keywords / Titles (comma separated)",
                value=", ".join(config.get("keywords", [])),
                help="The agent searches and prioritizes jobs matching these titles."
            )
            loc_val = st.text_input(
                "Target Locations (comma separated)",
                value=", ".join(config.get("locations", [])),
                help="Cities to apply for (e.g. Bengaluru, Remote, Hyderabad)"
            )

            skills_val = st.text_area(
                "Key Skills to Match in Job Tags (comma separated)",
                value=", ".join(config.get("skills", [])),
                help="Skills matched in the job card's tags will increase the relevance score."
            )

            c_exp_min, c_exp_max = st.columns(2)
            with c_exp_min:
                min_exp_inp = st.number_input("Candidate Min Exp (Yrs)", 0, 30, int(config.get("min_experience", 0)))
            with c_exp_max:
                max_exp_inp = st.number_input("Candidate Max Exp (Yrs)", 0, 30, int(config.get("max_experience", 2)))

            strict_exp = st.checkbox(
                "Strict Experience Verification",
                value=bool(config.get("strict_experience_filter", True)),
                help="Automatically skips any job card if the required experience exceeds your maximum range."
            )

        with col_f2:
            st.markdown("#### 🚫 Negative Filters & Blacklist")
            neg_kw_val = st.text_area(
                "Negative Keywords (comma separated — Skip if found in title)",
                value=", ".join(config.get("negative_keywords", ["Internship", "Intern", "Non-tech", "Trainer", "Sales", "Telecaller", "Technical Support"])),
                help="Jobs with these words in their title will be immediately filtered out."
            )

            blacklist_cos = st.text_area(
                "Blacklisted Companies (comma separated)",
                value=", ".join(config.get("blacklisted_companies", [])),
                help="Companies you do NOT want to apply to."
            )

            min_score_inp = st.slider(
                "Minimum Relevance Score (%)",
                min_value=10,
                max_value=80,
                value=int(config.get("min_match_score", 35)),
                step=5,
                help="Jobs below this relevance match score will be skipped."
            )

            st.markdown("#### 📄 Pagination")
            max_pages_inp = st.number_input(
                "Max Search Result Pages to Scan",
                min_value=1,
                max_value=20,
                value=int(config.get("max_search_pages", 3)),
                help="Agent will navigate through this many pages of search results per keyword/location combo."
            )

        submit_filters = st.form_submit_button("💾 Save 'What to Apply' Criteria", type="primary", use_container_width=True)

        if submit_filters:
            new_cfg = config.copy()
            new_cfg.update({
                "keywords": [k.strip() for k in kw_val.split(",") if k.strip()],
                "locations": [l.strip() for l in loc_val.split(",") if l.strip()],
                "skills": [s.strip() for s in skills_val.split(",") if s.strip()],
                "min_experience": min_exp_inp,
                "max_experience": max_exp_inp,
                "strict_experience_filter": strict_exp,
                "negative_keywords": [k.strip() for k in neg_kw_val.split(",") if k.strip()],
                "blacklisted_companies": [c.strip() for c in blacklist_cos.split(",") if c.strip()],
                "min_match_score": min_score_inp,
                "max_search_pages": max_pages_inp,
            })
            ConfigManager.save_config(new_cfg)
            config = new_cfg
            st.success("Target job filters updated successfully!")
            st.rerun()

    st.divider()

    # Live Interactive Match Simulator
    st.subheader("🧪 Live Job Fit Simulator")
    st.caption("Type any sample job title, company, and experience below to preview how the 'What to Apply' engine scores and decides.")

    c_sim1, c_sim2, c_sim3, c_sim4 = st.columns([2, 1.5, 1, 1])
    with c_sim1:
        sim_title = st.text_input("Sample Job Title", value="Junior Python Developer")
    with c_sim2:
        sim_company = st.text_input("Sample Company", value="Tech Corp")
    with c_sim3:
        sim_exp = st.text_input("Experience (e.g. 0-2 Yrs)", value="0-2 Yrs")
    with c_sim4:
        sim_loc = st.text_input("Location", value="Bengaluru")

    if st.button("⚡ Test Job Fit Decision"):
        test_agent = NaukriAutoApplyAgent(config)
        decision, reason, score = test_agent.evaluate_job_card(sim_title, sim_company, sim_exp, sim_loc)

        # Visual score bar
        bar_color = "score-green" if score >= 60 else "score-yellow" if score >= 40 else "score-red"
        score_bar = f'''
        <div class="score-bar-track">
            <div class="score-bar-fill {bar_color}" style="width: {min(score, 100)}%;"></div>
        </div>
        '''

        if decision:
            st.markdown(f'''
            <div class="banner-ready">
                <b>Decision: ✅ APPLY</b> — {reason}
                {score_bar}
            </div>
            ''', unsafe_allow_html=True)
        else:
            st.markdown(f'''
            <div class="banner-warning">
                <b>Decision: ❌ SKIP</b> — {reason}
                {score_bar}
            </div>
            ''', unsafe_allow_html=True)

    # Current config summary
    st.divider()
    st.subheader("📋 Current 'What to Apply' Config Summary")
    cfg_c1, cfg_c2 = st.columns(2)
    with cfg_c1:
        st.markdown("**Target Keywords:**")
        for kw in config.get("keywords", []):
            st.markdown(f'<span class="badge-chip badge-match">✅ {kw}</span>', unsafe_allow_html=True)
        st.markdown("**Target Locations:**")
        for loc in config.get("locations", []):
            st.markdown(f'<span class="badge-chip badge-match">📍 {loc}</span>', unsafe_allow_html=True)
    with cfg_c2:
        st.markdown("**Negative Keywords:**")
        for nk in config.get("negative_keywords", []):
            st.markdown(f'<span class="badge-chip badge-neg">🚫 {nk}</span>', unsafe_allow_html=True)
        st.markdown(f"**Min Match Score:** {config.get('min_match_score', 40)}%")
        st.markdown(f"**Experience Range:** {config.get('min_experience', 0)}–{config.get('max_experience', 5)} years")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3: CANDIDATE PROFILE & RESUME
# ──────────────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("📄 Resume Upload & Automated Profile Extraction")
    st.write("Upload your resume to automatically extract your skills, experience, and profile summary.")

    uploaded_file = st.file_uploader("Upload Resume (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], key="res_upload")

    if uploaded_file is not None:
        if st.button("⚡ Extract Details from Resume", type="primary"):
            with st.spinner("Parsing resume details..."):
                resume_dir = os.path.join(os.path.dirname(__file__), "resumes")
                os.makedirs(resume_dir, exist_ok=True)
                save_path = os.path.join(resume_dir, uploaded_file.name)
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                parser = ResumeParser(api_key=config.get("gemini_api_key", ""))
                parsed_data, raw_text = parser.parse_resume(uploaded_file, uploaded_file.name)

                if parsed_data:
                    upd_cfg = config.copy()
                    upd_cfg["resume_path"] = save_path
                    upd_cfg["resume_filename"] = uploaded_file.name
                    for k in ["total_experience_years", "skills", "headline", "education"]:
                        if k in parsed_data and parsed_data[k]:
                            upd_cfg[k] = parsed_data[k]
                    ConfigManager.save_config(upd_cfg)
                    config = upd_cfg
                    st.success(f"Resume '{uploaded_file.name}' parsed! Details updated.")
                    st.json(parsed_data)
                else:
                    st.warning("Could not extract structured fields. Raw text extracted.")
                    if raw_text:
                        st.text_area("Extracted Resume Text", value=raw_text[:1200], height=160)

    st.divider()

    # Candidate Profile Readiness
    st.subheader("👤 Candidate Profile Details")

    missing = []
    if not config.get("skills"): missing.append("Key Skills")
    if config.get("notice_period_days") is None: missing.append("Notice Period")
    if not config.get("current_location"): missing.append("Current Location")
    if not config.get("headline"): missing.append("Resume Headline")

    if missing:
        st.markdown(f'''
        <div class="banner-warning">
            <b>⚠️ {len(missing)} Recommended Fields Missing:</b> {", ".join(missing)}. Fill them in below for 100% automated form filling.
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.markdown('''
        <div class="banner-ready">
            <b>✅ Profile 100% Ready!</b> All candidate details are configured for automated screening questions.
        </div>
        ''', unsafe_allow_html=True)

    with st.form("candidate_profile_edit"):
        cp1, cp2, cp3 = st.columns(3)
        with cp1:
            f_exp = st.number_input("Total Experience (Years)", 0.0, 40.0, float(config.get("total_experience_years", 1.0)), step=0.5)
            f_curr_ctc = st.number_input("Current CTC (LPA)", 0.0, 200.0, float(config.get("current_ctc_lakhs", 0.0)), step=0.5)
            f_exp_ctc = st.number_input("Expected CTC (LPA)", 0.0, 200.0, float(config.get("expected_ctc_lakhs", 6.0)), step=0.5)

        with cp2:
            f_notice = st.selectbox(
                "Notice Period",
                options=[0, 15, 30, 60, 90],
                index=0 if config.get("notice_period_days") == 0 else 1 if config.get("notice_period_days") == 15 else 2,
                format_func=lambda x: "Immediate (0 days)" if x == 0 else f"{x} days"
            )
            f_city = st.text_input("Current Location / City", value=str(config.get("current_location", "Bengaluru")))
            f_relocate = st.checkbox("Willing to Relocate?", value=bool(config.get("willing_to_relocate", True)))

        with cp3:
            f_edu = st.text_input("Highest Degree / Education", value=str(config.get("education", "B.E. Information Science")))
            f_gender = st.selectbox("Gender", options=["Male", "Female", "Other"], index=0 if config.get("gender") == "Male" else 1)
            f_github = st.text_input("GitHub / Portfolio URL", value=str(config.get("portfolio_url", "")))

        f_skills = st.text_area("Key Skills (comma separated)", value=", ".join(config.get("skills", [])))
        f_headline = st.text_area("Resume Headline (Used for Profile Booster Bump)", value=str(config.get("headline", "")))

        if st.form_submit_button("💾 Save Profile Changes", type="primary", use_container_width=True):
            upd_p = config.copy()
            upd_p.update({
                "total_experience_years": f_exp,
                "current_ctc_lakhs": f_curr_ctc,
                "expected_ctc_lakhs": f_exp_ctc,
                "notice_period_days": f_notice,
                "current_location": f_city,
                "willing_to_relocate": f_relocate,
                "education": f_edu,
                "gender": f_gender,
                "portfolio_url": f_github,
                "skills": [s.strip() for s in f_skills.split(",") if s.strip()],
                "headline": f_headline
            })
            ConfigManager.save_config(upd_p)
            config = upd_p
            st.success("Candidate Profile updated successfully!")
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# TAB 4: Q&A MEMORY & AI SANDBOX
# ──────────────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("🧠 Self-Learning Question-Answer Knowledge Base")
    st.write("Every screening question answered during applications is memorized here. Subsequent identical or similar questions use local memory without making any external Gemini API calls.")

    # Sandbox / Tester
    st.markdown("#### 🧪 Test Screening Question Solver")
    with st.form("test_q_form"):
        cq1, cq2 = st.columns([3, 1])
        with cq1:
            test_q = st.text_input("Enter any recruiter question", value="How many years of experience in Python?")
        with cq2:
            test_opts = st.text_input("Options (optional, comma-sep)", value="")

        test_btn = st.form_submit_button("⚡ Test Answer Solver", type="primary")
        if test_btn and test_q:
            opts_list = [o.strip() for o in test_opts.split(",") if o.strip()] if test_opts else None
            solver = QuestionSolver(config)
            ans = solver.answer_question(test_q, opts_list)
            st.success(f"**Solved Answer:** `{ans}`")

    st.divider()

    # Manual Q&A Rule Add
    with st.expander("➕ Add Custom Screening Question Rule", expanded=False):
        with st.form("add_custom_qna"):
            add_q = st.text_input("Question (e.g. 'Are you comfortable working in hybrid mode?')")
            add_ans = st.text_input("Answer (e.g. 'Yes')")
            if st.form_submit_button("💾 Save Rule", type="primary") and add_q and add_ans:
                db.save_learned_answer(add_q, add_ans, source="manual")
                st.success("Saved new rule to local memory!")
                st.rerun()

    # Display All Stored Q&A
    st.subheader("📚 Saved Q&A Rules in Local SQLite")
    all_rules = db.get_all_learned_qna()

    if all_rules:
        search_kw = st.text_input("🔍 Search stored questions", value="")
        filtered = [r for r in all_rules if not search_kw or search_kw.lower() in r["original_question"].lower() or search_kw.lower() in r["answer"].lower()]
        st.caption(f"Showing {len(filtered)} of {len(all_rules)} stored rules")

        for r in filtered:
            with st.container():
                col_rq1, col_rq2, col_rq3, col_rq4 = st.columns([4, 3, 2, 1])
                with col_rq1:
                    st.markdown(f"**Q:** {r['original_question']}")
                with col_rq2:
                    st.markdown(f"**A:** `{r['answer']}`")
                with col_rq3:
                    st.caption(f"Source: `{r['source']}` • Used: **{r['use_count']}**")
                with col_rq4:
                    if st.button("🗑️", key=f"del_q_{r['id']}"):
                        db.delete_learned_qna(r["id"])
                        st.toast("Rule deleted")
                        st.rerun()
                st.divider()
    else:
        st.info("No Q&A pairs recorded yet. As the agent runs and answers recruiter questions, rules will populate here automatically.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 5: APPLICATION ANALYTICS
# ──────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("📊 Job Application History & Tracker")
    df = db.get_applied_jobs_df()

    if not df.empty:
        # Summary stats row
        stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
        with stat_c1:
            applied_count = len(df[df["status"] == "applied"])
            st.markdown(f'''
            <div class="stat-card">
                <div class="stat-value">{applied_count}</div>
                <div class="stat-label">Successfully Applied</div>
            </div>
            ''', unsafe_allow_html=True)
        with stat_c2:
            skipped_count = len(df[df["status"].str.contains("skip", case=False, na=False)])
            st.markdown(f'''
            <div class="stat-card">
                <div class="stat-value">{skipped_count}</div>
                <div class="stat-label">Skipped / Filtered</div>
            </div>
            ''', unsafe_allow_html=True)
        with stat_c3:
            failed_count = len(df[df["status"].str.contains("fail", case=False, na=False)])
            st.markdown(f'''
            <div class="stat-card">
                <div class="stat-value">{failed_count}</div>
                <div class="stat-label">Failed / Unconfirmed</div>
            </div>
            ''', unsafe_allow_html=True)
        with stat_c4:
            unique_cos = df["company"].nunique()
            st.markdown(f'''
            <div class="stat-card">
                <div class="stat-value">{unique_cos}</div>
                <div class="stat-label">Unique Companies</div>
            </div>
            ''', unsafe_allow_html=True)

        st.write("")

        col_flt1, col_flt2 = st.columns([2, 1])
        with col_flt1:
            all_statuses = df["status"].unique().tolist()
            sel_statuses = st.multiselect("Filter by Status", options=all_statuses, default=all_statuses)
        with col_flt2:
            search_job = st.text_input("Search Job / Company", value="")

        filtered_df = df[df["status"].isin(sel_statuses)]
        if search_job:
            filtered_df = filtered_df[
                filtered_df["title"].str.contains(search_job, case=False, na=False) |
                filtered_df["company"].str.contains(search_job, case=False, na=False)
            ]

        st.dataframe(
            filtered_df[["applied_at", "title", "company", "location", "status", "url"]],
            column_config={
                "url": st.column_config.LinkColumn("Naukri Link"),
                "applied_at": "Applied Timestamp",
                "title": "Role Title",
                "company": "Company",
                "location": "Location",
                "status": "Outcome Status"
            },
            use_container_width=True,
            height=440
        )

        csv_bytes = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV Report",
            data=csv_bytes,
            file_name="naukri_applied_jobs.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        st.info("No applications logged yet. Click 'Launch Auto-Apply Agent' on Tab 1 to start applying!")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 6: HOW IT WORKS
# ──────────────────────────────────────────────────────────────────────────────
with tabs[5]:
    st.markdown("""
    ### 💼 How the Auto-Apply & Booster Agent Works

    1. **Organic Browser Automation**:
       - Uses Playwright with your local Google Chrome profile (`naukri_browser_session`).
       - Cookies and login state remain saved permanently.
       - Runs directly on your screen (Visible mode) or hidden in the background (Headless mode).

    2. **Intelligent 'What to Apply' Precision Engine**:
       - Pre-screens every job card from search results.
       - Evaluates title relevance, keywords, and skill matches.
       - Filters out blacklisted companies, negative titles (e.g. internships, trainers, non-tech).
       - Enforces strict experience overlap checks to ensure you only apply for roles matching your level.
       - Calculates a relevance match score (0-100%) and skips jobs below your configured threshold.

    3. **Automated Screening Question Solver**:
       - Handles single/multi-choice radio buttons, dropdowns, and text inputs.
       - Solves standard recruiter questions (Notice period, CTC, experience, relocation) using fast rule heuristics.
       - Saves every answered question in your local SQLite memory (`naukri_jobs.db`), ensuring zero duplicate AI calls.

    4. **Multi-Page Search Scanning**:
       - Agent navigates through multiple pages of search results (configurable).
       - Processes all job cards from each page before moving to the next.

    5. **Daily Profile Booster**:
       - Updates a whitespace/character in your profile headline to shift your candidacy to the top of recruiter searches under the *"Recently Active"* filter.

    ---
    ### 🛡️ Anti-Bot Bypass Techniques
    - Uses your real Chrome profile with saved cookies (persistent session)
    - Organic click navigation (clicks job cards instead of direct URL access)
    - Removes `navigator.webdriver` fingerprint
    - Human-like delays between actions
    - Skips external company sites that break automation
    """)
