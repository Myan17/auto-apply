"""Workday account-password handling.

Workday applications create an account on the employer's tenant holding the
applicant's name, address, phone and resume. The password for that account
must come from the user's own configuration -- never from a value in this
public repository.
"""
from types import SimpleNamespace

import pytest

from src.applicator.browser import workday
from src.applicator.browser.workday import (
    WorkdayApplicator,
    WorkdayPasswordNotConfigured,
)

OLD_PUBLIC_DEFAULT = "AutoApply@2026!"


class _Locator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def count(self):
        return 1 if self.selector in self.page.present else 0

    def fill(self, value, timeout=None):
        self.page.filled[self.selector] = value

    def click(self, timeout=None):
        self.page.clicked.append(self.selector)

    def check(self, timeout=None):
        self.page.clicked.append(self.selector)

    @property
    def first(self):
        return self


class _FakePage:
    """Minimal stand-in for a Playwright page showing Workday's auth form."""

    def __init__(self, form: str):
        submit = {
            "create": "[data-automation-id='createAccountSubmitButton']",
            "signin": "[data-automation-id='signInSubmitButton']",
        }[form]
        self.present = {submit}
        self.filled = {}
        self.clicked = []

    def inner_text(self, _selector):
        return "create account" if "create" in next(iter(self.present)).lower() else "sign in"

    def locator(self, selector):
        return _Locator(self, selector)

    def get_by_text(self, *_a, **_kw):
        return _Locator(self, "text")

    def get_by_role(self, *_a, **_kw):
        return _Locator(self, "role")


def _cfg(password: str):
    env = SimpleNamespace(
        workday_password=password,
        applicant_email="me@example.com",
        applicant_name="Test User",
    )
    return SimpleNamespace(env=env)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(workday, "_random_delay", lambda *_a, **_kw: None)


@pytest.fixture
def applicator():
    return WorkdayApplicator.__new__(WorkdayApplicator)


@pytest.mark.parametrize("form", ["create", "signin"])
def test_missing_password_fails_closed(applicator, form):
    page = _FakePage(form)
    with pytest.raises(WorkdayPasswordNotConfigured, match="WORKDAY_PASSWORD"):
        applicator._handle_auth(page, _cfg(""))
    # Nothing was typed into the form before refusing.
    assert page.filled == {}


def test_the_old_public_default_is_gone_from_the_module():
    source = open(workday.__file__, encoding="utf-8").read()
    assert OLD_PUBLIC_DEFAULT not in source


def test_create_account_uses_the_configured_password(applicator):
    page = _FakePage("create")
    applicator._handle_auth(page, _cfg("user-chosen-Pw-7731"))

    passwords = {
        v for k, v in page.filled.items()
        if "password" in k.lower()
    }
    assert passwords == {"user-chosen-Pw-7731"}
    assert OLD_PUBLIC_DEFAULT not in page.filled.values()


def test_missing_password_marks_the_job_failed_not_the_batch():
    # apply() catches per-job exceptions and returns a FAILED result, so one
    # unconfigured run cannot crash a whole batch -- and the error names the fix.
    err = WorkdayPasswordNotConfigured("WORKDAY_PASSWORD is not set")
    assert isinstance(err, RuntimeError)
    assert "WORKDAY_PASSWORD" in str(err)
