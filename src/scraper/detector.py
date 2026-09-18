"""Detect job portal type from a job URL.

Matching is done on the parsed hostname, not on the raw URL string. A substring
match over the whole URL misroutes lookalike hosts -- `clever.co/...` contains
`lever.co/` and `notworkday.com` contains `workday.com` -- which would send the
job to an applicator that cannot fill its form.
"""

from urllib.parse import parse_qs, urlparse

from ..models import PortalType

# (portal, registrable domains). A host matches a domain if it is that domain
# or any subdomain of it.
PORTAL_DOMAINS = [
    (PortalType.GREENHOUSE, ["greenhouse.io"]),
    (PortalType.LEVER, ["lever.co"]),
    (PortalType.WORKDAY, ["myworkdayjobs.com", "myworkday.com", "workday.com", "careers.t-mobile.com"]),
    (PortalType.ASHBY, ["ashbyhq.com"]),
]


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def detect_portal(url: str) -> PortalType:
    """Detect the portal type from a job URL."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()

    if scheme == "mailto":
        return PortalType.EMAIL

    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()

    for portal_type, domains in PORTAL_DOMAINS:
        if any(_host_matches(host, d) for d in domains):
            return portal_type

    if _host_matches(host, "linkedin.com") and path.startswith("/job"):
        return PortalType.LINKEDIN

    # Greenhouse's embeddable board serves on the company's own domain and is
    # identified only by its gh_jid query parameter.
    if "gh_jid" in parse_qs(parsed.query):
        return PortalType.GREENHOUSE

    return PortalType.GENERIC
