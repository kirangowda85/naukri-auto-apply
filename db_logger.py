import sqlite3
import os
import json
import re
from datetime import datetime, date
from difflib import SequenceMatcher
import pandas as pd
from typing import Dict, Any, List, Optional

DB_FILE = os.path.join(os.path.dirname(__file__), "naukri_jobs.db")

class DatabaseLogger:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applied_jobs (
                    job_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT,
                    location TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    url TEXT,
                    status TEXT,
                    notes TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS qna_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_key TEXT UNIQUE NOT NULL,
                    original_question TEXT NOT NULL,
                    options_json TEXT,
                    answer TEXT NOT NULL,
                    source TEXT DEFAULT 'gemini',
                    use_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    @staticmethod
    def normalize_question_key(question_text: str) -> str:
        """Normalize question text to generate a clean comparison key."""
        text = question_text.lower().strip()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return re.sub(r'\s+', ' ', text)

    def is_already_applied(self, job_id: str) -> bool:
        """Check if job_id was already successfully applied in applied_jobs table."""
        if not job_id:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM applied_jobs WHERE job_id = ? AND status IN ('applied', 'already_applied')", (job_id,))
            return cursor.fetchone() is not None

    def clear_failed_history(self) -> int:
        """Clear past failed application attempts so they can be retried."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM applied_jobs WHERE status LIKE 'failed%'")
            conn.commit()
            return cursor.rowcount

    def log_application(self, job_id: str, title: str, company: str, location: str, url: str, status: str, notes: str = ""):
        """Record an application attempt."""
        applied_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO applied_jobs (job_id, title, company, location, applied_at, url, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (job_id, title, company, location, applied_at, url, status, notes))
            conn.commit()

    def get_applied_jobs(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Return list of applied jobs sorted by date descending."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM applied_jobs ORDER BY applied_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_applied_jobs_df(self) -> pd.DataFrame:
        """Return dataframe of applied jobs for reporting."""
        with self._get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM applied_jobs ORDER BY applied_at DESC", conn)

    # --- Self-Learning Q&A Memory Engine Methods ---

    def get_learned_answer(self, question_text: str, options: Optional[List[str]] = None) -> Optional[str]:
        """Check SQLite qna_memory for exact or fuzzy match. If found, increment use_count and return answer."""
        if not question_text or not question_text.strip():
            return None

        q_key = self.normalize_question_key(question_text)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Exact Key Search
            cursor.execute("SELECT id, answer, options_json FROM qna_memory WHERE question_key = ?", (q_key,))
            row = cursor.fetchone()

            if not row:
                # 2. Fuzzy similarity search over all learned questions
                cursor.execute("SELECT id, question_key, original_question, answer, options_json FROM qna_memory")
                all_rows = cursor.fetchall()
                best_match = None
                best_score = 0.0

                for r in all_rows:
                    score = SequenceMatcher(None, q_key, r["question_key"]).ratio()
                    if score > best_score and score >= 0.82:
                        best_score = score
                        best_match = r

                if best_match:
                    row = best_match

            if row:
                qna_id = row["id"]
                saved_answer = row["answer"]

                # If options list provided, match against closest option if needed
                matched_final_ans = saved_answer
                if options:
                    for opt in options:
                        if saved_answer.lower() == opt.lower() or saved_answer.lower() in opt.lower() or opt.lower() in saved_answer.lower():
                            matched_final_ans = opt
                            break

                # Increment usage counter
                cursor.execute("""
                    UPDATE qna_memory 
                    SET use_count = use_count + 1, updated_at = ?
                    WHERE id = ?
                """, (now_str, qna_id))
                conn.commit()
                return matched_final_ans

        return None

    def save_learned_answer(self, question_text: str, answer: str, options: Optional[List[str]] = None, source: str = "gemini") -> bool:
        """Save a new question & answer pair into qna_memory database for future zero-API reuse."""
        if not question_text or not answer:
            return False

        q_key = self.normalize_question_key(question_text)
        if not q_key:
            return False

        options_json = json.dumps(options) if options else None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO qna_memory (question_key, original_question, options_json, answer, source, use_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(question_key) DO UPDATE SET
                        answer = excluded.answer,
                        options_json = COALESCE(excluded.options_json, qna_memory.options_json),
                        source = excluded.source,
                        updated_at = excluded.updated_at
                """, (q_key, question_text.strip(), options_json, answer.strip(), source, now_str, now_str))
                conn.commit()
                return True
        except Exception as e:
            print(f"[DatabaseLogger] Error saving Q&A memory: {e}")
            return False

    def get_all_learned_qna(self) -> List[Dict[str, Any]]:
        """Fetch all stored Q&A memory items."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM qna_memory ORDER BY use_count DESC, updated_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    def delete_learned_qna(self, qna_id: int) -> bool:
        """Delete a learned Q&A pair from memory."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM qna_memory WHERE id = ?", (qna_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_qna_stats(self) -> Dict[str, int]:
        """Return memory statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(use_count) FROM qna_memory")
            row = cursor.fetchone()
            total_learned = row[0] or 0
            total_uses = row[1] or 0
            # Calls saved are total uses minus initial learning calls
            api_calls_saved = max(0, total_uses - total_learned)
            return {
                "total_learned": total_learned,
                "total_uses": total_uses,
                "api_calls_saved": api_calls_saved
            }

    def get_stats(self) -> Dict[str, int]:
        """Get summary metrics for dashboard."""
        today_str = date.today().strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM applied_jobs WHERE status = 'applied'")
            total_applied = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM applied_jobs WHERE status = 'applied' AND DATE(applied_at) = ?", (today_str,))
            today_applied = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM applied_jobs WHERE status LIKE 'failed%'")
            total_failed = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM applied_jobs")
            total_tracked = cursor.fetchone()[0] or 0

            qna_stats = self.get_qna_stats()

            return {
                "total_applied": total_applied,
                "today_applied": today_applied,
                "total_failed": total_failed,
                "total_tracked": total_tracked,
                "total_learned_qna": qna_stats["total_learned"],
                "api_calls_saved": qna_stats["api_calls_saved"]
            }

    def export_csv(self, output_path: str = "applied_jobs_export.csv") -> str:
        """Export job application records to CSV file."""
        with self._get_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM applied_jobs ORDER BY applied_at DESC", conn)
            df.to_csv(output_path, index=False)
            return output_path

if __name__ == "__main__":
    logger = DatabaseLogger()
    print("Database initialized. Stats:", logger.get_stats())

