"""Scraper for Lever job postings via their public API."""

import re
from bs4 import BeautifulSoup
import httpx

from .base import BaseScraper
from ..models import Job


class LeverScraper(BaseScraper):
    def scrape(self, job: Job) -> Job:
        company_slug, job_id = self._parse_url(job.url)

        api_url = f"https://api.lever.co/v0/postings/{company_slug}/{job_id}"
        response = httpx.get(api_url, timeout=15)
        response.raise_for_status()

        data = response.json()

        # Lever returns description as plain text lists
        sections = data.get("lists", [])
        description_parts = [data.get("descriptionPlain", "")]
        for section in sections:
            description_parts.append(f"\n{section.get('text', '')}:")
            description_parts.append(section.get("content", ""))

        description = "\n".join(description_parts).strip()

        job.company = job.company or data.get("company", company_slug)
        job.role = job.role or data.get("text", "")
        job.description = description

        return job

    def _parse_url(self, url: str):
        # jobs.lever.co/{company}/{job-id}
        m = re.search(r"lever\.co/([^/]+)/([a-f0-9-]{36})", url)
        if m:
            return m.group(1), m.group(2)
        raise ValueError(f"Cannot parse Lever URL: {url}")
