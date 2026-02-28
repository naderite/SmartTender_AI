import os
from pathlib import Path

from dotenv import load_dotenv


APP_DIR = Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


DATA_DIR = APP_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
CV_BANK_DIR = DATA_DIR / "cv_bank"
TENDER_BANK_DIR = DATA_DIR / "tender_bank"
PARSED_CVS_DIR = DATA_DIR / "parsed" / "cvs"
PARSED_TENDERS_DIR = DATA_DIR / "parsed" / "tenders"
REPORTS_DIR = DATA_DIR / "generated"
CHROMA_DIR = DATA_DIR / "chroma"
DB_PATH = DATA_DIR / "smarttender.db"
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

OPTIONAL_KEYS = {
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
    "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", ""),
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY", ""),
}

SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "10"))
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

for directory in [
    UPLOADS_DIR,
    CV_BANK_DIR,
    TENDER_BANK_DIR,
    PARSED_CVS_DIR,
    PARSED_TENDERS_DIR,
    REPORTS_DIR,
    CHROMA_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)
