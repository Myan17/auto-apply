"""Scraper for Greenhouse job postings via their public API."""

import re
from bs4 import BeautifulSoup
import httpx

from .base import BaseScraper
from ..models import Job


class GreenhouseScraper(BaseScraper):
    def scrape(self, job: Job) -> Job:
        job_id, company_slug = self._parse_url(job.url)

        api_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs/{job_id}"
        response = httpx.get(api_url, timeout=15)
        response.raise_for_status()

        data = response.json()

        html = data.get("content", "")
        soup = BeautifulSoup(html, "html.parser")
        description = soup.get_text(separator="\n").strip()

        job.company = job.company or data.get("company", {}).get("name", company_slug)
        job.role = job.role or data.get("title", "")
        job.description = description

        return job

    def _parse_url(self, url: str):
        # boards.greenhouse.io/{company}/jobs/{id}
        m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
        if m:
            return m.group(2), m.group(1)
        # ?gh_jid={id}
        m = re.search(r"gh_jid=(\d+)", url)
        if m:
            # Company slug not in URL — return just the ID with unknown slug
            return m.group(1), "unknown"
        raise ValueError(f"Cannot parse Greenhouse URL: {url}")
