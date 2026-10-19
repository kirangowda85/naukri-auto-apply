import os
import json
from typing import List, Dict, Any

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "keywords": ["Python Developer", "Software Engineer", "Backend Developer"],
    "locations": ["Bengaluru", "Remote", "Hyderabad", "Pune"],
    "min_experience": 1,
    "max_experience": 5,
    "min_salary": 6,  # in LPA
    "freshness_days": 7,  # jobs posted in last N days
    
    # Applicant details for screening questions
    "total_experience_years": 3.0,
    "current_ctc_lakhs": 10.0,
    "expected_ctc_lakhs": 15.0,
    "notice_period_days": 30,  # e.g., 0 for immediate, 15, 30, 60, 90
    "current_location": "Bengaluru",
    "willing_to_relocate": True,
    "skills": ["Python", "FastAPI", "Django", "SQL", "REST API", "Docker"],
    "education": "B.Tech in Computer Science",
    "gender": "Male",
    "portfolio_url": "",
    "linkedin_url": "",
    "preferred_work_mode": "Hybrid",
    "resume_path": "",
    "resume_filename": "",
    "headline": "Experienced Python & Backend Developer | FastAPI, Django, PostgreSQL & Cloud Infrastructure",
    
    "naukri_email": "",
    "naukri_password": "",
    "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
    # What-to-Apply Filtering & Scoring Criteria
    "negative_keywords": ["Internship", "Intern", "Non-tech", "Trainer", "Sales", "Telecaller", "Technical Support"],
    "blacklisted_companies": [],
    "min_match_score": 35,  # Minimum percentage match between job and profile/keywords
    "strict_experience_filter": True,  # Verify job card exp range matches candidate min/max
    "max_search_pages": 3,  # Number of search result pages to scan per keyword/location
    "max_applications_per_run": 20,
    "headless": False,  # Run in visible mode by default to observe or handle initial OTP
    "user_data_dir": os.path.join(os.path.expanduser("~"), ".naukri_browser_profile"),
    "apply_mode": "easy_apply_only",  # "easy_apply_only" or "all"
}

class ConfigManager:
    """Manages application settings with persistent JSON storage."""

    @staticmethod
    def load_config() -> Dict[str, Any]:
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved_config = json.load(f)
                    config.update(saved_config)
            except Exception as e:
                print(f"Error loading {SETTINGS_FILE}: {e}. Using default config.")

        # On cloud environments (e.g. Streamlit Cloud / Linux without display), default to headless mode
        if os.name != "nt" and not os.environ.get("DISPLAY"):
            config["headless"] = True

        # Support Streamlit Cloud Secrets (st.secrets)
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                for sec_k in ["naukri_email", "naukri_password", "gemini_api_key"]:
                    if sec_k in st.secrets:
                        config[sec_k] = st.secrets[sec_k]
        except Exception:
            pass

        return config

    @staticmethod
    def save_config(config: Dict[str, Any]) -> bool:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving {SETTINGS_FILE}: {e}")
            return False

# Quick test
if __name__ == "__main__":
    cfg = ConfigManager.load_config()
    print("Loaded config:", cfg)
