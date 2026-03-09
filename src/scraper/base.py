"""Abstract base scraper interface."""

from abc import ABC, abstractmethod
from ..models import Job


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, job: Job) -> Job:
        """
        Scrape the job page and return an enriched Job with:
        - company, role, description filled in
        """
