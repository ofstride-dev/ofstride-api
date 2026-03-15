import base64
import csv
import json
import os
import sqlite3
import smtplib
import sys
import urllib.error
import urllib.parse
import urllib.request
import requests
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
load_dotenv(API_DIR / ".env")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from new_agent.chart_agent import ChartAgent
from new_agent.chart_tools import overview as chart_overview
DATA_DIR = BASE_DIR / "public" / "data"
DB_FILE = DATA_DIR / "offstride.db"
LEADS_FILE = DATA_DIR / "leads.csv"
CONSULTANTS_FILE = DATA_DIR / "consultants.csv"
NOTIFY_FILE = DATA_DIR / "notifications.csv"
HR_HIRING_FILE = DATA_DIR / "hr_hiring_requests.csv"
HR_CANDIDATE_FILE = DATA_DIR / "hr_candidate_profiles.csv"
UPLOADS_DIR = BASE_DIR / "public" / "uploads" / "hr"

LEAD_PORT = int(os.getenv("LEAD_PORT", "5175"))
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
LEAD_CORS_ORIGINS_RAW = os.getenv("LEAD_CORS_ORIGINS")
if LEAD_CORS_ORIGINS_RAW:
    LEAD_CORS_ORIGINS = [
        origin.strip()
        for origin in LEAD_CORS_ORIGINS_RAW.split(",")
        if origin.strip()
    ]
else:
    LEAD_CORS_ORIGINS = DEFAULT_CORS_ORIGINS
SAARTHI_URL = os.getenv("SAARTHI_URL", "http://127.0.0.1:8001/chat")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", "notifications@ofstride.com")
SMTP_TO = os.getenv("SMTP_TO")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
TWILIO_WHATSAPP_TO = os.getenv("TWILIO_WHATSAPP_TO", "whatsapp:+918951606862")

app = FastAPI(title="Offstride Lead API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=LEAD_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LeadPayload(BaseModel):
    name: str
    phone: str
    location: str
    company: str
    taskSummary: str
    preferredTime: Optional[str] = None
    preferredTimezone: Optional[str] = None


class ConsultantRequest(BaseModel):
    taskSummary: str


class ConsultantInfo(BaseModel):
    name: str
    location: str
    mobile: str
    role: str
    email: str


class NotifyPayload(BaseModel):
    lead: LeadPayload
    consultant: ConsultantInfo


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChartAgentRequest(BaseModel):
    question: str


class HRHiringRequest(BaseModel):
    company: str
    roleTitle: str
    employmentType: str
    workMode: Optional[str] = None
    location: str
    experience: str
    skills: str
    positionsCount: Optional[str] = None
    salaryRange: Optional[str] = None
    urgency: Optional[str] = None
    contractDuration: Optional[str] = None
    officeAddress: Optional[str] = None
    timezone: Optional[str] = None
    contactName: str
    contactEmail: str
    contactPhone: str
    notes: Optional[str] = None


def ensure_file(path: Path, header: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)


def get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                timestamp TEXT,
                name TEXT,
                phone TEXT,
                location TEXT,
                company TEXT,
                task_summary TEXT,
                preferred_time TEXT,
                preferred_timezone TEXT
            );
            CREATE TABLE IF NOT EXISTS consultants (
                name TEXT,
                location TEXT,
                mobile TEXT,
                role TEXT,
                email TEXT
            );
            CREATE TABLE IF NOT EXISTS notifications (
                timestamp TEXT,
                lead_name TEXT,
                lead_phone TEXT,
                consultant_name TEXT,
                consultant_phone TEXT,
                consultant_email TEXT,
                task_summary TEXT,
                preferred_time TEXT,
                preferred_timezone TEXT
            );
            CREATE TABLE IF NOT EXISTS hr_hiring_requests (
                timestamp TEXT,
                company TEXT,
                role_title TEXT,
                employment_type TEXT,
                work_mode TEXT,
                location TEXT,
                experience TEXT,
                skills TEXT,
                positions_count TEXT,
                salary_range TEXT,
                urgency TEXT,
                contract_duration TEXT,
                office_address TEXT,
                timezone TEXT,
                contact_name TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS hr_candidate_profiles (
                timestamp TEXT,
                full_name TEXT,
                email TEXT,
                phone TEXT,
                location TEXT,
                role_interest TEXT,
                experience TEXT,
                skills TEXT,
                linkedin TEXT,
                portfolio TEXT,
                resume_path TEXT
            );
            """
        )


def _table_is_empty(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.execute(f"SELECT COUNT(*) as total FROM {table}")
    row = cursor.fetchone()
    return (row["total"] if row else 0) == 0


def migrate_csv_to_db() -> None:
    normalize_csv_file(
        CONSULTANTS_FILE,
        ["name", "location", "mobile", "role", "email"],
        row_mapper=normalize_consultant_row,
    )
    normalize_csv_file(
        LEADS_FILE,
        [
            "timestamp",
            "name",
            "phone",
            "location",
            "company",
            "task_summary",
            "preferred_time",
            "preferred_timezone",
        ],
    )
    normalize_csv_file(
        NOTIFY_FILE,
        [
            "timestamp",
            "lead_name",
            "lead_phone",
            "consultant_name",
            "consultant_phone",
            "consultant_email",
            "task_summary",
            "preferred_time",
            "preferred_timezone",
        ],
    )
    normalize_csv_file(
        HR_HIRING_FILE,
        [
            "timestamp",
            "company",
            "role_title",
            "employment_type",
            "work_mode",
            "location",
            "experience",
            "skills",
            "positions_count",
            "salary_range",
            "urgency",
            "contract_duration",
            "office_address",
            "timezone",
            "contact_name",
            "contact_email",
            "contact_phone",
            "notes",
        ],
    )
    normalize_csv_file(
        HR_CANDIDATE_FILE,
        [
            "timestamp",
            "full_name",
            "email",
            "phone",
            "location",
            "role_interest",
            "experience",
            "skills",
            "linkedin",
            "portfolio",
            "resume_path",
        ],
    )

    with get_db() as conn:
        if _table_is_empty(conn, "consultants") and CONSULTANTS_FILE.exists():
            with CONSULTANTS_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO consultants (name, location, mobile, role, email)
                    VALUES (:name, :location, :mobile, :role, :email)
                    """,
                    rows,
                )
        if _table_is_empty(conn, "leads") and LEADS_FILE.exists():
            with LEADS_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO leads (timestamp, name, phone, location, company, task_summary, preferred_time, preferred_timezone)
                    VALUES (:timestamp, :name, :phone, :location, :company, :task_summary, :preferred_time, :preferred_timezone)
                    """,
                    rows,
                )
        if _table_is_empty(conn, "notifications") and NOTIFY_FILE.exists():
            with NOTIFY_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO notifications (timestamp, lead_name, lead_phone, consultant_name, consultant_phone, consultant_email, task_summary, preferred_time, preferred_timezone)
                    VALUES (:timestamp, :lead_name, :lead_phone, :consultant_name, :consultant_phone, :consultant_email, :task_summary, :preferred_time, :preferred_timezone)
                    """,
                    rows,
                )
        if _table_is_empty(conn, "hr_hiring_requests") and HR_HIRING_FILE.exists():
            with HR_HIRING_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO hr_hiring_requests (
                        timestamp, company, role_title, employment_type, work_mode, location, experience, skills,
                        positions_count, salary_range, urgency, contract_duration, office_address, timezone,
                        contact_name, contact_email, contact_phone, notes
                    )
                    VALUES (
                        :timestamp, :company, :role_title, :employment_type, :work_mode, :location, :experience, :skills,
                        :positions_count, :salary_range, :urgency, :contract_duration, :office_address, :timezone,
                        :contact_name, :contact_email, :contact_phone, :notes
                    )
                    """,
                    rows,
                )
        if _table_is_empty(conn, "hr_candidate_profiles") and HR_CANDIDATE_FILE.exists():
            with HR_CANDIDATE_FILE.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = [row for row in reader if row]
            if rows:
                conn.executemany(
                    """
                    INSERT INTO hr_candidate_profiles (
                        timestamp, full_name, email, phone, location, role_interest, experience, skills,
                        linkedin, portfolio, resume_path
                    )
                    VALUES (
                        :timestamp, :full_name, :email, :phone, :location, :role_interest, :experience, :skills,
                        :linkedin, :portfolio, :resume_path
                    )
                    """,
                    rows,
                )

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_URL = "https://models.inference.ai.azure.com/chat/completions"
GITHUB_MODEL = "gpt-5.1"

SYSTEM_PROMPT_PATH = API_DIR / "system_prompt.txt"
RESUME_SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

def call_llm(system_prompt: str, user_prompt: str) -> dict:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set in environment")

    headers = {
        "Content-Type": "application/json",
        # ✅ THIS is the important change:
        "api-key": GITHUB_TOKEN,
        # If your account instead expects Authorization, use this instead:
        # "Authorization": GITHUB_TOKEN,
    }

    payload = {
        "model": GITHUB_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    resp = requests.post(GITHUB_API_URL, headers=headers, json=payload, timeout=120)

    # Helpful debug if it fails
    if resp.status_code != 200:
        print("LLM ERROR:", resp.status_code, resp.text)

    resp.raise_for_status()
    data = resp.json()
    return data

import re
from typing import Any, Dict

def extract_json_from_text(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    # remove markdown fences if model adds them
    cleaned = re.sub(r"```json\s*|\s*```", "", text).strip()

    # try direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # fallback: parse the biggest {...} block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(cleaned[start:end+1])
    except Exception:
        return {}
    # Extract JSON safely
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM did not return JSON")

    return json.loads(text[start:end+1])


@app.post("/api/hr/candidate/analyze")
def analyze_candidate_resume(resume: UploadFile = File(...)):
    if not resume.filename:
        raise HTTPException(status_code=400, detail="No resume uploaded")

    content = resume.file.read()

    # Simple text extraction (demo-safe)
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        text = ""

    if len(text.strip()) < 100:
        raise HTTPException(status_code=400, detail="Could not extract enough text from resume")

    user_prompt = f"Analyze this resume thoroughly:\n\n{text[:12000]}"

    try:
        data = call_llm(RESUME_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Extract text from model response
    raw_text = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""

    analysis = extract_json_from_text(raw_text)

# Optional debug (remove later)
    if not analysis:
        print("⚠️ Model returned non-JSON or empty. Raw text (first 500 chars):")
        print(raw_text[:500])

    return {"ok": True, "analysis": analysis}


def normalize_csv_file(path: Path, header: list[str], row_mapper=None) -> None:
    if not path.exists():
        return
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows = list(reader)

    if not rows:
        return

    data_rows = rows[1:] if rows else []
    normalized: list[list[str]] = []

    for row in data_rows:
        if not row or all(not str(item).strip() for item in row):
            continue
        items = [str(item).strip() for item in row]
        if row_mapper:
            items = row_mapper(items)
        if len(items) < len(header):
            items = items + [""] * (len(header) - len(items))
        elif len(items) > len(header):
            items = items[: len(header)]
        normalized.append(items)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(normalized)


def normalize_consultant_row(row: list[str]) -> list[str]:
    if len(row) >= 5:
        return [row[0], row[1], row[2], row[3], ",".join(row[4:]).strip()]
    if len(row) == 4:
        if "@" in row[3]:
            return [row[0], row[1], row[2], "", row[3]]
        return [row[0], row[1], row[2], row[3], ""]
    if len(row) == 3:
        return [row[0], row[1], row[2], "", ""]
    return row


def infer_domain(text: str) -> str:
    value = text.lower()
    if any(word in value for word in ["hire", "hiring", "recruit", "recruitment", "staffing", "candidate"]) or "hr" in value or "human resources" in value or "talent" in value:
        return "hr"
    if "legal" in value or "compliance" in value or "contract" in value:
        return "legal"
    if "finance" in value or "cfo" in value or "tax" in value or "account" in value:
        return "finance"
    if "it" in value or "data" in value or "ai" in value or "cloud" in value:
        return "it"
    return ""


DOMAIN_KEYWORDS = {
    "hr": [
        "hr",
        "human resources",
        "talent",
        "recruitment",
        "recruit",
        "hiring",
        "hire",
        "staffing",
        "payroll",
        "employee",
        "candidate",
    ],
    "legal": ["legal", "compliance", "contract", "policy", "litigation"],
    "finance": ["finance", "financial", "cfo", "tax", "audit", "account"],
    "it": ["it", "data", "ai", "cloud", "software", "infrastructure", "website", "computing"],
}


def load_consultants() -> list[ConsultantInfo]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name, location, mobile, role, email FROM consultants"
        ).fetchall()
    return [
        ConsultantInfo(
            name=row["name"] or "",
            location=row["location"] or "",
            mobile=row["mobile"] or "",
            role=row["role"] or "",
            email=row["email"] or "",
        )
        for row in rows
    ]


def find_best_consultant(task_summary: str) -> Optional[ConsultantInfo]:
    consultants = load_consultants()
    if not consultants:
        return None

    domain = infer_domain(task_summary)
    keywords = DOMAIN_KEYWORDS.get(domain, [])
    summary = task_summary.lower()

    best_score = 0
    best_match: Optional[ConsultantInfo] = None

    for consultant in consultants:
        role = consultant.role.lower()
        email = consultant.email.lower()
        score = 0

        if domain:
            if domain in role or domain in email:
                score += 3

        for keyword in keywords:
            if keyword in summary:
                score += 2
            if keyword in role:
                score += 1
            if keyword in email:
                score += 1

        if score > best_score:
            best_score = score
            best_match = consultant

    if best_score == 0:
        if domain:
            fallback = next(
                (
                    consultant
                    for consultant in consultants
                    if domain in consultant.role.lower() or domain in consultant.email.lower()
                ),
                None,
            )
            return fallback
        fallback = next(
            (
                consultant
                for consultant in consultants
                if any(key in consultant.role.lower() or key in consultant.email.lower() for key in ["hr", "legal", "finance", "it"])
            ),
            None,
        )
        return fallback
    return best_match


@app.on_event("startup")
def normalize_csv_files() -> None:
    init_db()
    migrate_csv_to_db()


def _send_email(subject: str, body: str, recipients: Optional[list[str]] = None) -> str:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return "skipped"
    recipient_list = [r for r in (recipients or []) if r]
    if SMTP_TO:
        recipient_list.append(SMTP_TO)
    recipient_list = sorted(set(recipient_list))
    if not recipient_list:
        return "skipped"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = ", ".join(recipient_list)
    message.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(message)
        return "sent"
    except Exception:
        return "error"


def _send_whatsapp(message: str) -> str:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        return "skipped"
    auth = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode("utf-8")
    headers = {
        "Authorization": f"Basic {base64.b64encode(auth).decode('utf-8')}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = urllib.parse.urlencode(
        {
            "From": TWILIO_WHATSAPP_FROM,
            "To": TWILIO_WHATSAPP_TO,
            "Body": message,
        }
    ).encode("utf-8")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20):
            return "sent"
    except Exception:
        return "error"


@app.post("/api/leads")
def create_lead(payload: LeadPayload):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO leads (
                timestamp, name, phone, location, company, task_summary, preferred_time, preferred_timezone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                payload.name.strip(),
                payload.phone.strip(),
                payload.location.strip(),
                payload.company.strip(),
                payload.taskSummary.strip(),
                (payload.preferredTime or "").strip(),
                (payload.preferredTimezone or "").strip(),
            ),
        )

    return {"ok": True}


@app.post("/api/consultant")
def get_consultant(payload: ConsultantRequest):
    consultant = find_best_consultant(payload.taskSummary)
    if not consultant:
        raise HTTPException(status_code=404, detail="No consultant found")
    return {"consultant": consultant}


@app.post("/api/notify")
def log_notification(payload: NotifyPayload):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO notifications (
                timestamp, lead_name, lead_phone, consultant_name, consultant_phone, consultant_email,
                task_summary, preferred_time, preferred_timezone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                payload.lead.name.strip(),
                payload.lead.phone.strip(),
                payload.consultant.name.strip(),
                payload.consultant.mobile.strip(),
                payload.consultant.email.strip(),
                payload.lead.taskSummary.strip(),
                (payload.lead.preferredTime or "").strip(),
                (payload.lead.preferredTimezone or "").strip(),
            ),
        )

    email_status = _send_email(
        "New Offstride consultation request",
        (
            f"Lead: {payload.lead.name}\n"
            f"Phone: {payload.lead.phone}\n"
            f"Location: {payload.lead.location}\n"
            f"Company: {payload.lead.company}\n"
            f"Task: {payload.lead.taskSummary}\n"
            f"Preferred time: {payload.lead.preferredTime or '-'} {payload.lead.preferredTimezone or ''}\n\n"
            f"Consultant: {payload.consultant.name} ({payload.consultant.role})\n"
            f"Consultant phone: {payload.consultant.mobile}\n"
            f"Consultant email: {payload.consultant.email}"
        ),
        recipients=[payload.consultant.email],
    )
    whatsapp_status = _send_whatsapp(
        (
            f"New consultation request\n"
            f"Lead: {payload.lead.name}\n"
            f"Phone: {payload.lead.phone}\n"
            f"Company: {payload.lead.company}\n"
            f"Task: {payload.lead.taskSummary}\n"
            f"Consultant: {payload.consultant.name} ({payload.consultant.role})"
        )
    )

    return {"ok": True, "email": email_status, "whatsapp": whatsapp_status}


@app.post("/api/hr/hiring")
def create_hr_hiring(payload: HRHiringRequest):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO hr_hiring_requests (
                timestamp, company, role_title, employment_type, work_mode, location, experience, skills,
                positions_count, salary_range, urgency, contract_duration, office_address, timezone,
                contact_name, contact_email, contact_phone, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                payload.company.strip(),
                payload.roleTitle.strip(),
                payload.employmentType.strip(),
                (payload.workMode or "").strip(),
                payload.location.strip(),
                payload.experience.strip(),
                payload.skills.strip(),
                (payload.positionsCount or "").strip(),
                (payload.salaryRange or "").strip(),
                (payload.urgency or "").strip(),
                (payload.contractDuration or "").strip(),
                (payload.officeAddress or "").strip(),
                (payload.timezone or "").strip(),
                payload.contactName.strip(),
                payload.contactEmail.strip(),
                payload.contactPhone.strip(),
                (payload.notes or "").strip(),
            ),
        )

    return {"ok": True}


@app.post("/api/hr/candidate")
def create_hr_candidate(
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    location: str = Form(...),
    role_interest: str = Form(...),
    experience: str = Form(...),
    skills: str = Form(...),
    linkedin: Optional[str] = Form(None),
    portfolio: Optional[str] = Form(None),
    resume: Optional[UploadFile] = File(None),
):
    resume_path = ""
    if resume and resume.filename:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = Path(resume.filename).name
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        saved_name = f"{timestamp}_{safe_name}"
        target = UPLOADS_DIR / saved_name
        with target.open("wb") as handle:
            handle.write(resume.file.read())
        resume_path = f"/uploads/hr/{saved_name}"

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO hr_candidate_profiles (
                timestamp, full_name, email, phone, location, role_interest, experience, skills,
                linkedin, portfolio, resume_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                full_name.strip(),
                email.strip(),
                phone.strip(),
                location.strip(),
                role_interest.strip(),
                experience.strip(),
                skills.strip(),
                (linkedin or "").strip(),
                (portfolio or "").strip(),
                resume_path,
            ),
        )

    return {"ok": True, "resumePath": resume_path}


@app.post("/api/chat")
def chat_with_saarthi(payload: ChatRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    body = json.dumps(
        {
            "message": message,
            "session_id": payload.session_id or "default",
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        SAARTHI_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Saarthi error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="Saarthi service unreachable") from exc

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Invalid Saarthi response") from exc

    text = (
        data.get("text")
        or data.get("answer")
        or data.get("response")
        or "Sorry, I couldn't find an answer."
    )
    return {"text": text}


@app.get("/api/charts/overview")
def get_charts_overview():
    return chart_overview()


@app.post("/api/charts/agent")
def chart_agent_answer(payload: ChartAgentRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    agent = ChartAgent()
    response = agent.answer(question)
    return {
        "text": response.text,
        "tools_used": response.tools_used,
        "data": response.data,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=LEAD_PORT)
