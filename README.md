# 💼 Naukri.com ("Novkaari") Auto-Apply & Profile Booster Agent

An intelligent, automated job search, application, and profile optimization agent built for **Naukri.com**. It automates searching for relevant listings, applying to jobs, answering recruiter screening questions (via rule-matching + Gemini AI), logging applications to a local SQLite database, and boosting profile visibility.

---

## 🔥 Key Features

- **Automated Web Search & Apply**: Searches Naukri based on keywords, locations, experience level, salary range, and posting freshness.
- **Smart Recruiter Question Solver**: Automates single/multi-choice radio options, dropdowns, and text questions (Notice period, CTC, experience, relocation, etc.) with optional Gemini AI fallback.
- **Profile Ranking Booster**: Periodically updates your profile headline to bump your candidacy to the top of recruiter searches ("Recently Updated" filter).
- **SQLite Tracker & CSV Exporter**: Prevents duplicate applications and tracks applied jobs with dates, status, company name, and job links.
- **Interactive Web Dashboard**: Streamlit-powered Web UI to adjust filters, monitor live execution logs, view application metrics, and download CSV reports.
- **Persistent Session**: Keeps browser cookies saved locally so you don't need to log in repeatedly or deal with OTP every time.

---

## 🛠️ Setup Instructions

### 1. Install Dependencies
Open PowerShell or Command Prompt in this folder and run:
```bash
pip install -r requirements.txt
```

### 2. Install Playwright Browsers
```bash
playwright install chromium
```

---

## 🚀 Running the Application

### Option A: Web Dashboard (Recommended)
Run the Streamlit Control Panel:
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

From the dashboard:
1. Configure your target job titles, locations, CTC, notice period, and profile details in the sidebar.
2. Click **💾 Save Settings**.
3. Click **🚀 Launch Auto-Apply Agent** or **⚡ Run Profile Booster**.

---

### Option B: Command Line (CLI)
To run the auto-apply agent directly from the terminal:
```bash
python naukri_agent.py
```

To run the profile booster directly from the terminal:
```bash
python profile_booster.py
```

---

## 📂 Project Structure

```
├── app.py                # Streamlit Web UI Dashboard & Control Panel
├── naukri_agent.py       # Core Playwright automation & job apply engine
├── profile_booster.py    # Naukri search rank refresher module
├── ai_solver.py          # Rule-based & Gemini AI question-answering solver
├── config.py             # Settings persistence & config manager
├── db_logger.py          # SQLite database logger for job history
├── settings.json         # User settings storage file
├── naukri_jobs.db        # SQLite database storing application history
└── requirements.txt      # Python dependencies
```

---

## 🔒 Security & Privacy Notice
All login session data and cookies are stored locally in the `naukri_browser_session/` directory on your machine. Your credentials and personal data are never sent to any external server (except Gemini API if you choose to enable AI question answering).
