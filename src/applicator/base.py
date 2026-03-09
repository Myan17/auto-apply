"""Abstract base applicator interface."""

from abc import ABC, abstractmethod
from ..models import ApplicationResult, Job, TailoredDocuments


class BaseApplicator(ABC):
    @abstractmethod
    def apply(
        self,
        job: Job,
        docs: TailoredDocuments,
        confirm: bool = True,
    ) -> ApplicationResult:
        """
        Apply to a job. Returns an ApplicationResult.
        If confirm=True, pause before final submission.
        """
