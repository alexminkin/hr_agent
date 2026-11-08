import unittest
from unittest.mock import patch

import httpx

from hr_agent.config import settings
from hr_agent.routing import HHOperationRouter, OperationBlocked, OperationUnknown, classify_api_error


def status_error(status: int, payload: dict | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.hh.ru/negotiations")
    response = httpx.Response(status, json=payload or {}, request=request)
    return httpx.HTTPStatusError("HH API error", request=request, response=response)


class StubAPI:
    def __init__(self, result=None, error=None):
        self.result = result or {"id": "42"}
        self.error = error
        self.calls = 0

    def apply(self, *_args):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class StubBrowser:
    def __init__(self):
        self.calls = 0

    def apply(self, *_args):
        self.calls += 1
        return {"id": "browser-42"}


class RoutingTests(unittest.TestCase):
    def test_generic_forbidden_is_blocked(self):
        self.assertEqual(classify_api_error(status_error(403)), "blocked")

    def test_api_success_does_not_open_browser(self):
        api, browser = StubAPI(), StubBrowser()
        router = HHOperationRouter(api, browser)
        with patch.object(settings, "hh_access_token", "token"), patch.object(settings, "hh_api_verified", True):
            self.assertEqual(router.apply("1", "2", "letter"), {"id": "42"})
        self.assertEqual((api.calls, browser.calls, router.last_channel), (1, 0, "api"))

    def test_explicit_access_denial_uses_browser(self):
        api = StubAPI(error=status_error(403, {"errors": [{"type": "access_denied"}]}))
        browser = StubBrowser()
        router = HHOperationRouter(api, browser)
        with patch.object(settings, "hh_access_token", "token"), patch.object(settings, "hh_api_verified", True), patch.object(settings, "browser_enabled", True):
            self.assertEqual(router.apply("1", "2", "letter"), {"id": "browser-42"})
        self.assertEqual((api.calls, browser.calls, router.last_channel), (1, 1, "browser"))

    def test_rate_limit_never_falls_back(self):
        api, browser = StubAPI(error=status_error(429)), StubBrowser()
        router = HHOperationRouter(api, browser)
        with patch.object(settings, "hh_access_token", "token"), patch.object(settings, "hh_api_verified", True):
            with self.assertRaises(OperationBlocked):
                router.apply("1", "2", "letter")
        self.assertEqual(browser.calls, 0)

    def test_unverified_api_capability_does_not_imply_browser_fallback(self):
        api, browser = StubAPI(), StubBrowser()
        router = HHOperationRouter(api, browser)
        with patch.object(settings, "hh_access_token", "token"), patch.object(settings, "hh_api_verified", False), patch.object(settings, "hh_api_apply_unavailable", False):
            with self.assertRaises(OperationBlocked):
                router.apply("1", "2", "letter")
        self.assertEqual((api.calls, browser.calls), (0, 0))

    def test_unknown_post_result_never_falls_back(self):
        request = httpx.Request("POST", "https://api.hh.ru/negotiations")
        api, browser = StubAPI(error=httpx.ReadTimeout("timeout", request=request)), StubBrowser()
        router = HHOperationRouter(api, browser)
        with patch.object(settings, "hh_access_token", "token"), patch.object(settings, "hh_api_verified", True):
            with self.assertRaises(OperationUnknown):
                router.apply("1", "2", "letter")
        self.assertEqual(browser.calls, 0)


if __name__ == "__main__":
    unittest.main()
