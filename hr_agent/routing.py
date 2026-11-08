"""Choose an allowed execution channel without treating transient failures as fallback permission."""
import httpx

from .browser import BrowserNeedsReview, BrowserUnavailable, HHBrowserAdapter
from .config import settings
from .hh import HHClient


class OperationBlocked(RuntimeError):
    pass


class OperationUnknown(RuntimeError):
    pass


def classify_api_error(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    try:
        payload = exc.response.json()
    except ValueError:
        payload = {}
    errors = payload.get("errors", []) if isinstance(payload, dict) else []
    types = {error.get("type") for error in errors if isinstance(error, dict)}
    if status in (405, 501) or types.intersection({"access_denied", "not_supported", "test_required"}):
        return "unsupported"
    if status == 401:
        return "reauthorize"
    if status == 429:
        return "rate_limited"
    if status == 403:
        return "blocked"
    if status >= 500:
        return "unknown"
    return "failed"


class HHOperationRouter:
    def __init__(self, api: HHClient | None = None, browser: HHBrowserAdapter | None = None):
        self.api = api or HHClient()
        self.browser = browser or HHBrowserAdapter()
        self.last_channel: str | None = None

    def vacancy(self, hh_id: str) -> dict:
        try:
            result = self.api.vacancy(hh_id)
            self.last_channel = "api"
            return result
        except httpx.HTTPStatusError as exc:
            reason = classify_api_error(exc)
            if reason != "unsupported":
                raise OperationBlocked(reason) from exc
        except httpx.TransportError as exc:
            # A read can be attempted through the browser; no external mutation occurred.
            if not settings.browser_enabled:
                raise OperationBlocked("api_unreachable") from exc
        if not settings.browser_enabled:
            raise OperationBlocked("no_available_channel")
        self.last_channel = "browser"
        return self.browser.vacancy(hh_id)

    def search(self, text: str, page: int = 0) -> dict:
        try:
            result = self.api.search(text, page)
            self.last_channel = "api"
            return result
        except httpx.HTTPStatusError as exc:
            reason = classify_api_error(exc)
            if reason not in ("unsupported", "reauthorize"):
                raise OperationBlocked(reason) from exc
        except httpx.TransportError as exc:
            if not settings.browser_enabled:
                raise OperationBlocked("api_unreachable") from exc
        if not settings.browser_enabled:
            raise OperationBlocked("no_available_channel")
        self.last_channel = "browser"
        return self.browser.search(text, page)

    def find_application(self, vacancy_id: str, resume_id: str) -> dict | None:
        if settings.hh_access_token:
            try:
                result = self.api.find_application(vacancy_id, resume_id)
                self.last_channel = "api"
                return result
            except httpx.HTTPStatusError as exc:
                if classify_api_error(exc) != "unsupported":
                    raise OperationBlocked(classify_api_error(exc)) from exc
            except httpx.TransportError as exc:
                raise OperationUnknown("reconciliation_unavailable") from exc
        if not settings.browser_enabled:
            raise OperationBlocked("reconciliation_unavailable")
        self.last_channel = "browser"
        return self.browser.find_application(vacancy_id, resume_id)

    def apply(self, vacancy_id: str, resume_id: str, letter: str) -> dict:
        if settings.hh_access_token and not settings.hh_api_verified and not settings.hh_api_apply_unavailable:
            raise OperationBlocked("api_apply_capability_unverified")
        if settings.hh_access_token and settings.hh_api_verified:
            try:
                self.last_channel = "api"
                return self.api.apply(vacancy_id, resume_id, letter)
            except httpx.HTTPStatusError as exc:
                reason = classify_api_error(exc)
                if reason != "unsupported":
                    if reason == "unknown":
                        raise OperationUnknown(reason) from exc
                    raise OperationBlocked(reason) from exc
            except httpx.TransportError as exc:
                raise OperationUnknown("api_result_unknown") from exc
        if not settings.browser_enabled:
            raise OperationBlocked("no_available_channel")
        self.last_channel = "browser"
        return self.browser.apply(vacancy_id, resume_id, letter)
