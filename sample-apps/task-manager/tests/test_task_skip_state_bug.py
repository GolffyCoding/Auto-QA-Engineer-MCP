"""State-machine test: a task must not be able to go straight from "todo"
to "done" - it has to pass through "in_progress" first, per the declared
state machine. EXPECTED TO FAIL - demonstrates BUG 1 in app.py (the
"complete" action is accepted from any state, not just "in_progress").

This is exactly the kind of case test.generate's `states` dimension exists
to catch automatically and exhaustively (see run_demo.py) - here it's run
by hand against this sample app to keep the demo fast.
"""
import os
import sys

import httpx

BASE_URL = os.environ.get("TASK_APP_URL", "http://127.0.0.1:8421")


def main():
    login = httpx.post(f"{BASE_URL}/api/login", json={"username": "alice", "password": "admin123"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    task = httpx.post(f"{BASE_URL}/api/tasks", json={"title": "Skip-state task"}, headers=headers).json()
    task_id = task["id"]
    assert task["state"] == "todo"

    resp = httpx.post(f"{BASE_URL}/api/tasks/{task_id}/transition", json={"action": "complete"}, headers=headers)
    body = resp.json()

    if resp.status_code != 400:
        print(
            f"assertion failed: expected HTTP 400 (invalid transition 'complete' from state "
            f"'todo'), but got HTTP {resp.status_code} with state now {body.get('state')!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("OK: skip-state transition correctly rejected")


if __name__ == "__main__":
    main()
