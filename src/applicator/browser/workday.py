"""Playwright applicator for Workday job postings."""

import re
import time
from datetime import datetime
from pathlib import Path

from ...config import AppConfig
from ...models import ApplicationMethod, ApplicationResult, ApplicationStatus, Job, TailoredDocuments
from ..base import BaseApplicator
from .engine import get_browser, _random_delay


# Workday page states we can detect
STATE_LANDING      = "landing"       # "Autofill / Apply Manually / Use Last Application"
STATE_AUTH         = "auth"          # "Create Account / Sign In"
STATE_EMAIL_VERIFY = "email_verify"  # "Check your email" / verification pending
STATE_MY_INFO      = "my_info"       # Step: My Information
STATE_MY_EXP       = "my_experience" # Step: My Experience (resume upload)
STATE_QUESTIONS    = "questions"     # Step: Application Questions
STATE_EEO          = "eeo"          # Step: Voluntary Disclosures / Self Identify
STATE_REVIEW       = "review"        # Step: Review (final)
STATE_SUBMITTED    = "submitted"     # Confirmation page
STATE_UNKNOWN      = "unknown"


def detect_state(page) -> str:
    """Detect the current Workday page state using both text and DOM presence."""
    try:
        text = page.inner_text("body", timeout=3000).lower()
    except Exception:
        return STATE_UNKNOWN

    # --- Submission confirmation ---
    if "application submitted" in text or "thank you for applying" in text or "application has been submitted" in text:
        return STATE_SUBMITTED

    # --- Review: must have a visible Submit Application button in DOM, not just the word "review" ---
    try:
        submit_btn = page.locator(
            "[data-automation-id='bottomNavigationSubmitButton'], "
            "button:has-text('Submit Application')"
        )
        if submit_btn.count() > 0 and submit_btn.first.is_visible(timeout=1000):
            return STATE_REVIEW
    except Exception:
        pass

    # --- EEO / Self-identify: check current step heading, not sidebar ---
    # Look for the active step heading (not the sidebar nav item)
    try:
        active = page.locator("[data-automation-id='formHeaderTitle'], h2").first.inner_text(timeout=2000).lower()
        if "voluntary disclosure" in active or "self identify" in active:
            return STATE_EEO
        if "application question" in active or "question" in active:
            return STATE_QUESTIONS
        if "my experience" in active:
            return STATE_MY_EXP
        if "my information" in active:
            return STATE_MY_INFO
        if "create account" in active or "sign in" in active:
            return STATE_AUTH
    except Exception:
        pass

    # --- Fallback: text-based detection on the active content area only ---
    # Use a narrower selector to avoid sidebar nav text
    try:
        main_text = page.locator("main, [role='main'], form, #wd-main-area").first.inner_text(timeout=2000).lower()
    except Exception:
        main_text = text

    if "voluntary disclosure" in main_text or "self identify" in main_text or ("veteran" in main_text and "status" in main_text):
        return STATE_EEO
    if "application question" in main_text:
        return STATE_QUESTIONS
    if "my experience" in main_text and ("resume" in main_text or "work experience" in main_text):
        return STATE_MY_EXP
    if "my information" in main_text and ("first name" in main_text or "phone" in main_text):
        return STATE_MY_INFO
    if "verify" in main_text and "email" in main_text:
        return STATE_EMAIL_VERIFY
    if "create account" in main_text or ("sign in" in main_text and "password" in main_text):
        return STATE_AUTH
    if "apply manually" in text or "autofill with resume" in text or "use my last application" in text:
        return STATE_LANDING
    return STATE_UNKNOWN


class WorkdayApplicator(BaseApplicator):
    def __init__(self, config: AppConfig):
        self.config = config

    def apply(self, job: Job, docs: TailoredDocuments, confirm: bool = True) -> ApplicationResult:
        cfg = self.config
        screenshot_path = None
        apply_url = self._resolve_apply_url(job.url)

        print(f"\n  Opening Workday for: {job.company} — {job.role}")
        print(f"  URL: {apply_url}\n")

        try:
            with get_browser(cfg, headless=False) as context:
                page = context.new_page()
                page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
                _random_delay(3.0)

                visited = set()
                max_steps = 20  # safety limit

                for _ in range(max_steps):
                    state = detect_state(page)
                    print(f"  [state] {state}")

                    if state == STATE_SUBMITTED:
                        print("  [✓] Application submitted!")
                        break

                    if state in visited and state not in (STATE_QUESTIONS, STATE_EEO, STATE_UNKNOWN):
                        # Avoid infinite loops on the same state
                        print(f"  [!] Already handled state '{state}' — may be stuck. Pausing for manual action.")
                        input("  Press Enter once you've moved past this screen > ")
                        visited.discard(state)
                        continue

                    visited.add(state)

                    if state == STATE_LANDING:
                        self._click_apply_manually(page)

                    elif state == STATE_AUTH:
                        self._handle_auth(page, cfg)

                    elif state == STATE_EMAIL_VERIFY:
                        print("\n  [!] Check your email for a Workday verification link.")
                        print("  Click the link in the email to verify, then come back here.")
                        input("  Press Enter once verified > ")

                    elif state == STATE_MY_INFO:
                        self._fill_my_information(page, cfg)

                    elif state == STATE_MY_EXP:
                        self._fill_my_experience(page, cfg, docs)

                    elif state == STATE_QUESTIONS:
                        self._handle_questions(page)
                        _random_delay(1.0)
                        self._click_next(page)
                        _random_delay(1.5)
                        # Check if next failed (still on questions — validation errors remain)
                        if detect_state(page) == STATE_QUESTIONS:
                            print("\n  [!] Some questions still need answers — please complete in browser.")
                            input("  Press Enter when done > ")
                            self._click_next(page)
                        visited.discard(STATE_QUESTIONS)  # may have multiple question pages

                    elif state == STATE_EEO:
                        print("\n  [!] EEO / Self-identify form — please complete in browser.")
                        input("  Press Enter when done > ")
                        self._click_next(page)
                        visited.discard(STATE_EEO)

                    elif state == STATE_REVIEW:
                        screenshot_path = f"data/screenshots/{job.company}_workday_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=screenshot_path, full_page=True)
                        print("\n  [✓] Review page reached. Please review and click Submit.")
                        print("  Close the browser when done.")
                        page.wait_for_event("close", timeout=0)
                        break

                    else:  # STATE_UNKNOWN
                        _random_delay(2.0)  # wait for page to settle and re-detect

                    _random_delay(1.5)

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

    def _click_apply_manually(self, page):
        """Click 'Apply Manually' on the Workday landing screen."""
        for label in ["Apply Manually"]:
            try:
                page.get_by_text(label, exact=True).click(timeout=5000)
                _random_delay(2.0)
                print("  Clicked 'Apply Manually'.")
                return
            except Exception:
                pass
        try:
            page.locator("text=Manually").first.click(timeout=5000)
            _random_delay(2.0)
        except Exception:
            print("  Could not click 'Apply Manually' — proceeding.")

    def _handle_auth(self, page, cfg):
        """Fill Workday account creation or sign-in form using exact data-automation-id selectors."""
        _random_delay(1.0)
        text = page.inner_text("body").lower()
        password = cfg.env.workday_password or "AutoApply@2026!"

        # Check which sub-form is visible: Create Account vs Sign In
        is_create = page.locator("[data-automation-id='createAccountSubmitButton']").count() > 0
        is_signin = page.locator("[data-automation-id='signInSubmitButton']").count() > 0

        if is_create:
            print("  Filling Create Account form...")
            # Email (type=text with automation-id 'email')
            try:
                page.locator("[data-automation-id='email']").fill(cfg.env.applicant_email, timeout=5000)
                _random_delay(0.4)
            except Exception as e:
                print(f"  [warn] email field: {e}")

            # Password
            try:
                page.locator("[data-automation-id='password']").fill(password, timeout=5000)
                _random_delay(0.3)
            except Exception as e:
                print(f"  [warn] password field: {e}")

            # Verify Password
            try:
                page.locator("[data-automation-id='verifyPassword']").fill(password, timeout=5000)
                _random_delay(0.3)
            except Exception as e:
                print(f"  [warn] verifyPassword field: {e}")

            # Consent checkbox
            try:
                page.locator("[data-automation-id='createAccountCheckbox']").check(timeout=3000)
                _random_delay(0.4)
            except Exception as e:
                print(f"  [warn] checkbox: {e}")

            # Submit — Workday hides the button with aria-hidden, use JS click as fallback
            try:
                btn = page.locator("[data-automation-id='createAccountSubmitButton']")
                btn.click(timeout=5000, force=True)
                _random_delay(3.0)
                print("  Create Account submitted.")
            except Exception as e:
                print(f"  [warn] submit button: {e}")

        elif is_signin:
            print("  Filling Sign In form...")
            try:
                page.locator("[data-automation-id='email']").fill(cfg.env.applicant_email, timeout=5000)
                _random_delay(0.4)
                page.locator("[data-automation-id='password']").fill(password, timeout=5000)
                _random_delay(0.4)
                page.locator("[data-automation-id='signInSubmitButton']").click(timeout=5000, force=True)
                _random_delay(3.0)
                print("  Signed in.")
            except Exception as e:
                print(f"  [warn] sign in: {e}")

        else:
            print("  [!] Auth form not detected by automation-id — pausing for manual action.")
            input("  Please fill the form manually and press Enter > ")

    def _fill_text_field(self, page, label: str, value: str, automation_ids: list = None):
        """Fill a text input by trying automation-id selectors then label fallback."""
        if not value:
            return
        # Try explicit automation-ids first
        for aid in (automation_ids or []):
            try:
                loc = page.locator(f"[data-automation-id='{aid}']").first
                if loc.count() and loc.is_visible(timeout=2000):
                    loc.triple_click(timeout=3000)
                    loc.fill(value, timeout=3000)
                    _random_delay(0.3)
                    return
            except Exception:
                pass
        # Fallback: match by visible label text
        try:
            loc = page.get_by_label(re.compile(re.escape(label), re.I), exact=False).first
            loc.triple_click(timeout=3000)
            loc.fill(value, timeout=3000)
            _random_delay(0.3)
            return
        except Exception:
            pass

    def _select_workday_dropdown(self, page, label: str, value: str, automation_ids: list = None):
        """Select an option from a Workday custom combobox/dropdown."""
        opened = False
        # Try clicking the combobox trigger by automation-id
        for aid in (automation_ids or []):
            try:
                loc = page.locator(f"[data-automation-id='{aid}']").first
                if loc.count() and loc.is_visible(timeout=2000):
                    loc.click(timeout=3000)
                    _random_delay(0.5)
                    opened = True
                    break
            except Exception:
                pass
        # Fallback: click by label
        if not opened:
            try:
                page.get_by_label(re.compile(re.escape(label), re.I), exact=False).first.click(timeout=3000)
                _random_delay(0.5)
                opened = True
            except Exception:
                pass

        if not opened:
            return

        # Type value to filter options
        try:
            page.keyboard.type(value, delay=60)
            _random_delay(0.8)
        except Exception:
            pass

        # Click the best matching option in the dropdown list
        for strategy in [
            lambda: page.get_by_role("option", name=re.compile(re.escape(value), re.I)).first.click(timeout=3000),
            lambda: page.locator(f"[data-automation-id*='option']", ).filter(has_text=re.compile(re.escape(value), re.I)).first.click(timeout=3000),
            lambda: page.locator("li[role='option']").filter(has_text=re.compile(re.escape(value), re.I)).first.click(timeout=3000),
            lambda: page.get_by_role("listbox").locator("*").filter(has_text=re.compile(re.escape(value), re.I)).first.click(timeout=2000),
            lambda: page.keyboard.press("Enter"),  # accept first suggestion
        ]:
            try:
                strategy()
                _random_delay(0.4)
                return
            except Exception:
                pass

    def _fill_my_information(self, page, cfg):
        """Fill Step: My Information."""
        _random_delay(1.5)
        name_parts = cfg.env.applicant_name.split()
        first = name_parts[0] if name_parts else ""
        last = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        env = cfg.env

        # --- Text fields ---
        self._fill_text_field(page, "First Name", first,
            ["legalNameSection_firstName", "firstName", "legalName_firstName"])
        self._fill_text_field(page, "Last Name", last,
            ["legalNameSection_lastName", "lastName", "legalName_lastName"])
        self._fill_text_field(page, "Address Line 1", env.applicant_address,
            ["addressSection_addressLine1", "address1", "addressLine1"])
        self._fill_text_field(page, "City", env.applicant_city,
            ["addressSection_city", "city"])
        self._fill_text_field(page, "Postal Code", env.applicant_zip,
            ["addressSection_postalCode", "postalCode", "zipCode"])
        self._fill_text_field(page, "Phone Number", env.applicant_phone,
            ["phone-number", "phoneNumber", "phone"])

        # --- Dropdowns ---
        if getattr(env, "applicant_state", ""):
            self._select_workday_dropdown(page, "State", env.applicant_state,
                ["addressSection_countryRegion", "state", "addressSection_state"])

        # Phone Device Type — default to Mobile
        self._select_workday_dropdown(page, "Phone Device Type", "Mobile",
            ["phone-device-type", "phoneDeviceType"])

        self._click_next(page)

    def _fill_my_experience(self, page, cfg, docs: TailoredDocuments):
        """Fill Step: My Experience — upload resume."""
        _random_delay(1.5)
        resume = docs.resume_path or cfg.env.resume_path
        if resume and Path(resume).exists():
            for sel in ["[data-automation-id='file-upload-input-ref']", "input[type='file']"]:
                try:
                    page.locator(sel).first.set_input_files(resume, timeout=5000)
                    _random_delay(2.0)
                    print("  Resume uploaded.")
                    break
                except Exception:
                    pass
        self._click_next(page)

    def _handle_questions(self, page):
        """Auto-answer common application questions found on the page."""
        _random_delay(1.0)
        try:
            body = page.inner_text("body", timeout=3000).lower()
        except Exception:
            return

        # "How Did You Hear About Us?" — try common dropdown values in order
        if "how did you hear" in body:
            for value in ["LinkedIn", "Indeed", "Job Board", "Company Website", "Internet"]:
                try:
                    self._select_workday_dropdown(page, "How Did You Hear About Us", value)
                    _random_delay(0.5)
                    # Verify it was selected
                    updated = page.inner_text("body", timeout=2000).lower()
                    if value.lower() in updated or "how did you hear" not in updated:
                        break
                except Exception:
                    continue

        # "Have you previously been DIRECTLY employed with T-Mobile..." — select No
        if "previously been directly employed" in body or "previously been employed" in body:
            for label_fragment in ["previously been DIRECTLY employed", "previously been employed"]:
                try:
                    # Try radio button labeled "No"
                    loc = page.locator("fieldset").filter(
                        has_text=re.compile(re.escape(label_fragment), re.I)
                    ).first
                    loc.get_by_role("radio", name=re.compile("no", re.I)).click(timeout=3000)
                    _random_delay(0.4)
                    break
                except Exception:
                    pass
            # Fallback: try dropdown
            if "previously been directly employed" in body:
                try:
                    self._select_workday_dropdown(page, "previously been DIRECTLY employed", "No")
                except Exception:
                    pass

        # Generic Yes/No dropdowns — answer "No" for common exclusionary questions
        for fragment in ["authorized to work", "require sponsorship", "felony"]:
            if fragment in body:
                try:
                    self._select_workday_dropdown(page, fragment, "No")
                except Exception:
                    pass

        # Work authorization — "Yes" if present
        if "legally authorized" in body or "authorized to work in the" in body:
            try:
                self._select_workday_dropdown(page, "authorized to work", "Yes")
            except Exception:
                pass

    def _click_next(self, page):
        """Click the Next / Save & Continue button."""
        _random_delay(1.0)
        for name in ["Next", "Save & Continue", "Save and Continue", "Continue"]:
            try:
                page.get_by_role("button", name=re.compile(f"^{name}$", re.I)).click(timeout=5000)
                _random_delay(2.5)
                return
            except Exception:
                pass

    def _resolve_apply_url(self, url: str) -> str:
        """Resolve to Workday apply URL if given a company careers page."""
        if "myworkdayjobs.com" in url or "myworkday.com" in url:
            return url
        import httpx
        from bs4 import BeautifulSoup
        try:
            r = httpx.get(url, follow_redirects=True, timeout=15,
                          headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "myworkdayjobs.com" in href and "/apply" in href:
                    return href
        except Exception:
            pass
        return url
