"""Scraper for Ashby job postings via their public API."""

import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import httpx

from .base import BaseScraper
from ..models import Job

# UUID pattern
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


class AshbyScraper(BaseScraper):
    def scrape(self, job: Job) -> Job:
        # Strip query params and extract path: jobs.ashbyhq.com/{company}/{job-id}[/application]
        parsed = urlparse(job.url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p and p != "application"]

        # Find the UUID job ID within path parts
        job_id = next((p for p in path_parts if _UUID_RE.match(p)), None)
        company_slug = path_parts[0] if path_parts else None

        if not job_id or not company_slug:
            raise ValueError(f"Cannot parse Ashby URL: {job.url}")

        # Fetch all jobs from the company board and find ours by ID
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
        response = httpx.get(api_url, timeout=15)
        response.raise_for_status()

        data = response.json()
        posting = next(
            (j for j in data.get("jobs", []) if j.get("id") == job_id),
            None,
        )

        if not posting:
            # Job may be unlisted — fall back to Playwright-based scraping
            raise ValueError(
                f"Job {job_id} not found in {company_slug} board API. "
                "It may be unlisted or expired."
            )

        # Strip HTML from description
        html = posting.get("descriptionHtml", "")
        soup = BeautifulSoup(html, "html.parser")
        description = soup.get_text(separator="\n").strip()

        # Derive company name: use board's organization name if available
        org_name = data.get("organization", {}).get("name", company_slug)

        job.company = job.company or org_name
        job.role = job.role or posting.get("title", "")
        job.description = description

        return job
