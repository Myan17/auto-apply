"""Portal detection routes each job URL to the applicator that can fill it.

A wrong route sends a Workday form to the Greenhouse filler, which at best
fails and at worst submits a half-filled application, so this is tested
against both real URL shapes and near-miss hosts.
"""
import pytest

from src.models import PortalType
from src.scraper.detector import detect_portal


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://boards.greenhouse.io/stripe/jobs/5123456", PortalType.GREENHOUSE),
        ("https://job-boards.greenhouse.io/anthropic/jobs/4020305008", PortalType.GREENHOUSE),
        ("https://www.example.com/careers/jobs?gh_jid=4412345", PortalType.GREENHOUSE),
        ("https://jobs.lever.co/netflix/1a2b3c4d-0000-1111-2222-333344445555", PortalType.LEVER),
        ("https://www.linkedin.com/jobs/view/3912345678", PortalType.LINKEDIN),
        ("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA/Engineer_JR1", PortalType.WORKDAY),
        ("https://wd1.myworkday.com/acme/d/inst/job/123", PortalType.WORKDAY),
        ("https://jobs.ashbyhq.com/openai/abcdef12-3456", PortalType.ASHBY),
        ("mailto:jobs@startup.io?subject=Application", PortalType.EMAIL),
        ("https://careers.somecompany.com/positions/42", PortalType.GENERIC),
    ],
)
def test_real_url_shapes_route_correctly(url, expected):
    assert detect_portal(url) == expected


def test_detection_is_case_insensitive():
    assert detect_portal("HTTPS://JOBS.LEVER.CO/Netflix/ABC") == PortalType.LEVER


@pytest.mark.parametrize(
    "url",
    [
        # Hosts that merely *contain* a portal name must not be misrouted.
        "https://clever.co/careers/engineer/",
        "https://www.clever.com/jobs/123",
        "https://notworkday.com/jobs/1",
        "https://myashbyhqclone.example/jobs/1",
    ],
)
def test_lookalike_hosts_are_not_misrouted(url):
    assert detect_portal(url) == PortalType.GENERIC
