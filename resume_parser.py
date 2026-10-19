import os
import re
import json
from typing import Dict, Any, List, Optional, Tuple

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class ResumeParser:
    """Parses PDF, DOCX, and TXT resume files into structured candidate profile attributes."""

    COMMON_SKILLS = [
        "python", "java", "c++", "c#", "javascript", "typescript", "react", "angular", "vue", "node.js",
        "express", "fastapi", "django", "flask", "spring boot", "html", "css", "sql", "postgresql",
        "mysql", "mongodb", "redis", "docker", "kubernetes", "aws", "azure", "gcp", "git", "ci/cd",
        "rest api", "graphql", "microservices", "pandas", "numpy", "scikit-learn", "tensorflow",
        "pytorch", "machine learning", "data science", "devops", "selenium", "playwright", "qa"
    ]

    def __init__(self, api_key: str = ""):
        self.api_key = api_key.strip()
        self.client = None
        if HAS_GENAI and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[ResumeParser] Gemini client init error: {e}")

    def extract_text_from_file(self, file_path_or_bytes: Any, filename: str) -> str:
        """Extract plain text from PDF, DOCX, or TXT file."""
        ext = os.path.splitext(filename)[1].lower()
        extracted_text = ""

        try:
            if ext == ".pdf":
                if HAS_PYPDF:
                    reader = PdfReader(file_path_or_bytes)
                    for page in reader.pages:
                        t = page.extract_text()
                        if t:
                            extracted_text += t + "\n"
                else:
                    extracted_text = "[PDF parser not available]"

            elif ext in [".docx", ".doc"]:
                if HAS_DOCX:
                    doc = docx.Document(file_path_or_bytes)
                    full_text = []
                    for para in doc.paragraphs:
                        full_text.append(para.text)
                    extracted_text = "\n".join(full_text)
                else:
                    extracted_text = "[DOCX parser not available]"

            else:
                # Text / Plain file
                if isinstance(file_path_or_bytes, bytes):
                    extracted_text = file_path_or_bytes.decode("utf-8", errors="ignore")
                elif hasattr(file_path_or_bytes, "read"):
                    extracted_text = file_path_or_bytes.read().decode("utf-8", errors="ignore")
                elif isinstance(file_path_or_bytes, str) and os.path.exists(file_path_or_bytes):
                    with open(file_path_or_bytes, "r", encoding="utf-8", errors="ignore") as f:
                        extracted_text = f.read()

        except Exception as e:
            print(f"[ResumeParser] Error reading {filename}: {e}")

        return extracted_text.strip()

    def parse_with_rules(self, text: str) -> Dict[str, Any]:
        """Rule-based extraction of candidate details using Regex & heuristics."""
        res: Dict[str, Any] = {}

        # Email
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        if email_match:
            res["email"] = email_match.group(0)

        # Phone
        phone_match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
        if phone_match:
            res["phone"] = phone_match.group(0)

        # Total Experience Years
        exp_match = re.search(r'(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b(?:\s*of)?\s*exp', text, re.IGNORECASE)
        if exp_match:
            try:
                res["total_experience_years"] = float(exp_match.group(1))
            except ValueError:
                pass
        else:
            # Fallback: search for numbers followed by years
            gen_exp = re.search(r'(\d{1,2})\+?\s*(?:years|yrs)\b', text, re.IGNORECASE)
            if gen_exp:
                try:
                    res["total_experience_years"] = float(gen_exp.group(1))
                except ValueError:
                    pass

        # Key Skills
        lower_text = text.lower()
        found_skills = [skill for skill in self.COMMON_SKILLS if re.search(rf'\b{re.escape(skill)}\b', lower_text)]
        if found_skills:
            # Capitalize nicely
            formatted_skills = [s.title() if s not in ["sql", "aws", "gcp", "qa", "html", "css", "ci/cd", "rest api", "graphql"] else s.upper() for s in found_skills]
            res["skills"] = formatted_skills[:12]

        # Suggested job keywords
        top_skills = found_skills[:3]
        if top_skills:
            kw_suggestions = [f"{s.title()} Developer" for s in top_skills]
            res["suggested_keywords"] = kw_suggestions

        # Degree / Education
        degree_patterns = [
            r'\bB\.?E\.?\b|\bB\.?Tech\b|\bBachelor of Technology\b|\bBachelor of Engineering\b',
            r'\bM\.?Tech\b|\bMaster of Technology\b',
            r'\bB\.?S\.?\b|\bBachelor of Science\b',
            r'\bM\.?S\.?\b|\bMaster of Science\b',
            r'\bM\.?C\.?A\.?\b|\bMaster of Computer Applications\b',
            r'\bB\.?C\.?A\.?\b|\bBachelor of Computer Applications\b'
        ]
        for pat in degree_patterns:
            deg_match = re.search(pat, text, re.IGNORECASE)
            if deg_match:
                res["education"] = deg_match.group(0)
                break

        # Resume headline: Build professional role + skills headline (avoid phone/email contact info)
        top_skill_str = ", ".join(res.get("skills", [])[:4]) if res.get("skills") else "Python, Backend Development"
        role_label = res.get("suggested_keywords", ["Software Engineer"])[0] if res.get("suggested_keywords") else "Software Engineer"
        exp_yrs = res.get("total_experience_years")
        exp_str = f"{int(exp_yrs) if exp_yrs and float(exp_yrs).is_integer() else exp_yrs} Yrs Exp" if exp_yrs is not None else "Entry Level"
        res["headline"] = f"{role_label} | {top_skill_str} | {exp_str}"

        return res

    def parse_with_gemini(self, text: str) -> Optional[Dict[str, Any]]:
        """AI-powered structured resume parsing using Gemini LLM."""
        if not self.client or not text:
            return None

        prompt = f"""
Analyze the following resume text and extract candidate profile details into a JSON object:
Resume Text:
\"\"\"
{text[:4000]}
\"\"\"

Return ONLY a valid JSON object with the following exact keys:
- "name": String (full candidate name if found, else empty)
- "email": String
- "phone": String
- "total_experience_years": Number (float, e.g. 3.5)
- "headline": String (Concise 1-sentence professional resume headline for Naukri, e.g. "Software Engineer | Python, React, SQL")
- "skills": Array of Strings (e.g. ["Python", "FastAPI", "Docker", "SQL"])
- "suggested_keywords": Array of Strings (3-4 job title search terms like ["Python Developer", "Backend Engineer"])
- "education": String (e.g. "B.Tech in Computer Science")
- "current_location": String (city if mentioned)
- "notice_period_days": Number or null (if notice period is mentioned, e.g. 30, 0 for immediate)
- "current_ctc_lakhs": Number or null
- "expected_ctc_lakhs": Number or null

Respond ONLY with valid JSON. Do not include markdown code block syntax.
"""
        for model_name in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                raw_ans = response.text.strip()
                raw_ans = re.sub(r'^```json\s*|^```\s*|\s*```$', '', raw_ans, flags=re.MULTILINE).strip()
                data = json.loads(raw_ans)
                if data:
                    return data
            except Exception as e:
                continue
        return None

    def parse_resume(self, file_path_or_bytes: Any, filename: str) -> Tuple[Dict[str, Any], str]:
        """Main entry point to parse a resume file. Returns (parsed_profile_dict, extracted_raw_text)."""
        raw_text = self.extract_text_from_file(file_path_or_bytes, filename)
        if not raw_text or raw_text.startswith("["):
            return {}, raw_text

        # 1. Rule-based extraction
        profile_data = self.parse_with_rules(raw_text)

        # 2. Upgrade with Gemini if available
        if self.client:
            ai_data = self.parse_with_gemini(raw_text)
            if ai_data:
                # Merge AI data over rule data where non-empty
                for key, val in ai_data.items():
                    if val is not None and val != "" and val != []:
                        profile_data[key] = val

        return profile_data, raw_text
