"""Local browser foundation. Live HH mutations need an independently verified UI flow."""
from pathlib import Path
from urllib.parse import urlencode, urljoin
import re

from .config import settings


class BrowserUnavailable(RuntimeError):
    pass


class BrowserNeedsReview(RuntimeError):
    pass


class HHBrowserAdapter:
    def __init__(self, state_path: str | None = None):
        self.state_path = Path(state_path or settings.browser_state_path)

    @staticmethod
    def _check_page(page, response) -> None:
        if response is None:
            raise BrowserUnavailable("HH page returned no response")
        if response.status in (403, 429) or response.status >= 500:
            raise BrowserNeedsReview(f"HH page blocked or unavailable: HTTP {response.status}")
        if response.status >= 400:
            raise BrowserUnavailable(f"HH page returned HTTP {response.status}")
        if "captcha" in page.url.lower() or "login" in page.url.lower():
            raise BrowserNeedsReview("HH requires CAPTCHA or login")

    def vacancy(self, hh_id: str) -> dict:
        """Read a public vacancy when the API read method is unavailable."""
        if not settings.browser_enabled:
            raise BrowserUnavailable("browser channel is disabled")
        if not hh_id.isdecimal():
            raise ValueError("invalid HH vacancy id")
        from playwright.sync_api import Error as PlaywrightError, sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(self.state_path) if self.state_path.exists() else None,
                    locale="ru-RU",
                )
                page = context.new_page()
                try:
                    response = page.goto(f"https://hh.ru/vacancy/{hh_id}", wait_until="domcontentloaded", timeout=30000)
                    self._check_page(page, response)
                    title = page.title()
                    body = page.locator("body").inner_text(timeout=10000)
                    return {"id": hh_id, "name": title, "description_text": body, "alternate_url": page.url, "source_channel": "browser"}
                finally:
                    context.close()
                    browser.close()
        except PlaywrightError as exc:
            raise BrowserUnavailable("HH browser failed to read vacancy") from exc

    def search(self, text: str, page_number: int = 0) -> dict:
        if not settings.browser_enabled:
            raise BrowserUnavailable("browser channel is disabled")
        from playwright.sync_api import Error as PlaywrightError, sync_playwright

        url = "https://hh.ru/search/vacancy?" + urlencode({"text": text, "page": page_number})
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(self.state_path) if self.state_path.exists() else None,
                    locale="ru-RU",
                )
                page = context.new_page()
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    self._check_page(page, response)
                    items = []
                    seen = set()
                    for anchor in page.locator('a[href*="/vacancy/"]').all():
                        href = anchor.get_attribute("href") or ""
                        match = re.search(r"/vacancy/(\d+)", href)
                        if match and match.group(1) not in seen:
                            seen.add(match.group(1))
                            items.append({"id": match.group(1), "name": anchor.inner_text().strip() or match.group(1), "alternate_url": urljoin(page.url, href), "source_channel": "browser"})
                    return {"items": items}
                finally:
                    context.close()
                    browser.close()
        except PlaywrightError as exc:
            raise BrowserUnavailable("HH browser failed to search") from exc

    def find_application(self, vacancy_id: str, resume_id: str) -> dict | None:
        # Absence cannot safely be inferred from an unverified page or a single list view.
        raise BrowserNeedsReview("HH browser reconciliation is not verified")

    def apply(self, vacancy_id: str, resume_id: str, letter: str) -> dict:
        if not settings.hh_browser_writes_verified:
            raise BrowserNeedsReview("HH browser application flow has not been verified")
        raise BrowserNeedsReview("HH browser submit adapter is not implemented")
