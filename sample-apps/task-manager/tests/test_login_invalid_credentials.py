"""API test: logging in with a wrong password must be rejected. Expected
to PASS - this validation works correctly.
"""
import os
import sys

import httpx

BASE_URL = os.environ.get("TASK_APP_URL", "http://127.0.0.1:8421")


def main():
    resp = httpx.post(f"{BASE_URL}/api/login", json={"username": "alice", "password": "wrong-password"})
    if resp.status_code != 401:
        print(f"assertion failed: expected HTTP 401 but got HTTP {resp.status_code}", file=sys.stderr)
        sys.exit(1)
    print("OK: invalid credentials rejected")


if __name__ == "__main__":
    main()
