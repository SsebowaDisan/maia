from __future__ import annotations

from pathlib import Path
import os
import sys


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(
            "Playwright is not installed. Run `pip install playwright` and `playwright install`.",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 1

    profile_dir = Path(
        os.getenv("AGENT_GMAIL_PLAYWRIGHT_PROFILE_DIR", ".maia_agent/playwright/gmail_profile")
    ).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"Using Playwright Gmail profile: {profile_dir}")
    print("Opening Gmail. Sign in manually if prompted.")
    print("After inbox loads, press ENTER in this terminal to close and save the session.")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1366, "height": 860},
            slow_mo=50,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded", timeout=45000)
        try:
            input()
        finally:
            context.close()
    print("Gmail desktop session stored. You can now run live Gmail theater actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
