"""API test: fetching a nonexistent order must return 404. EXPECTED TO
FAIL - demonstrates BUG 2 in app.py (returns 200 with an empty body
instead).
"""
import os
import sys

import httpx

BASE_URL = os.environ.get("CHECKOUT_APP_URL", "http://127.0.0.1:8420")


def main():
    resp = httpx.get(f"{BASE_URL}/api/orders/does-not-exist")

    if resp.status_code != 404:
        print(f"assertion failed: expected HTTP 404 but got HTTP {resp.status_code}", file=sys.stderr)
        sys.exit(1)

    print("OK: 404 returned for nonexistent order")


if __name__ == "__main__":
    main()
