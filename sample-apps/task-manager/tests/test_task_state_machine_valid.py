"""API test: the declared state machine's valid path (todo -> in_progress
-> done via "start" then "complete") must work. Expected to PASS.
"""
import os
import sys

import httpx

BASE_URL = os.environ.get("TASK_APP_URL", "http://127.0.0.1:8421")


def main():
    login = httpx.post(f"{BASE_URL}/api/login", json={"username": "alice", "password": "admin123"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    task = httpx.post(f"{BASE_URL}/api/tasks", json={"title": "Valid path task"}, headers=headers).json()
    task_id = task["id"]

    started = httpx.post(f"{BASE_URL}/api/tasks/{task_id}/transition", json={"action": "start"}, headers=headers).json()
    if started["state"] != "in_progress":
        print(f"assertion failed: expected state 'in_progress' but got {started['state']!r}", file=sys.stderr)
        sys.exit(1)

    completed = httpx.post(f"{BASE_URL}/api/tasks/{task_id}/transition", json={"action": "complete"}, headers=headers).json()
    if completed["state"] != "done":
        print(f"assertion failed: expected state 'done' but got {completed['state']!r}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: task {task_id} went todo -> in_progress -> done")


if __name__ == "__main__":
    main()
