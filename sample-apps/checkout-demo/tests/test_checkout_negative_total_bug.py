"""Business-logic test: applying a coupon larger than the order amount
must never be allowed to produce a negative total. This is exactly the
kind of case test.generate's `business_rules` dimension exists to catch
(see run_demo.py) - it is EXPECTED TO FAIL, demonstrating BUG 1 in app.py
(no floor at 0 on the discounted total).
"""
import os
import sys

import httpx

BASE_URL = os.environ.get("CHECKOUT_APP_URL", "http://127.0.0.1:8420")


def main():
    resp = httpx.post(
        f"{BASE_URL}/api/checkout",
        json={"email": "customer@example.com", "amount": 100, "coupon_code": "HUGE1000"},
    )
    body = resp.json()
    total = body.get("total")

    if total is None or total < 0:
        print(
            f"assertion failed: expected order total >= 0 (coupon discount should be "
            f"capped at the order amount), but got {total}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"OK: total={total}")


if __name__ == "__main__":
    main()
