"""Real HTTP request against POST /api/checkout with valid data. Expected
to PASS.
"""
import os
import sys

import httpx

BASE_URL = os.environ.get("CHECKOUT_APP_URL", "http://127.0.0.1:8420")


def main():
    resp = httpx.post(f"{BASE_URL}/api/checkout", json={"email": "customer@example.com", "amount": 100})
    if resp.status_code != 201:
        print(f"assertion failed: expected HTTP 201 but got HTTP {resp.status_code}", file=sys.stderr)
        sys.exit(1)

    body = resp.json()
    if body["total"] != 100:
        print(f"assertion failed: expected total 100 but got {body['total']}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: order {body['id']} total={body['total']}")


if __name__ == "__main__":
    main()
