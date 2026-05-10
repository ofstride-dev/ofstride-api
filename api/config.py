from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parent
load_dotenv(API_DIR / ".env")

BASE_DIR = API_DIR.parent

DATA_DIR = BASE_DIR / "public" / "data"
UPLOADS_DIR = BASE_DIR / "public" / "uploads" / "hr"

DB_FILE = DATA_DIR / "offstride.db"
LEADS_FILE = DATA_DIR / "leads.csv"
CONSULTANTS_FILE = DATA_DIR / "consultants.csv"
NOTIFY_FILE = DATA_DIR / "notifications.csv"
HR_HIRING_FILE = DATA_DIR / "hr_hiring_requests.csv"
HR_CANDIDATE_FILE = DATA_DIR / "hr_candidate_profiles.csv"

LEAD_PORT = int(os.getenv("LEAD_PORT", "5175"))

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

LEAD_CORS_ORIGINS_RAW = os.getenv("LEAD_CORS_ORIGINS")


def get_cors_origins() -> List[str]:
    if LEAD_CORS_ORIGINS_RAW:
        return [o.strip() for o in LEAD_CORS_ORIGINS_RAW.split(",") if o.strip()]
    return DEFAULT_CORS_ORIGINS


SAARTHI_URL = os.getenv("SAARTHI_URL", "http://127.0.0.1:8001/chat")
SAARTHI_CHART_URL = os.getenv("SAARTHI_CHART_URL", "http://127.0.0.1:8001/chart")

# ── Resend ─────────────────────────────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Ofstride <notifications@ofstride.com>")
EMAIL_TO = os.getenv("EMAIL_TO", "info@ofstride.com")

# ── Twilio WhatsApp (optional) ─────────────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
TWILIO_WHATSAPP_TO = os.getenv("TWILIO_WHATSAPP_TO", "whatsapp:+918951606862")

# ── GitHub Models / LLM ───────────────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://models.inference.ai.azure.com/chat/completions")
GITHUB_MODEL = os.getenv("GITHUB_MODEL", "gpt-5.1")

SYSTEM_PROMPT_PATH = API_DIR / "system_prompt.txt"
RESUME_SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8") if SYSTEM_PROMPT_PATH.exists() else ""
