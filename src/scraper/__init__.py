"""Scraper package — routes jobs to the right portal scraper."""

from ..models import Job, PortalType
from .ashby import AshbyScraper
from .greenhouse import GreenhouseScraper
from .lever import LeverScraper
from .workday import WorkdayScraper
from .generic import GenericScraper


def scrape_job(job: Job) -> Job:
    """Route a job to the appropriate scraper and return the enriched Job."""
    portal = job.portal_type

    if portal == PortalType.ASHBY:
        scraper = AshbyScraper()
    elif portal == PortalType.GREENHOUSE:
        scraper = GreenhouseScraper()
    elif portal == PortalType.LEVER:
        scraper = LeverScraper()
    elif portal == PortalType.WORKDAY:
        scraper = WorkdayScraper()
    else:
        scraper = GenericScraper()

    return scraper.scrape(job)
