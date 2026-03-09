"""Configuration loading and validation."""

import os
import sys
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, validator

# Project root
ROOT_DIR = Path(__file__).parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"


class SheetColumnsConfig(BaseModel):
    url: int = 1
    company: int = 2
    role: int = 3
    status: int = 4
    date_applied: int = 5
    method: int = 6
    notes: int = 7


class SheetConfig(BaseModel):
    worksheet: str = "Sheet1"
    columns: SheetColumnsConfig = SheetColumnsConfig()


class ApplyConfig(BaseModel):
    limit: int = 10
    delay: int = 45
    portals: list = ["greenhouse", "lever", "linkedin", "workday", "email", "generic"]


class BrowserConfig(BaseModel):
    headless: bool = False
    typing_delay: int = 80
    viewport_width: int = 1280
    viewport_height: int = 800
    session_path: str = "./data/browser_session"


class AIConfig(BaseModel):
    model: str = "gpt-4o"           # Vision agent model
    tailor_model: str = "gpt-4o-mini"  # Resume/cover letter model (higher TPM limits)
    max_tokens_resume: int = 2000
    max_tokens_cover_letter: int = 1500


class EmailTemplateConfig(BaseModel):
    subject: str = "Application for {role} - {company}"
    body: str = ""


class ProfileConfig(BaseModel):
    """Standard answers to common application questions."""
    based_in_us: bool = True
    requires_sponsorship: bool = True
    open_to_relocation: bool = True
    willing_to_work_onsite: bool = True
    prepared_for_startup: bool = True
    additional_note: str = ""
    # EEO / self-identification
    hispanic_or_latino: bool = False
    ethnicity: str = "Asian"
    veteran_status: str = "I am not a protected veteran"
    self_id_language: str = "English"
    # General application questions
    country_of_residence: str = "United States"
    heard_about_us: str = "LinkedIn"
    previously_employed_here: bool = False
    at_least_18: bool = True
    available_start_date: str = "May 2026"


class DocumentsConfig(BaseModel):
    format: str = "pdf"
    resume_name: str = "{name}_Resume_{company}.pdf"
    cover_letter_name: str = "{name}_CoverLetter_{company}.pdf"


class EnvConfig(BaseModel):
    """Secrets loaded from .env file."""
    openai_api_key: str = ""
    google_credentials_path: str = ""
    google_sheet_id: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_email: str = ""
    smtp_password: str = ""
    applicant_name: str = ""
    applicant_email: str = ""
    applicant_phone: str = ""
    applicant_address: str = ""
    applicant_city: str = ""
    applicant_state: str = ""
    applicant_zip: str = ""
    workday_password: str = ""
    resume_path: str = ""


class AppConfig(BaseModel):
    """Full application configuration."""
    sheet: SheetConfig = SheetConfig()
    apply: ApplyConfig = ApplyConfig()
    browser: BrowserConfig = BrowserConfig()
    ai: AIConfig = AIConfig()
    profile: ProfileConfig = ProfileConfig()
    email: EmailTemplateConfig = EmailTemplateConfig()
    documents: DocumentsConfig = DocumentsConfig()
    env: EnvConfig = EnvConfig()


def load_settings() -> Dict[str, Any]:
    """Load settings.yaml."""
    settings_path = CONFIG_DIR / "settings.yaml"
    if not settings_path.exists():
        return {}
    with open(settings_path, "r") as f:
        return yaml.safe_load(f) or {}


def load_env() -> EnvConfig:
    """Load environment variables from .env file."""
    env_path = ROOT_DIR / ".env"
    load_dotenv(env_path)

    return EnvConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        google_credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH", ""),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_email=os.getenv("SMTP_EMAIL", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        applicant_name=os.getenv("APPLICANT_NAME", ""),
        applicant_email=os.getenv("APPLICANT_EMAIL", ""),
        applicant_phone=os.getenv("APPLICANT_PHONE", ""),
        applicant_address=os.getenv("APPLICANT_ADDRESS", ""),
        applicant_city=os.getenv("APPLICANT_CITY", ""),
        applicant_state=os.getenv("APPLICANT_STATE", ""),
        applicant_zip=os.getenv("APPLICANT_ZIP", ""),
        workday_password=os.getenv("WORKDAY_PASSWORD", ""),
        resume_path=os.getenv("RESUME_PATH", ""),
    )


def load_config() -> AppConfig:
    """Load full application configuration."""
    settings = load_settings()
    env = load_env()

    config = AppConfig(
        sheet=SheetConfig(**settings.get("sheet", {})),
        apply=ApplyConfig(**settings.get("apply", {})),
        browser=BrowserConfig(**settings.get("browser", {})),
        ai=AIConfig(**settings.get("ai", {})),
        profile=ProfileConfig(**settings.get("profile", {})),
        email=EmailTemplateConfig(**settings.get("email", {})),
        documents=DocumentsConfig(**settings.get("documents", {})),
        env=env,
    )
    return config


def validate_config(config: AppConfig) -> list:
    """Validate config and return list of warnings/errors."""
    issues = []

    if not config.env.openai_api_key:
        issues.append("OPENAI_API_KEY not set in .env")
    if not config.env.google_credentials_path:
        issues.append("GOOGLE_CREDENTIALS_PATH not set in .env")
    elif not Path(config.env.google_credentials_path).exists():
        issues.append(f"Google credentials file not found: {config.env.google_credentials_path}")
    if not config.env.google_sheet_id:
        issues.append("GOOGLE_SHEET_ID not set in .env")
    if not config.env.resume_path:
        issues.append("RESUME_PATH not set in .env")
    elif not Path(config.env.resume_path).exists():
        issues.append(f"Resume file not found: {config.env.resume_path}")
    if not config.env.applicant_name:
        issues.append("APPLICANT_NAME not set in .env")
    if not config.env.applicant_email:
        issues.append("APPLICANT_EMAIL not set in .env")

    return issues
