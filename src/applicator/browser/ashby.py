"""Playwright applicator for Ashby job postings."""

import time
from datetime import datetime
from pathlib import Path

from ...config import AppConfig
from ...models import ApplicationMethod, ApplicationResult, ApplicationStatus, Job, TailoredDocuments
from ..base import BaseApplicator
from .engine import get_browser, human_type, _random_delay


class AshbyApplicator(BaseApplicator):
    def __init__(self, config: AppConfig):
        self.config = config

    def apply(
        self,
        job: Job,
        docs: TailoredDocuments,
        confirm: bool = True,
    ) -> ApplicationResult:
        cfg = self.config
        screenshot_path = None

        # Use the /application URL
        app_url = job.url
        if "/application" not in app_url:
            base = app_url.split("?")[0].rstrip("/")
            app_url = f"{base}/application"

        print(f"\n  Opening browser for: {job.company} — {job.role}")
        print(f"  URL: {app_url}")

        try:
            with get_browser(cfg, headless=False) as context:
                page = context.new_page()
                page.goto(app_url, wait_until="networkidle", timeout=30000)
                _random_delay(1.5)

                # --- Name ---
                page.fill("#_systemfield_name", cfg.env.applicant_name)
                _random_delay(0.5)

                # --- Email ---
                page.fill("#_systemfield_email", cfg.env.applicant_email)
                _random_delay(0.5)

                # --- Resume upload ---
                if docs.resume_path and Path(docs.resume_path).exists():
                    page.set_input_files("#_systemfield_resume", docs.resume_path)
                    _random_delay(1.0)
                    print("  Resume uploaded.")

                p = cfg.profile  # shorthand for profile answers

                # --- Yes/No radio questions (driven by profile config) ---
                # "Are you currently based in the United States?"
                self._click_yes_no(page, "7054e280-35c0-41f6-95b5-1cf90a6c6824",
                                   answer="Yes" if p.based_in_us else "No")
                _random_delay(0.4)

                # "Do you require employment sponsorship?"
                self._click_yes_no(page, "fb9b0be4-80ac-4c45-aeed-c9edecdc9bfd",
                                   answer="Yes" if p.requires_sponsorship else "No")
                _random_delay(0.4)

                # "Are you able to work in-person in SF 5 days/week?"
                if p.willing_to_work_onsite and p.open_to_relocation:
                    # Open to relocation (radio index 1)
                    relocation_radio = (
                        "#63d96627-73cc-4991-b099-cda4fa66e246_"
                        "a4e87367-a801-416b-8681-2dcef66a5803-labeled-radio-1"
                    )
                elif p.willing_to_work_onsite:
                    # Currently in SF Bay Area (radio index 0)
                    relocation_radio = (
                        "#63d96627-73cc-4991-b099-cda4fa66e246_"
                        "a4e87367-a801-416b-8681-2dcef66a5803-labeled-radio-0"
                    )
                else:
                    # Cannot work in-office (radio index 2)
                    relocation_radio = (
                        "#63d96627-73cc-4991-b099-cda4fa66e246_"
                        "a4e87367-a801-416b-8681-2dcef66a5803-labeled-radio-2"
                    )
                try:
                    page.click(relocation_radio, timeout=5000)
                except Exception:
                    pass
                _random_delay(0.4)

                # "Are you prepared to work at a startup?"
                self._click_yes_no(page, "3575258d-7132-4c72-bd8a-e9b05a82d7ee",
                                   answer="Yes" if p.prepared_for_startup else "No")
                _random_delay(0.4)

                # --- Optional "Anything else" textarea ---
                note = p.additional_note or f"I am excited about this opportunity at {job.company}."
                try:
                    page.fill("#80819a7e-5472-4d7f-bf8e-cc006d8a798a", note, timeout=3000)
                    _random_delay(0.4)
                except Exception:
                    pass

                print("\n  [✓] Form filled. Waiting for you to solve the reCAPTCHA and click Submit.")
                print("  Close the browser window when done (or after submission).\n")

                # Take a screenshot of the filled form
                screenshot_path = f"data/screenshots/{job.company}_filled_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot_path)

                if confirm:
                    # Wait for user to close the browser manually
                    print("  Waiting for browser to close...")
                    page.wait_for_event("close", timeout=0)  # no timeout

            return ApplicationResult(
                job_url=job.url,
                status=ApplicationStatus.APPLIED,
                method=ApplicationMethod.BROWSER,
                timestamp=datetime.now().isoformat(),
                screenshot_path=screenshot_path,
            )

        except Exception as e:
            return ApplicationResult(
                job_url=job.url,
                status=ApplicationStatus.FAILED,
                method=ApplicationMethod.BROWSER,
                timestamp=datetime.now().isoformat(),
                screenshot_path=screenshot_path,
                error_message=str(e),
            )

    def _click_yes_no(self, page, field_name: str, answer: str = "Yes"):
        """Click a Yes or No label for a custom radio/checkbox field."""
        try:
            # Ashby renders Yes/No as visible buttons — find by label text near the input
            label = page.locator(
                f"label:has(input[name='{field_name}'])"
            ).filter(has_text=answer).first
            label.click(timeout=5000)
        except Exception:
            # Fallback: click the raw input checkbox
            try:
                page.check(f"input[name='{field_name}']", timeout=3000)
            except Exception:
                pass
