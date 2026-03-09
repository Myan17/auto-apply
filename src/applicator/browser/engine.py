"""Playwright browser session manager."""

import random
import time
from pathlib import Path
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

from ...config import AppConfig


def _random_delay(base_seconds: float):
    """Sleep for base ± 40% to simulate human timing."""
    delta = base_seconds * 0.4
    time.sleep(base_seconds + random.uniform(-delta, delta))


def human_type(page: Page, selector: str, text: str, delay_ms: int = 80):
    """Type text with human-like per-character delays."""
    page.click(selector)
    page.type(selector, text, delay=delay_ms)


@contextmanager
def get_browser(config: AppConfig, headless: bool = False):
    """Context manager that yields a configured Playwright browser."""
    session_dir = Path(config.browser.session_path)
    session_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        context: BrowserContext = browser.new_context(
            viewport={
                "width": config.browser.viewport_width,
                "height": config.browser.viewport_height,
            },
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            storage_state=str(session_dir / "state.json")
            if (session_dir / "state.json").exists()
            else None,
        )

        # Hide automation fingerprint
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        try:
            yield context
        finally:
            browser.close()
