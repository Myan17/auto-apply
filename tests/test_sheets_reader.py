"""Sheet parsing: which rows become jobs, and with what status."""
from types import SimpleNamespace

import pytest

from src.models import ApplicationStatus, PortalType
from src.sheets import reader


class _Worksheet:
    def __init__(self, rows):
        self._rows = rows

    def get_all_values(self):
        return self._rows


@pytest.fixture
def cfg():
    cols = SimpleNamespace(url=1, company=2, role=3, status=4, notes=7)
    return SimpleNamespace(
        env=SimpleNamespace(google_sheet_id="sheet-id", google_credentials_path="creds.json"),
        sheet=SimpleNamespace(worksheet="Jobs", columns=cols),
    )


def _read(monkeypatch, cfg, rows, **kw):
    ws = _Worksheet(rows)
    sheet = SimpleNamespace(worksheet=lambda _name: ws)
    client = SimpleNamespace(open_by_key=lambda _key: sheet)
    monkeypatch.setattr(reader, "_get_client", lambda _cfg: client)
    return reader.read_jobs(cfg, **kw)


HEADER = ["URL", "Company", "Role", "Status", "Date", "Method", "Notes"]


def test_header_row_is_skipped_and_rows_are_numbered_from_two(monkeypatch, cfg):
    jobs = _read(monkeypatch, cfg, [
        HEADER,
        ["https://jobs.lever.co/acme/1", "Acme", "SWE", "", "", "", ""],
    ])
    assert len(jobs) == 1
    # row_number is what the writer uses to update the sheet, so an off-by-one
    # here would write results onto the wrong job.
    assert jobs[0].row_number == 2


def test_rows_without_a_url_are_ignored(monkeypatch, cfg):
    jobs = _read(monkeypatch, cfg, [HEADER, ["", "Acme", "SWE", "", "", "", ""]])
    assert jobs == []


def test_applied_rows_are_skipped_by_default(monkeypatch, cfg):
    rows = [HEADER, ["https://jobs.lever.co/acme/1", "Acme", "SWE", "applied", "", "", ""]]
    assert _read(monkeypatch, cfg, rows) == []
    assert len(_read(monkeypatch, cfg, rows, skip_applied=False)) == 1


def test_unknown_status_text_is_treated_as_pending(monkeypatch, cfg):
    jobs = _read(monkeypatch, cfg, [
        HEADER, ["https://jobs.lever.co/acme/1", "Acme", "SWE", "maybe later", "", "", ""],
    ])
    assert jobs[0].status == ApplicationStatus.PENDING


def test_short_rows_do_not_raise(monkeypatch, cfg):
    # Google Sheets trims trailing empty cells, so rows arrive ragged.
    jobs = _read(monkeypatch, cfg, [HEADER, ["https://jobs.lever.co/acme/1"]])
    assert jobs[0].company == ""
    assert jobs[0].notes == ""


def test_portal_is_detected_from_the_url(monkeypatch, cfg):
    jobs = _read(monkeypatch, cfg, [
        HEADER,
        ["https://boards.greenhouse.io/acme/jobs/1", "", "", "", "", "", ""],
        ["https://acme.wd5.myworkdayjobs.com/x/job/1", "", "", "", "", "", ""],
    ])
    assert [j.portal_type for j in jobs] == [PortalType.GREENHOUSE, PortalType.WORKDAY]


def test_empty_sheet_returns_no_jobs(monkeypatch, cfg):
    assert _read(monkeypatch, cfg, []) == []
