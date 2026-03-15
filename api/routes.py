from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .config import RESUME_SYSTEM_PROMPT, UPLOADS_DIR
from .db import get_db, init_db, migrate_csv_to_db
from .models import (
    ChartAgentRequest,
    ChatRequest,
    ConsultantInfo,
    ConsultantRequest,
    HRHiringRequest,
    LeadPayload,
    NotifyPayload,
)
from .services import (
    call_llm,
    chart_via_agent,
    chat_with_saarthi,
    extract_json_from_text,
    find_best_consultant,
    _send_email,
    _send_whatsapp,
)
from new_agent.chart_tools import overview as chart_overview

router = APIRouter()


@router.on_event("startup")
def on_startup() -> None:
    init_db()
    migrate_csv_to_db()


@router.post("/api/leads")
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


@router.post("/api/consultant")
def get_consultant(payload: ConsultantRequest):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name, location, mobile, role, email FROM consultants"
        ).fetchall()
    consultants = [
        ConsultantInfo(
            name=row["name"] or "",
            location=row["location"] or "",
            mobile=row["mobile"] or "",
            role=row["role"] or "",
            email=row["email"] or "",
        )
        for row in rows
    ]
    consultant = find_best_consultant(payload.taskSummary, consultants)
    if not consultant:
        raise HTTPException(status_code=404, detail="No consultant found")
    return {"consultant": consultant}


@router.post("/api/notify")
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


@router.post("/api/hr/hiring")
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


@router.post("/api/hr/candidate")
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


@router.post("/api/hr/candidate/analyze")
def analyze_candidate_resume(resume: UploadFile = File(...)):
    if not resume.filename:
        raise HTTPException(status_code=400, detail="No resume uploaded")

    content = resume.file.read()
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

    raw_text = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
    analysis = extract_json_from_text(raw_text)

    if not analysis:
        print("⚠️ Model returned non-JSON or empty. Raw text (first 500 chars):")
        print(raw_text[:500])

    return {"ok": True, "analysis": analysis}


@router.post("/api/chat")
def chat_with_agent(payload: ChatRequest):
    try:
        text = chat_with_saarthi(payload.message, payload.session_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"text": text}


@router.get("/api/charts/overview")
def get_charts_overview():
    return chart_overview()


@router.post("/api/charts/agent")
def chart_agent_answer(payload: ChartAgentRequest):
    try:
        data = chart_via_agent(payload.question)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return data
