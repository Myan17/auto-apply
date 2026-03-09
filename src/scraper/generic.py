"""Generic scraper using trafilatura for static pages."""

import httpx
import trafilatura
from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Job

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class GenericScraper(BaseScraper):
    def scrape(self, job: Job) -> Job:
        response = httpx.get(job.url, headers=HEADERS, follow_redirects=True, timeout=20)
        response.raise_for_status()

        html = response.text

        # Try trafilatura first (best at extracting main content)
        text = trafilatura.extract(html, include_formatting=True)

        # Fall back to BeautifulSoup if trafilatura returns nothing
        if not text:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n").strip()

        # Try to extract title and company
        soup = BeautifulSoup(html, "html.parser")
        if not job.role:
            for sel in ["h1", "title"]:
                tag = soup.find(sel)
                if tag:
                    job.role = tag.get_text().strip()[:120]
                    break
        if not job.company:
            for meta_attr in [{"property": "og:site_name"}, {"name": "application-name"}]:
                meta = soup.find("meta", meta_attr)
                if meta and meta.get("content"):
                    job.company = meta["content"].strip()[:60]
                    break

        job.description = text or "Could not extract job description."
        return job
