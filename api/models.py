from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


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
