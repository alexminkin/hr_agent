from playwright.sync_api import sync_playwright


def test_local_chromium_starts():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto("data:text/html,<title>ready</title>")
            assert page.title() == "ready"
        finally:
            browser.close()
