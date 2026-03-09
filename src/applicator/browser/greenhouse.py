"""Playwright applicator for Greenhouse job postings."""

from datetime import datetime
from pathlib import Path

from ...config import AppConfig
from ...models import ApplicationMethod, ApplicationResult, ApplicationStatus, Job, TailoredDocuments
from ..base import BaseApplicator
from .engine import get_browser, _random_delay


class GreenhouseApplicator(BaseApplicator):
    def __init__(self, config: AppConfig):
        self.config = config

    def apply(self, job: Job, docs: TailoredDocuments, confirm: bool = True) -> ApplicationResult:
        screenshot_path = None
        try:
            with get_browser(self.config, headless=False) as context:
                page = context.new_page()
                page.goto(job.url, wait_until="networkidle", timeout=30000)
                _random_delay(1.5)

                # Standard Greenhouse fields
                self._fill_if_present(page, "#first_name", self.config.env.applicant_name.split()[0])
                self._fill_if_present(page, "#last_name", " ".join(self.config.env.applicant_name.split()[1:]))
                self._fill_if_present(page, "#email", self.config.env.applicant_email)
                self._fill_if_present(page, "#phone", "")

                if docs.resume_path and Path(docs.resume_path).exists():
                    try:
                        page.set_input_files("#resume", docs.resume_path, timeout=5000)
                        _random_delay(1.0)
                    except Exception:
                        pass

                if docs.cover_letter_path and Path(docs.cover_letter_path).exists():
                    try:
                        page.set_input_files("#cover_letter", docs.cover_letter_path, timeout=5000)
                        _random_delay(1.0)
                    except Exception:
                        pass

                screenshot_path = f"data/screenshots/{job.company}_filled_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot_path)

                print("\n  [✓] Form filled. Solve any CAPTCHA and click Submit, then close the browser.")
                if confirm:
                    page.wait_for_event("close", timeout=0)

            return ApplicationResult(
                job_url=job.url, status=ApplicationStatus.APPLIED,
                method=ApplicationMethod.BROWSER, timestamp=datetime.now().isoformat(),
                screenshot_path=screenshot_path,
            )
        except Exception as e:
            return ApplicationResult(
                job_url=job.url, status=ApplicationStatus.FAILED,
                method=ApplicationMethod.BROWSER, timestamp=datetime.now().isoformat(),
                screenshot_path=screenshot_path, error_message=str(e),
            )

    def _fill_if_present(self, page, selector: str, value: str):
        try:
            page.fill(selector, value, timeout=3000)
            _random_delay(0.3)
        except Exception:
            pass
