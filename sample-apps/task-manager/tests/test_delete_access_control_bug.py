"""Access-control test: a non-admin member who does not own a task must
not be able to delete it. EXPECTED TO FAIL - demonstrates BUG 2 in app.py
(DELETE /api/tasks/<id> doesn't check role or ownership at all).

This is exactly the kind of case test.generate's `roles` dimension exists
to catch automatically (see run_demo.py) - here it's run by hand against
this sample app to keep the demo fast.
"""
import os
import sys

import httpx

BASE_URL = os.environ.get("TASK_APP_URL", "http://127.0.0.1:8421")


def main():
    admin_login = httpx.post(f"{BASE_URL}/api/login", json={"username": "alice", "password": "admin123"}).json()
    admin_headers = {"Authorization": f"Bearer {admin_login['token']}"}
    task = httpx.post(f"{BASE_URL}/api/tasks", json={"title": "Alice's task"}, headers=admin_headers).json()
    task_id = task["id"]

    member_login = httpx.post(f"{BASE_URL}/api/login", json={"username": "bob", "password": "member123"}).json()
    member_headers = {"Authorization": f"Bearer {member_login['token']}"}

    resp = httpx.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=member_headers)

    if resp.status_code != 403:
        print(
            f"assertion failed: expected HTTP 403 (member 'bob' must not be able to delete "
            f"a task owned by 'alice'), but got HTTP {resp.status_code}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("OK: unauthorized delete correctly rejected")


if __name__ == "__main__":
    main()
