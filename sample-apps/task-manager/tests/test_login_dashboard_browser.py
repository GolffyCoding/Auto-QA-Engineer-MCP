"""Real browser test (Playwright, headless Chromium): log in as alice and
confirm the dashboard shows the seeded task. Expected to PASS.
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("TASK_APP_URL", "http://127.0.0.1:8421")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/dashboard.html")

        page.click("#login-btn")
        page.wait_for_selector("#welcome:has-text('alice')", timeout=5000)

        welcome_text = page.inner_text("#welcome")
        task_items = page.locator("#task-list li").count()
        browser.close()

        if "alice" not in welcome_text or "admin" not in welcome_text:
            print(f"assertion failed: expected welcome text to mention alice/admin, got {welcome_text!r}", file=sys.stderr)
            sys.exit(1)
        if task_items < 1:
            print(f"assertion failed: expected at least 1 task in the list, got {task_items}", file=sys.stderr)
            sys.exit(1)

        print(f"OK: {welcome_text}, {task_items} task(s) shown")


if __name__ == "__main__":
    main()
