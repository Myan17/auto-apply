"""Data models for auto-apply."""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, HttpUrl


class PortalType(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    LINKEDIN = "linkedin"
    WORKDAY = "workday"
    ASHBY = "ashby"
    EMAIL = "email"
    GENERIC = "generic"


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    SCRAPED = "scraped"
    TAILORED = "tailored"
    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApplicationMethod(str, Enum):
    BROWSER = "browser"
    EMAIL = "email"


class Job(BaseModel):
    """A job listing from the Google Sheet."""
    row_number: int
    url: str
    company: str = ""
    role: str = ""
    status: ApplicationStatus = ApplicationStatus.PENDING
    portal_type: Optional[PortalType] = None
    description: Optional[str] = None
    application_email: Optional[str] = None
    date_applied: Optional[str] = None
    notes: Optional[str] = None


class TailoredDocuments(BaseModel):
    """AI-generated application materials."""
    resume_text: str
    cover_letter_text: str
    resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None


class ApplicationResult(BaseModel):
    """Result of an application attempt."""
    job_url: str
    status: ApplicationStatus
    method: ApplicationMethod
    timestamp: str
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None


class UserProfile(BaseModel):
    """Applicant's information."""
    name: str
    email: str
    resume_path: str
    resume_text: Optional[str] = None
