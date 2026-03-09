"""Applicator package — all portals routed through VisionApplicator."""

from ..config import AppConfig
from ..models import ApplicationResult, Job, TailoredDocuments
from .browser.vision_agent import VisionApplicator


def apply_to_job(
    job: Job,
    docs: TailoredDocuments,
    config: AppConfig,
    confirm: bool = True,
) -> ApplicationResult:
    """
    Apply to any job using the GPT-4o Vision agent.
    Works on Workday, Ashby, Greenhouse, Lever, or any portal.
    """
    applicator = VisionApplicator(config)
    return applicator.apply(job, docs, confirm=confirm)
