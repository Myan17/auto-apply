"""Scraper for Workday job postings — uses static HTML + Playwright fallback."""

import re
import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper
from .generic import HEADERS
from ..models import Job


class WorkdayScraper(BaseScraper):
    def scrape(self, job: Job) -> Job:
        # Try static HTTP first (works for company career pages like T-Mobile)
        try:
            r = httpx.get(job.url, headers=HEADERS, follow_redirects=True, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")

            # Extract job title
            if not job.role:
                for sel in ["h1", "title"]:
                    tag = soup.find(sel)
                    if tag:
                        job.role = tag.get_text().strip()
                        break

            # Extract company name: try "Apply for <role> at <Company>" description pattern
            if not job.company:
                for meta_attr in [{"name": "description"}, {"property": "og:description"},
                                  {"name": "twitter:description"}]:
                    meta = soup.find("meta", meta_attr)
                    if meta:
                        m = re.search(r"\bat\s+([A-Z][^\.\,\n]{1,50}?)(?:\s*[\.\,]|$)",
                                      meta.get("content", ""))
                        if m:
                            job.company = m.group(1).strip()
                            break
            # Fallback: extract from domain
            if not job.company:
                m = re.search(r"(?:careers\.|jobs\.)([a-z0-9-]+)\.", job.url)
                if m:
                    job.company = m.group(1).replace("-", " ").title()
            # Hard cap — never let company name exceed 60 chars
            if job.company:
                job.company = job.company[:60].strip()

            # Extract description text
            for sel in ["div.job-description", "div[class*='description']",
                        "section[class*='description']", "article", "main"]:
                tag = soup.select_one(sel)
                if tag:
                    job.description = tag.get_text(separator="\n").strip()
                    break

            if not job.description:
                # Strip nav/header/footer and take body text
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                job.description = soup.get_text(separator="\n").strip()[:5000]

        except Exception:
            job.description = "Could not scrape job description."

        return job
