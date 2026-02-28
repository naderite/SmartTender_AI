import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader


SKILL_CATALOG = {
    "python": ["python"],
    "java": ["java"],
    "javascript": ["javascript", "js"],
    "typescript": ["typescript", "ts"],
    "react": ["react"],
    "angular": ["angular"],
    "node.js": ["node.js", "nodejs", "node js"],
    "fastapi": ["fastapi"],
    "flask": ["flask"],
    "django": ["django"],
    "spring boot": ["spring boot"],
    "sql": ["sql", "postgresql", "mysql", "sqlite"],
    "mongodb": ["mongodb"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "git": ["git", "github", "gitlab"],
    "linux": ["linux"],
    "aws": ["aws"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"],
    "data analysis": ["data analysis", "analytics"],
    "power bi": ["power bi", "powerbi"],
    "excel": ["excel"],
    "scrum": ["scrum"],
    "agile": ["agile"],
    "devops": ["devops"],
    "ci/cd": ["ci/cd", "ci cd", "jenkins", "github actions"],
}

LANGUAGE_CATALOG = {
    "english": ["english", "anglais"],
    "french": ["french", "francais", "français"],
    "arabic": ["arabic", "arabe"],
    "german": ["german", "allemand"],
    "spanish": ["spanish", "espagnol"],
}

EDUCATION_KEYWORDS = {
    "phd": ["phd", "doctorate"],
    "master": ["master", "msc", "engineer", "ingénieur", "ingenieur"],
    "bachelor": ["bachelor", "licence", "bsc"],
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "have",
    "will",
    "your",
    "into",
    "their",
    "need",
    "must",
    "using",
    "about",
    "able",
    "more",
    "plus",
    "des",
    "les",
    "une",
    "pour",
    "avec",
    "dans",
    "sur",
    "aux",
    "par",
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    return value.strip("-") or "file"


def file_sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    return file_path.read_text(encoding="utf-8-sig", errors="ignore").strip()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_email(text: str) -> str:
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    return match.group(0) if match else ""


def extract_phone(text: str) -> str:
    match = re.search(r"(\+?\d[\d\s().-]{7,}\d)", text)
    return normalize_space(match.group(1)) if match else ""


def extract_links(text: str) -> dict[str, str]:
    links = {"linkedin": "", "github": "", "portfolio": ""}
    patterns = {
        "linkedin": r"https?://(?:www\.)?linkedin\.com/[^\s]+",
        "github": r"https?://(?:www\.)?github\.com/[^\s]+",
        "portfolio": r"https?://[^\s]+",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            links[key] = match.group(0)
    return links


def detect_skills(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for skill, aliases in SKILL_CATALOG.items():
        for alias in aliases:
            pattern = r"(?<!\w)" + re.escape(alias.lower()) + r"(?!\w)"
            if re.search(pattern, lowered):
                found.append(skill)
                break
    return sorted(set(found))


def detect_languages(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    results = []
    for language, aliases in LANGUAGE_CATALOG.items():
        if any(alias in lowered for alias in aliases):
            results.append({"name": language.title(), "proficiency": None})
    return results


def detect_education_level(text: str) -> str:
    lowered = text.lower()
    for level, aliases in EDUCATION_KEYWORDS.items():
        if any(alias in lowered for alias in aliases):
            return level
    return ""


def estimate_cv_experience_years(text: str) -> int:
    years = sorted({int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", text)})
    current_year = datetime.now().year
    valid_years = [year for year in years if 1980 <= year <= current_year]
    if len(valid_years) >= 2:
        return max(0, min(current_year - min(valid_years), 25))
    if len(valid_years) == 1:
        return max(1, min(current_year - valid_years[0], 25))
    explicit = re.findall(r"(\d+)\+?\s*(?:years|year|ans|an)\b", text, re.I)
    return int(explicit[0]) if explicit else 0


def estimate_required_experience(text: str) -> int:
    matches = re.findall(r"(\d+)\+?\s*(?:years|year|ans|an)\b", text, re.I)
    if matches:
        return max(int(match) for match in matches)
    return 0


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z+#/. -]{2,}", text.lower())
    cleaned = []
    for token in tokens:
        token = token.strip(" .-/")
        if len(token) < 3 or token in STOPWORDS:
            continue
        cleaned.append(token)
    return [word for word, _ in Counter(cleaned).most_common(limit)]


def parse_cv_text(text: str, source_name: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    full_name = ""
    for line in lines[:6]:
        if "@" in line or len(line.split()) < 2 or len(line) > 60:
            continue
        if re.search(r"\d", line):
            continue
        full_name = line.title()
        break

    technical_skills = detect_skills(text)
    languages = detect_languages(text)
    education_level = detect_education_level(text)
    experience_years = estimate_cv_experience_years(text)
    links = extract_links(text)
    summary = normalize_space(" ".join(lines[:5]))[:300]

    work_experience = []
    if experience_years:
        work_experience.append(
            {
                "job_title": "",
                "company": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "responsibilities": [],
                "achievements": [],
                "estimated_years": experience_years,
            }
        )

    education = []
    if education_level:
        education.append(
            {
                "degree": education_level,
                "field_of_study": "",
                "school": "",
                "location": "",
                "start_year": "",
                "end_year": "",
                "gpa": None,
            }
        )

    return {
        "source_file": source_name,
        "personal_information": {
            "full_name": full_name or Path(source_name).stem.replace("-", " ").title(),
            "email": extract_email(text),
            "phone": extract_phone(text),
        },
        "website_and_social_links": links,
        "professional_summary": summary,
        "work_experience": work_experience,
        "education": education,
        "certification": [],
        "awards_and_achievements": [],
        "projects": [],
        "skills_and_interests": {
            "technical_skills": technical_skills,
            "soft_skills": [],
            "languages": languages,
            "hobbies_and_interests": [],
        },
        "volunteering": [],
        "publications": [],
        "metadata": {
            "experience_years": experience_years,
            "education_level": education_level,
            "keywords": extract_keywords(text),
        },
    }


def parse_tender_text(text: str, source_name: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0] if lines else Path(source_name).stem.replace("-", " ").title()
    required_skills = detect_skills(text)
    languages = [item["name"] for item in detect_languages(text)]
    education_level = detect_education_level(text)

    return {
        "source_file": source_name,
        "title": title,
        "required_skills": required_skills,
        "preferred_skills": [],
        "experience_level": estimate_required_experience(text),
        "languages": languages,
        "education_level": education_level,
        "keywords": extract_keywords(text),
        "summary": normalize_space(" ".join(lines[:8]))[:500],
    }


def build_cv_search_text(cv_json: dict[str, Any], raw_text: str) -> str:
    parts = [
        cv_json["personal_information"]["full_name"],
        cv_json.get("professional_summary", ""),
        " ".join(cv_json.get("skills_and_interests", {}).get("technical_skills", [])),
        " ".join(item.get("name", "") for item in cv_json.get("skills_and_interests", {}).get("languages", [])),
        " ".join(cv_json.get("metadata", {}).get("keywords", [])),
        raw_text[:3000],
    ]
    return normalize_space(" ".join(part for part in parts if part))


def build_tender_search_text(tender_json: dict[str, Any], raw_text: str) -> str:
    parts = [
        tender_json["title"],
        tender_json.get("summary", ""),
        " ".join(tender_json.get("required_skills", [])),
        " ".join(tender_json.get("languages", [])),
        " ".join(tender_json.get("keywords", [])),
        raw_text[:3000],
    ]
    return normalize_space(" ".join(part for part in parts if part))


def write_json(payload: dict[str, Any], target_path: Path) -> None:
    target_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
