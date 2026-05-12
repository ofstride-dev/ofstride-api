from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import requests
import resend

from .config import (
    EMAIL_FROM,
    EMAIL_TO,
    GITHUB_API_URL,
    GITHUB_MODEL,
    GITHUB_TOKEN,
    OPENAI_API_URL,
    OPENAI_MODEL,
    AZURE_API_KEY,
    PROJECT_ENDPOINT,
    RESEND_API_KEY,
    SAARTHI_CHART_URL,
    SAARTHI_URL,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    TWILIO_WHATSAPP_TO,
)
from .models import ConsultantInfo


# ── LLM ───────────────────────────────────────────────────────────────────────

def call_llm(system_prompt: str, user_prompt: str) -> dict:
    if OPENAI_API_URL and AZURE_API_KEY and OPENAI_MODEL:
        headers = {"Content-Type": "application/json", "api-key": AZURE_API_KEY}
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=120)
    elif GITHUB_TOKEN:
        headers = {"Content-Type": "application/json", "api-key": GITHUB_TOKEN}
        payload = {
            "model": GITHUB_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        resp = requests.post(GITHUB_API_URL, headers=headers, json=payload, timeout=120)
    else:
        raise RuntimeError(
            "No LLM configuration found. Set AZURE_API_KEY/API_URL/GPT_MODEL for Foundry or GITHUB_TOKEN/GITHUB_API_URL/GITHUB_MODEL for GitHub inference."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"LLM ERROR: {resp.status_code} - {resp.text}")
    return resp.json()


def extract_json_from_text(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    cleaned = re.sub(r"```json\s*|\s*```", "", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(cleaned[start: end + 1])
    except Exception:
        return {}


# ── Consultant matching ───────────────────────────────────────────────────────

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "hr": ["hr", "human resources", "talent", "recruitment", "recruit", "hiring", "hire", "staffing", "payroll", "employee", "candidate"],
    "legal": ["legal", "compliance", "contract", "policy", "litigation"],
    "finance": ["finance", "financial", "cfo", "tax", "audit", "account"],
    "it": ["it", "data", "ai", "cloud", "software", "infrastructure", "website", "computing"],
}


def infer_domain(text: str) -> str:
    value = text.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in value for kw in keywords):
            return domain
    return ""


def find_best_consultant(task_summary: str, consultants: List[ConsultantInfo]) -> Optional[ConsultantInfo]:
    if not consultants:
        return None
    domain = infer_domain(task_summary)
    keywords = DOMAIN_KEYWORDS.get(domain, [])
    summary = task_summary.lower()
    best_score = 0
    best_match: Optional[ConsultantInfo] = None
    for c in consultants:
        role = c.role.lower()
        email = c.email.lower()
        score = 0
        if domain and (domain in role or domain in email):
            score += 3
        for kw in keywords:
            if kw in summary: score += 2
            if kw in role: score += 1
            if kw in email: score += 1
        if score > best_score:
            best_score = score
            best_match = c
    if best_score == 0:
        return next(
            (c for c in consultants if domain and (domain in c.role.lower() or domain in c.email.lower())),
            next((c for c in consultants if any(k in c.role.lower() or k in c.email.lower() for k in ["hr", "legal", "finance", "it"])), None),
        )
    return best_match


# ── Email via Resend ──────────────────────────────────────────────────────────

def _plain_to_html(text: str) -> str:
    """Wrap plain text in minimal HTML for Resend."""
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body = "<br>".join(safe.splitlines())
    return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#333;line-height:1.7;max-width:600px;margin:0 auto;padding:24px">
{body}
<hr style="margin-top:32px;border:none;border-top:1px solid #eee">
<p style="font-size:12px;color:#999">Ofstride Services LLP &nbsp;|&nbsp; info@ofstride.com &nbsp;|&nbsp; +91 89516 06862</p>
</body></html>"""


def _send_email(subject: str, text_body: str, recipients: List[str]) -> str:
    """Send via Resend. Returns 'sent', 'skipped', or 'error'."""
    if not RESEND_API_KEY:
        print("[email] RESEND_API_KEY not set — skipping")
        return "skipped"
    to = sorted(set(r for r in recipients if r))
    if not to:
        return "skipped"
    resend.api_key = RESEND_API_KEY
    try:
        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": to,
            "subject": subject,
            "html": _plain_to_html(text_body),
        })
        return "sent"
    except Exception as exc:
        print(f"[email] Resend error: {exc}")
        return "error"


def _send_confirmation_email(lead_name: str, lead_email: str, task_summary: str) -> str:
    """Instant confirmation to the user as soon as their lead is saved."""
    if not lead_email:
        return "skipped"
    subject = "We've received your request — Ofstride"
    text = f"""Hi {lead_name},

Thanks for reaching out to Ofstride! We've received your request and our team will be in touch shortly.

Here's a summary of what you shared with us:

  {task_summary}

In the meantime, feel free to reply to this email if you want to add more context.

Warm regards,
The Ofstride Team

Ofstride Services LLP
Phone: +91 89516 06862
Email: info@ofstride.com
LinkedIn: https://www.linkedin.com/company/ofstride"""
    return _send_email(subject, text, recipients=[lead_email])


def _send_consultant_notification(
    lead_name: str, lead_email: str, lead_phone: str, lead_location: str,
    lead_company: str, task_summary: str, preferred_time: str, preferred_timezone: str,
    consultant_name: str, consultant_role: str, consultant_mobile: str, consultant_email: str,
) -> str:
    """Full notification to consultant + Ofstride inbox + CC user."""
    subject = f"New consultation request — {lead_name} ({lead_company})"
    text = f"""A new consultation request has been submitted via Saarthi.

-- Lead Details ----------------------------------------
Name:     {lead_name}
Email:    {lead_email or '(not provided)'}
Phone:    {lead_phone}
Location: {lead_location}
Company:  {lead_company}
Request:  {task_summary}
Preferred time: {preferred_time or '-'} {preferred_timezone or ''}

-- Matched Consultant -----------------------------------
Name:     {consultant_name}
Role:     {consultant_role}
Phone:    {consultant_mobile}
Email:    {consultant_email}

Please reach out to the lead within 24 hours.

Ofstride Saarthi | Automated notification"""
    recipients = [r for r in [consultant_email, EMAIL_TO] if r]
    if lead_email:
        recipients.append(lead_email)
    return _send_email(subject, text, recipients=recipients)


def _send_user_consultant_email(
    lead_name: str, lead_email: str,
    consultant_name: str, consultant_role: str, consultant_mobile: str, consultant_email: str,
) -> str:
    """Warm personal email to user with their consultant's details."""
    if not lead_email:
        return "skipped"
    subject = f"Your Ofstride consultant: {consultant_name}"
    text = f"""Hi {lead_name},

Great news — we've matched you with one of our specialists who will be in touch shortly.

-- Your Consultant --------------------------------------
Name:  {consultant_name}
Role:  {consultant_role}
Phone: {consultant_mobile}
Email: {consultant_email}

Feel free to reach out to them directly, or reply to this email if you need anything else.

Warm regards,
The Ofstride Team

Ofstride Services LLP
Phone: +91 89516 06862
Email: info@ofstride.com
LinkedIn: https://www.linkedin.com/company/ofstride"""
    return _send_email(subject, text, recipients=[lead_email])


# ── WhatsApp via Twilio (optional) ────────────────────────────────────────────

def _send_whatsapp(message: str) -> str:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        return "skipped"
    auth = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode("utf-8")
    headers = {
        "Authorization": f"Basic {base64.b64encode(auth).decode('utf-8')}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = urllib.parse.urlencode({"From": TWILIO_WHATSAPP_FROM, "To": TWILIO_WHATSAPP_TO, "Body": message}).encode("utf-8")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20):
            return "sent"
    except Exception as exc:
        print(f"[whatsapp] error: {exc}")
        return "error"


# ── Saarthi proxy ─────────────────────────────────────────────────────────────

def chat_with_saarthi(message: str, session_id: Optional[str] = None) -> str:
    if not message:
        raise ValueError("message is required")
    body = json.dumps({"message": message, "session_id": session_id or "default"}).encode("utf-8")
    req = urllib.request.Request(SAARTHI_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Saarthi error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Saarthi service unreachable") from exc
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid Saarthi response") from exc
    return data.get("text") or data.get("answer") or data.get("response") or "Sorry, I couldn't find an answer."


def chart_via_agent(question: str) -> dict:
    if not question:
        raise ValueError("question is required")
    response = requests.post(SAARTHI_CHART_URL, json={"question": question}, timeout=60)
    response.raise_for_status()
    return response.json()
