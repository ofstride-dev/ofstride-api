from __future__ import annotations

import base64
import json
import re
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import requests

from .config import (
    GITHUB_API_URL,
    GITHUB_MODEL,
    GITHUB_TOKEN,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASS,
    SMTP_PORT,
    SMTP_TO,
    SAARTHI_CHART_URL,
    SAARTHI_URL,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    TWILIO_WHATSAPP_TO,
)
from .models import ConsultantInfo


def call_llm(system_prompt: str, user_prompt: str) -> dict:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set in environment")

    headers = {
        "Content-Type": "application/json",
        "api-key": GITHUB_TOKEN,
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
        return json.loads(cleaned[start : end + 1])
    except Exception:
        return {}


DOMAIN_KEYWORDS: Dict[str, List[str]] = {
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


def infer_domain(text: str) -> str:
    value = text.lower()
    if any(word in value for word in DOMAIN_KEYWORDS["hr"]):
        return "hr"
    if any(word in value for word in DOMAIN_KEYWORDS["legal"]):
        return "legal"
    if any(word in value for word in DOMAIN_KEYWORDS["finance"]):
        return "finance"
    if any(word in value for word in DOMAIN_KEYWORDS["it"]):
        return "it"
    return ""


def find_best_consultant(task_summary: str, consultants: List[ConsultantInfo]) -> Optional[ConsultantInfo]:
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


def _send_email(subject: str, body: str, recipients: Optional[List[str]] = None) -> str:
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


def chat_with_saarthi(message: str, session_id: Optional[str] = None) -> str:
    if not message:
        raise ValueError("message is required")

    body = json.dumps({"message": message, "session_id": session_id or "default"}).encode("utf-8")
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
        raise RuntimeError(f"Saarthi error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Saarthi service unreachable") from exc

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid Saarthi response") from exc

    return (
        data.get("text")
        or data.get("answer")
        or data.get("response")
        or "Sorry, I couldn't find an answer."
    )


def chart_via_agent(question: str) -> dict:
    if not question:
        raise ValueError("question is required")

    response = requests.post(SAARTHI_CHART_URL, json={"question": question}, timeout=60)
    response.raise_for_status()
    return response.json()
