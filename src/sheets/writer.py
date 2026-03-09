"""Write application results back to Google Sheets."""

from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from ..config import AppConfig
from ..models import ApplicationStatus, Job
from .reader import SCOPES, _get_client


def update_job_status(
    config: AppConfig,
    job: Job,
    status: ApplicationStatus,
    method: str = "",
    notes: str = "",
):
    """Update a job's status, date, method, and notes in the sheet."""
    client = _get_client(config)
    sheet = client.open_by_key(config.env.google_sheet_id)
    worksheet = sheet.worksheet(config.sheet.worksheet)

    cols = config.sheet.columns
    row = job.row_number

    updates = []

    # Company column (backfill if scraped)
    if job.company and cols.company:
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row, cols.company),
            "values": [[job.company]],
        })

    # Role column (backfill if scraped)
    if job.role and cols.role:
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row, cols.role),
            "values": [[job.role]],
        })

    # Status column
    updates.append({
        "range": gspread.utils.rowcol_to_a1(row, cols.status),
        "values": [[status.value]],
    })

    # Date applied column
    if status == ApplicationStatus.APPLIED:
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row, cols.date_applied),
            "values": [[datetime.now().strftime("%Y-%m-%d")]],
        })

    # Method column
    if method and cols.method:
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row, cols.method),
            "values": [[method]],
        })

    # Notes column
    if notes and cols.notes:
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row, cols.notes),
            "values": [[notes]],
        })

    if updates:
        worksheet.batch_update(updates)


def write_scraped_summary(config: AppConfig, job: Job, summary: str):
    """Write scraped job description summary to the Notes column."""
    client = _get_client(config)
    sheet = client.open_by_key(config.env.google_sheet_id)
    worksheet = sheet.worksheet(config.sheet.worksheet)

    cols = config.sheet.columns
    if cols.notes:
        cell = gspread.utils.rowcol_to_a1(job.row_number, cols.notes)
        worksheet.update(cell, [[summary[:500]]])  # cap at 500 chars
