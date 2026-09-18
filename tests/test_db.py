"""Application-tracking database.

`has_successful_application` is the idempotency guard: it is what stops the
tool submitting a second application to a company it already applied to. The
tests pin its exact semantics -- only an 'applied' row counts.
"""
import pytest

from src import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "auto_apply.db")
    db.init_db()


URL = "https://boards.greenhouse.io/acme/jobs/1"


def test_init_is_idempotent():
    db.init_db()
    db.init_db()
    assert db.get_stats()["total_jobs"] == 0


def test_upsert_inserts_then_updates_the_same_row():
    first = db.upsert_job(URL, company="Acme", role="SWE")
    second = db.upsert_job(URL, company="Acme Corp", role="Senior SWE")
    assert first == second
    assert db.get_stats()["total_jobs"] == 1


def test_a_fresh_job_has_no_successful_application():
    db.upsert_job(URL)
    assert db.has_successful_application(URL) is False


def test_an_applied_row_blocks_a_second_application():
    job_id = db.upsert_job(URL)
    db.record_application(job_id, status="applied", method="browser")
    assert db.has_successful_application(URL) is True


@pytest.mark.parametrize("status", ["failed", "skipped", "pending"])
def test_failed_or_skipped_attempts_do_not_block_a_retry(status):
    # A failed attempt must stay retryable, otherwise one flaky run would
    # permanently exclude the job.
    job_id = db.upsert_job(URL)
    db.record_application(job_id, status=status, error_message="timeout")
    assert db.has_successful_application(URL) is False


def test_the_guard_is_per_url():
    job_id = db.upsert_job(URL)
    db.record_application(job_id, status="applied")
    assert db.has_successful_application("https://boards.greenhouse.io/acme/jobs/2") is False


def test_a_retry_after_failure_is_recorded_as_a_new_attempt():
    job_id = db.upsert_job(URL)
    db.record_application(job_id, status="failed")
    db.record_application(job_id, status="applied")

    stats = db.get_stats()
    assert stats["by_status"] == {"failed": 1, "applied": 1}
    assert db.has_successful_application(URL) is True


def test_stats_count_successes_by_method():
    a = db.upsert_job(URL)
    b = db.upsert_job("https://jobs.lever.co/acme/2")
    db.record_application(a, status="applied", method="browser")
    db.record_application(b, status="applied", method="email")
    db.record_application(b, status="failed", method="browser")

    stats = db.get_stats()
    assert stats["by_method"] == {"browser": 1, "email": 1}
    assert stats["last_24h"] == 3


def test_url_is_unique_at_the_schema_level():
    import sqlite3

    conn = db.get_connection()
    conn.execute("INSERT INTO jobs (url) VALUES (?)", (URL,))
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO jobs (url) VALUES (?)", (URL,))
    conn.close()
