"""Read job listings from Google Sheets."""

import warnings
warnings.filterwarnings("ignore")

from typing import List

import gspread
from google.oauth2.service_account import Credentials
from rich.console import Console

from ..config import AppConfig
from ..models import ApplicationStatus, Job
from ..scraper.detector import detect_portal

console = Console()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _get_client(config: AppConfig) -> gspread.Client:
    """Authenticate and return a gspread client."""
    creds = Credentials.from_service_account_file(
        config.env.google_credentials_path,
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def read_jobs(config: AppConfig, skip_applied: bool = True) -> List[Job]:
    """
    Read all pending job rows from the Google Sheet.

    Expected sheet columns (configurable in settings.yaml):
        1: URL
        2: Company
        3: Role
        4: Status
        5: Date Applied
        6: Method
        7: Notes
    """
    client = _get_client(config)
    sheet = client.open_by_key(config.env.google_sheet_id)
    worksheet = sheet.worksheet(config.sheet.worksheet)

    rows = worksheet.get_all_values()
    if not rows:
        console.print("[yellow]Sheet is empty.[/yellow]")
        return []

    cols = config.sheet.columns
    jobs = []

    # Skip header row (row index 0 = row 1 in sheet)
    for i, row in enumerate(rows[1:], start=2):
        def cell(col_num: int) -> str:
            idx = col_num - 1
            return row[idx].strip() if idx < len(row) else ""

        url = cell(cols.url)
        if not url:
            continue

        status_raw = cell(cols.status).lower()
        try:
            status = ApplicationStatus(status_raw) if status_raw else ApplicationStatus.PENDING
        except ValueError:
            status = ApplicationStatus.PENDING

        # Skip already-applied rows
        if skip_applied and status == ApplicationStatus.APPLIED:
            continue

        job = Job(
            row_number=i,
            url=url,
            company=cell(cols.company),
            role=cell(cols.role),
            status=status,
            portal_type=detect_portal(url),
            notes=cell(cols.notes),
        )
        jobs.append(job)

    return jobs
