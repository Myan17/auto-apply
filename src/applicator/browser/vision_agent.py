"""
Vision-guided browser agent.
Takes a screenshot, sends it to GPT-4o Vision, gets back structured actions,
executes them with Playwright, repeats until done.
"""

import base64
import json
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from openai import OpenAI
from playwright.sync_api import Page

from ...config import AppConfig
from ...models import ApplicationMethod, ApplicationResult, ApplicationStatus, Job, TailoredDocuments
from ..base import BaseApplicator
from .engine import get_browser, _random_delay


# --------------------------------------------------------------------------- #
# System prompt — tells GPT-4o what it's doing and how to respond
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You are an intelligent browser automation agent helping fill out job applications.

You will be shown a screenshot of the current browser page along with:
- Applicant info (name, email, phone, address)
- Resume path
- What the goal is (apply for a specific job)
- A log of actions already taken
- INTERACTIVE PAGE ELEMENTS: a list of every real input/select/button/combobox on the page with their exact HTML attributes

Your job is to decide the SINGLE NEXT ACTION to take.

Respond with ONLY a JSON object (no markdown, no explanation):

{
  "observation": "brief description of what you see on screen",
  "action": "fill" | "click" | "select" | "upload" | "check" | "wait" | "pause" | "done",
  "selector": "<the actual selector string — see below>",
  "selector_type": "css" | "text" | "label" | "role",
  "value": "value to fill/select (empty string for click/check/wait)",
  "reason": "why you chose this action"
}

HOW TO USE selector AND selector_type (READ CAREFULLY):
- selector_type "css"  → selector is a CSS selector built from the INTERACTIVE PAGE ELEMENTS list, e.g. "[name='email']" or "[id='country']"
- selector_type "text" → selector is the EXACT VISIBLE TEXT of the element, e.g. "Apply Now"
- selector_type "label"→ selector is the label text next to the input, e.g. "Email address"
- selector_type "role" → selector is "role:name", e.g. "button:Apply Now"

ALWAYS prefer building selectors from the INTERACTIVE PAGE ELEMENTS list — use the id, name, data-automation-id, or aria-label shown there.
NEVER invent attribute values that are not in the element list.

EXAMPLES:
  Element list shows: [input] name="email" placeholder="Email"
  → {"action":"fill","selector":"[name='email']","selector_type":"css","value":"user@email.com"}

  Element list shows: [select] name="country" options=["","United States","Canada"]
  → {"action":"select","selector":"[name='country']","selector_type":"css","value":"United States"}

  Element list shows: [button] text="Apply Now"
  → {"action":"click","selector":"Apply Now","selector_type":"text","value":""}

  Upload resume when [input] type="file" is in element list:
  → {"action":"upload","selector":"input[type='file']","selector_type":"css","value":"/path/to/resume.pdf"}

Action meanings:
- fill: type a value into a text input
- click: click a button, link, or element
- select: choose an option from a dropdown
- upload: upload a file (value = file path)
- check: check a checkbox
- wait: wait for page to load (no selector needed)
- pause: you cannot figure out what to do — human needs to take over (explain in reason)
- done: application is complete / submitted

Rules:
- NEVER fill the "website" honeypot field (name="website", data-automation-id="beecatcher")
- For Workday: prefer data-automation-id selectors, e.g. "[data-automation-id='email']"
- If you see a CAPTCHA, use action "pause" (this is the ONLY reason to use pause)
- Email verification screens: use action "wait" — the system will handle it
- If you see a confirmation/thank you page, use action "done"
- Only return ONE action at a time
- Prefer "css" selector_type with specific attributes over "text" when possible
- IMPORTANT: Before filling or selecting a field, check if it already has the correct value (resume autofill may have populated it). If a field already contains the right value, SKIP it and target the next empty or incorrect field instead. Do NOT re-fill or re-select fields that are already correct.
- For dropdowns: if the displayed value already matches what you need to select, do not click it — move on.
- CRITICAL: If an action shows "✗ FAILED" in the action log, that selector DID NOT WORK. Do NOT repeat the same selector. Look at the INTERACTIVE PAGE ELEMENTS list and pick a different attribute (id, name, aria-label) for the same field.
- If a field is not in the INTERACTIVE PAGE ELEMENTS list at all, use action "wait" to let the page load more, then it will appear.
- Never give up on a field by using "pause" — always try the element list.
"""

USER_PROMPT_TEMPLATE = """
Goal: Apply for "{role}" at "{company}"
Apply URL: {url}

Applicant info:
- Name: {name}
- Email: {email}
- Phone: {phone}
- Address: {address}, {city} {zip}

Resume file path: {resume_path}
Tailored resume path: {tailored_resume_path}

Standard answers for application questions:
- Are you legally authorized to work in the US? Yes
- Do you require visa sponsorship now or in the future? Yes
- Are you open to relocation? Yes
- Are you willing to work on-site? Yes
- Country of residence: {country_of_residence}
- How did you hear about us? {heard_about_us}
- Have you previously been employed by this company? {previously_employed_here}
- Are you at least 18 years old? {at_least_18}
- When would you be available if an offer was accepted? {available_start_date}
- Hispanic or Latino? {hispanic_or_latino}
- Ethnicity / Race: {ethnicity}
- Veteran status: {veteran_status}
- Self-identification language preference: {self_id_language}

Actions taken so far:
{action_log}

{page_elements}

Current page screenshot is attached. What is the single next action?
"""


# --------------------------------------------------------------------------- #
# Action executor
# --------------------------------------------------------------------------- #
def execute_action(page: Page, action: dict, typing_delay: int = 80) -> bool:
    """
    Execute a single action dict on the Playwright page.
    Returns True on success, False on failure.
    """
    act = action.get("action", "wait")
    selector = action.get("selector", "")
    sel_type = action.get("selector_type", "css")
    value = action.get("value", "")

    try:
        if act == "wait":
            _random_delay(2.0)
            return True

        # Guard: if GPT put the type name literally in selector, use value instead
        _type_keywords = {"text", "css", "label", "role"}
        if sel_type == "text" and selector.lower() in _type_keywords:
            selector = value or selector

        # Resolve locator — with fallback chain
        def _resolve_loc():
            if sel_type == "text":
                # Try exact match first, then partial
                try:
                    l = page.get_by_text(selector, exact=True).first
                    l.wait_for(state="visible", timeout=3000)
                    return l
                except Exception:
                    pass
                return page.get_by_text(re.compile(re.escape(selector), re.I)).first
            elif sel_type == "label":
                return page.get_by_label(re.compile(re.escape(selector), re.I), exact=False).first
            elif sel_type == "role":
                parts = selector.split(":", 1)
                role = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else None
                return page.get_by_role(role, name=re.compile(re.escape(name), re.I) if name else None).first
            else:
                return page.locator(selector).first

        loc = _resolve_loc()

        # Scroll element into view before any interaction
        if act in ("fill", "click", "check"):
            try:
                loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass

        if act == "fill":
            # Skip if already has the correct value (resume autofill)
            try:
                current = loc.input_value(timeout=2000).strip()
                if current.lower() == value.strip().lower():
                    print(f"  [skip] field already has correct value: '{current}'")
                    return True
            except Exception:
                pass
            loc.click(timeout=5000)
            loc.fill("", timeout=3000)  # clear first
            loc.type(value, delay=typing_delay)
            _random_delay(0.4)

        elif act == "click":
            try:
                loc.click(timeout=8000, force=True)
            except Exception:
                # Fallback: JS click (works on elements hidden behind overlays)
                loc.evaluate("el => el.click()")
            _random_delay(1.5)

        elif act == "select":
            # Scroll element into view first
            try:
                loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass

            # Check if dropdown already shows the correct value (autofilled)
            try:
                current_text = loc.inner_text(timeout=2000).strip()
                if value.strip().lower() in current_text.lower():
                    print(f"  [skip] dropdown already shows correct value: '{current_text}'")
                    return True
            except Exception:
                pass

            # Try native <select> element first — fastest and most reliable
            try:
                tag = loc.evaluate("el => el.tagName.toLowerCase()", timeout=2000)
                if tag == "select":
                    try:
                        loc.select_option(label=value, timeout=3000)
                    except Exception:
                        # Try partial match on option text
                        options = loc.evaluate(
                            "el => Array.from(el.options).map(o => o.text)"
                        )
                        best = next((o for o in options if value.lower() in o.lower()), None)
                        if best:
                            loc.select_option(label=best, timeout=3000)
                        else:
                            loc.select_option(index=1, timeout=3000)  # pick first non-empty
                    _random_delay(0.5)
                    return True
            except Exception:
                pass

            # Custom dropdown (Workday-style): click to open, clear, type, pick option
            loc.click(timeout=5000)
            _random_delay(0.5)

            # Clear any existing text before typing (prevents "UnitedStatesUnitedStates")
            try:
                inner_input = page.locator("input:focus").first
                inner_input.fill("", timeout=1000)
            except Exception:
                pass
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            _random_delay(0.3)

            page.keyboard.type(value, delay=60)
            _random_delay(0.8)
            # Click best matching option
            for option_sel in [
                f"[role='option']:has-text('{value}')",
                f"li[role='option']:has-text('{value}')",
                f"[data-automation-id*='option']:has-text('{value}')",
            ]:
                try:
                    page.locator(option_sel).first.click(timeout=3000)
                    break
                except Exception:
                    pass
            else:
                page.keyboard.press("Enter")
            _random_delay(0.5)

        elif act == "upload":
            loc.set_input_files(value, timeout=8000)
            _random_delay(2.0)

        elif act == "check":
            loc.check(timeout=5000)
            _random_delay(0.4)

        return True

    except Exception as e:
        print(f"  [exec error] {act} on '{selector}': {e}")
        return False


# --------------------------------------------------------------------------- #
# Screenshot helper
# --------------------------------------------------------------------------- #
def take_screenshot(page: Page) -> str:
    """Take a screenshot and return it as base64."""
    img_bytes = page.screenshot(type="jpeg", quality=75)
    return base64.b64encode(img_bytes).decode("utf-8")


# --------------------------------------------------------------------------- #
# DOM element extractor — gives GPT real selectors to use
# --------------------------------------------------------------------------- #
_DOM_EXTRACT_JS = """
() => {
  function vis(el) {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && window.getComputedStyle(el).display !== 'none';
  }
  function attrs(el) {
    const a = {};
    for (const name of ['id','name','type','placeholder','aria-label','data-automation-id','role','value']) {
      const v = el.getAttribute(name) || el[name] || '';
      if (v) a[name] = String(v).substring(0, 80);
    }
    return a;
  }
  const out = [];

  // Native inputs
  document.querySelectorAll('input:not([type=hidden]),textarea').forEach(el => {
    if (!vis(el)) return;
    const a = attrs(el);
    out.push({ kind: 'input', ...a, current: (el.value||'').substring(0,60) });
  });

  // Native selects
  document.querySelectorAll('select').forEach(el => {
    if (!vis(el)) return;
    const a = attrs(el);
    const opts = Array.from(el.options).map(o => o.text.trim()).filter(Boolean).slice(0,30);
    out.push({ kind: 'select', ...a, options: opts, current: el.options[el.selectedIndex]?.text||'' });
  });

  // Buttons
  document.querySelectorAll('button,[type=submit],[role=button]').forEach(el => {
    if (!vis(el)) return;
    const a = attrs(el);
    const text = (el.innerText||el.value||'').trim().replace(/\\s+/g,' ').substring(0,60);
    if (text) out.push({ kind: 'button', text, ...a });
  });

  // Custom comboboxes / dropdowns
  document.querySelectorAll('[role=combobox],[role=listbox],[aria-haspopup=listbox]').forEach(el => {
    if (!vis(el)) return;
    const a = attrs(el);
    const current = (el.innerText||el.textContent||'').trim().replace(/\\s+/g,' ').substring(0,60);
    out.push({ kind: 'combobox', ...a, current });
  });

  return out.slice(0, 80);
}
"""


def get_page_elements(page: Page) -> str:
    """Extract interactive DOM elements and format them as a concise list for GPT."""
    try:
        elements = page.evaluate(_DOM_EXTRACT_JS)
    except Exception:
        return "(could not extract DOM elements)"

    lines = ["INTERACTIVE PAGE ELEMENTS (use these exact attributes for selectors):"]
    for el in elements:
        kind = el.pop("kind", "?")
        current = el.pop("current", "")
        opts = el.pop("options", None)

        # Build a concise selector hint
        parts = []
        for key in ["id", "name", "data-automation-id", "aria-label", "placeholder", "type", "role"]:
            v = el.get(key, "")
            if v:
                parts.append(f'{key}="{v}"')

        selector_hint = " ".join(parts) if parts else "(no attrs)"
        line = f"  [{kind}] {selector_hint}"
        if current:
            line += f"  →currently: \"{current}\""
        if opts:
            line += f"  options={opts[:15]}"  # show up to 15 options
        if kind == "button":
            line = f"  [button] text=\"{el.get('text','')}\" {selector_hint}"
        lines.append(line)

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Vision call
# --------------------------------------------------------------------------- #
def ask_vision(client: OpenAI, model: str, screenshot_b64: str,
               context: str) -> dict:
    """Send screenshot + context to GPT-4o Vision, return parsed action dict."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=500,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": context},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{screenshot_b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if GPT wraps in ```json
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract JSON object from raw text
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {"action": "pause", "reason": f"Could not parse GPT response: {raw}",
                "observation": "", "selector": "", "selector_type": "css", "value": ""}


# --------------------------------------------------------------------------- #
# Main vision applicator
# --------------------------------------------------------------------------- #
class VisionApplicator(BaseApplicator):
    """
    Portal-agnostic applicator driven by GPT-4o Vision.
    Works on any job portal without hardcoded selectors.
    """

    MAX_STEPS = 40

    def __init__(self, config: AppConfig):
        self.config = config
        self.client = OpenAI(api_key=config.env.openai_api_key)

    def apply(self, job: Job, docs: TailoredDocuments, confirm: bool = True) -> ApplicationResult:
        cfg = self.config
        screenshot_path = None
        action_log = []
        consecutive_failures = 0

        # Resolve start URL
        start_url = self._resolve_start_url(job)
        print(f"\n  [vision] Opening: {job.company} — {job.role}")
        print(f"  [vision] URL: {start_url}\n")

        try:
            with get_browser(cfg, headless=False) as context:
                page = context.new_page()
                page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                _random_delay(3.0)

                for step in range(self.MAX_STEPS):
                    # Take screenshot + extract real DOM elements
                    screenshot_b64 = take_screenshot(page)
                    page_elements = get_page_elements(page)

                    # Build context string
                    resume_path = docs.resume_path or cfg.env.resume_path
                    context_str = USER_PROMPT_TEMPLATE.format(
                        role=job.role,
                        company=job.company,
                        url=page.url,
                        name=cfg.env.applicant_name,
                        email=cfg.env.applicant_email,
                        phone=cfg.env.applicant_phone or "not provided",
                        address=cfg.env.applicant_address or "not provided",
                        city=cfg.env.applicant_city or "",
                        zip=cfg.env.applicant_zip or "",
                        resume_path=cfg.env.resume_path,
                        tailored_resume_path=resume_path,
                        country_of_residence=cfg.profile.country_of_residence,
                        heard_about_us=cfg.profile.heard_about_us,
                        previously_employed_here="No" if not cfg.profile.previously_employed_here else "Yes",
                        at_least_18="Yes" if cfg.profile.at_least_18 else "No",
                        available_start_date=cfg.profile.available_start_date,
                        hispanic_or_latino="No" if not cfg.profile.hispanic_or_latino else "Yes",
                        ethnicity=cfg.profile.ethnicity,
                        veteran_status=cfg.profile.veteran_status,
                        self_id_language=cfg.profile.self_id_language,
                        action_log="\n".join(action_log[-10:]) or "none yet",
                        page_elements=page_elements,
                    )

                    # Ask GPT-4o Vision
                    print(f"  [step {step+1}] asking GPT-4o Vision...")
                    action = ask_vision(self.client, cfg.ai.model, screenshot_b64, context_str)

                    obs = action.get("observation", "")
                    act = action.get("action", "wait")
                    reason = action.get("reason", "")
                    selector = action.get("selector", "")
                    value = action.get("value", "")

                    sel_type_log = action.get("selector_type", "css")
                    print(f"  [step {step+1}] {act.upper()} | {obs}")
                    if reason:
                        print(f"             reason: {reason}")
                    if selector:
                        print(f"             target [{sel_type_log}]: {selector}" + (f" = '{value}'" if value else ""))

                    # Handle terminal states
                    if act == "done":
                        print("\n  [✓] Vision agent says application is complete!")
                        screenshot_path = self._save_screenshot(page, job.company)
                        action_log.append(f"Step {step+1}: done — {obs}")
                        break

                    if act == "pause":
                        print(f"\n  [!] Vision agent needs human help: {reason}")
                        input("  Handle this in the browser, then press Enter to continue > ")
                        action_log.append(f"Step {step+1}: pause — human intervened")
                        consecutive_failures = 0
                        continue

                    # Execute the action
                    success = execute_action(page, action, cfg.browser.typing_delay)

                    if success:
                        action_log.append(f"Step {step+1}: {act} '{selector}' = '{value}' ✓ — {obs}")
                        consecutive_failures = 0
                    else:
                        action_log.append(
                            f"Step {step+1}: {act} '{selector}' = '{value}' ✗ FAILED — {obs} "
                            f"[selector did not work, try a completely different selector_type or approach]"
                        )
                        consecutive_failures += 1
                        print(f"  [warn] Action failed ({consecutive_failures} in a row)")

                        # After 5 consecutive failures, scroll the page to reveal hidden elements
                        if consecutive_failures == 3:
                            print("  [auto] Scrolling page to reveal more elements...")
                            try:
                                page.evaluate("window.scrollBy(0, 400)")
                            except Exception:
                                pass
                            _random_delay(1.5)
                        elif consecutive_failures >= 6:
                            # Too many failures — scroll back to top and reset count
                            print("  [auto] Resetting scroll position and retrying...")
                            try:
                                page.evaluate("window.scrollTo(0, 0)")
                            except Exception:
                                pass
                            consecutive_failures = 0
                            _random_delay(2.0)

                    _random_delay(1.0)

                else:
                    print(f"\n  [!] Reached max steps ({self.MAX_STEPS}).")
                    screenshot_path = self._save_screenshot(page, job.company)

                screenshot_path = screenshot_path or self._save_screenshot(page, job.company)

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

    def _resolve_start_url(self, job: Job) -> str:
        """Get the best apply URL for this job."""
        url = job.url
        # For Workday company career pages, find the actual Workday apply URL
        if "myworkdayjobs.com" in url or "myworkday.com" in url:
            return url
        import httpx
        from bs4 import BeautifulSoup
        try:
            r = httpx.get(url, follow_redirects=True, timeout=15,
                          headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "myworkdayjobs.com" in href and "/apply" in href:
                    return href
        except Exception:
            pass
        return url

    def _save_screenshot(self, page, company: str) -> str:
        path = f"data/screenshots/{company}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=path, full_page=True)
        except Exception:
            pass
        return path
