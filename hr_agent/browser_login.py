"""Interactive, local HH login. The user completes all authentication steps."""
import argparse
import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description="Save an HH browser session after manual login")
    parser.add_argument("--state", type=Path, default=Path("browser_profile/storage_state.json"))
    parser.add_argument("--channel", choices=("chrome", "chromium"), default="chrome")
    args = parser.parse_args()
    state = args.state.resolve()
    state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state.parent, 0o700)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel if args.channel == "chrome" else None, headless=False)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        page.goto("https://hh.ru/", wait_until="domcontentloaded")
        input("Войдите в HH в открытом Chromium, затем нажмите Enter здесь: ")
        if "hh.ru" not in page.url:
            raise RuntimeError("The browser is not on HH")
        fd, temp_name = tempfile.mkstemp(prefix=".storage-state-", dir=state.parent)
        os.close(fd)
        try:
            context.storage_state(path=temp_name)
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, state)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            context.close()
            browser.close()
    print(f"Сессия сохранена в {state}")


if __name__ == "__main__":
    main()
