"""Detect job portal type from URL patterns."""

import re
from ..models import PortalType


# URL patterns for each portal
PORTAL_PATTERNS = [
    (PortalType.GREENHOUSE, [
        r"boards\.greenhouse\.io",
        r"job-boards\.greenhouse\.io",
        r"/jobs\?gh_jid=",
    ]),
    (PortalType.LEVER, [
        r"jobs\.lever\.co",
        r"lever\.co/.*?/",
    ]),
    (PortalType.LINKEDIN, [
        r"linkedin\.com/jobs",
        r"linkedin\.com/job",
    ]),
    (PortalType.WORKDAY, [
        r"myworkdayjobs\.com",
        r"wd\d+\.myworkday\.com",
        r"workday\.com",
        r"careers\.t-mobile\.com",
    ]),
    (PortalType.ASHBY, [
        r"jobs\.ashbyhq\.com",
        r"ashbyhq\.com",
    ]),
]


def detect_portal(url: str) -> PortalType:
    """Detect the portal type from a job URL."""
    url_lower = url.lower()

    for portal_type, patterns in PORTAL_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return portal_type

    # Check if URL looks like a direct email application
    if "mailto:" in url_lower:
        return PortalType.EMAIL

    return PortalType.GENERIC
