"""Real browser test (Playwright, headless Chromium) against the checkout
form. Expected to PASS - this is the happy path working correctly.
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("CHECKOUT_APP_URL", "http://127.0.0.1:8420")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/checkout.html")

        page.fill("#email", "customer@example.com")
        page.fill("#amount", "150")
        page.click("#submit")
        page.wait_for_timeout(300)

        result_text = page.inner_text("#result")
        browser.close()

        if "Order placed" not in result_text:
            print(f"assertion failed: expected 'Order placed' in result, got {result_text!r}", file=sys.stderr)
            sys.exit(1)

        print(f"OK: {result_text}")


if __name__ == "__main__":
    main()
