"""
Sample app #2 for demonstrating qa_mcp: a small internal task tracker with
login, roles (admin/member), and a task state machine - closer to what a
real internal tool looks like than checkout-demo's single form, so it can
exercise test.generate's `roles` and `states` dimensions (checkout-demo
only exercises `fields` and `business_rules`).

Still stdlib-only (http.server), in-memory data, zero extra dependencies.

Two seeded users:
  alice / admin123   (role: admin)
  bob   / member123  (role: member)

Task state machine (intended):
  todo -> in_progress   via action "start"
  in_progress -> done   via action "complete"
  done -> todo          via action "reopen"

Two INTENTIONAL bugs, left in on purpose so the demo report has real
findings to show:

  BUG 1 (state machine): the "complete" action sets a task straight to
  "done" regardless of its current state, so a task can go directly from
  "todo" to "done" without ever passing through "in_progress" - the state
  machine's own declared transitions aren't enforced server-side.

  BUG 2 (access control): DELETE /api/tasks/<id> doesn't check the
  caller's role or task ownership - any authenticated user, including a
  non-admin who doesn't own the task, can delete someone else's task.
"""
import json
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

USERS = {
    "alice": {"password": "admin123", "role": "admin"},
    "bob": {"password": "member123", "role": "member"},
}
SESSIONS = {}  # token -> username
TASKS = {}  # id -> task dict

STATIC_DIR = Path(__file__).parent


def _seed_task(title, assignee, owner, state="todo"):
    task_id = uuid.uuid4().hex[:8]
    TASKS[task_id] = {"id": task_id, "title": title, "assignee": assignee, "owner": owner, "state": state}
    return task_id


_seed_task("Write onboarding docs", assignee="bob", owner="alice")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def _current_user(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[len("Bearer "):]
        username = SESSIONS.get(token)
        return {"username": username, **USERS[username]} if username else None

    def do_GET(self):
        if self.path in ("/", "/dashboard.html"):
            content = (STATIC_DIR / "dashboard.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if self.path == "/api/tasks":
            user = self._current_user()
            if not user:
                self._json(401, {"error": "not authenticated"})
                return
            self._json(200, {"tasks": list(TASKS.values())})
            return

        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/login":
            body = self._read_json()
            if body is None:
                self._json(400, {"error": "malformed JSON body"})
                return
            username, password = body.get("username"), body.get("password")
            user = USERS.get(username)
            if not user or user["password"] != password:
                self._json(401, {"error": "invalid credentials"})
                return
            token = uuid.uuid4().hex
            SESSIONS[token] = username
            self._json(200, {"token": token, "role": user["role"]})
            return

        if self.path == "/api/tasks":
            user = self._current_user()
            if not user:
                self._json(401, {"error": "not authenticated"})
                return
            body = self._read_json()
            if not body or not body.get("title"):
                self._json(400, {"error": "title is required"})
                return
            task_id = _seed_task(body["title"], body.get("assignee", user["username"]), owner=user["username"])
            self._json(201, TASKS[task_id])
            return

        if self.path.startswith("/api/tasks/") and self.path.endswith("/transition"):
            user = self._current_user()
            if not user:
                self._json(401, {"error": "not authenticated"})
                return
            task_id = self.path.split("/")[3]
            task = TASKS.get(task_id)
            if not task:
                self._json(404, {"error": "task not found"})
                return
            body = self._read_json() or {}
            action = body.get("action")

            valid_transitions = {
                ("todo", "start"): "in_progress",
                ("in_progress", "complete"): "done",
                ("done", "reopen"): "todo",
            }
            key = (task["state"], action)
            if key in valid_transitions:
                task["state"] = valid_transitions[key]
                self._json(200, task)
                return

            # BUG 1: "complete" is accepted from ANY state, not just
            # "in_progress" - the declared state machine above is bypassed.
            if action == "complete":
                task["state"] = "done"
                self._json(200, task)
                return

            self._json(400, {"error": f"invalid transition: '{action}' from state '{task['state']}'"})
            return

        self._json(404, {"error": "not found"})

    def do_DELETE(self):
        if self.path.startswith("/api/tasks/"):
            user = self._current_user()
            if not user:
                self._json(401, {"error": "not authenticated"})
                return
            task_id = self.path.split("/")[3]
            if task_id not in TASKS:
                self._json(404, {"error": "task not found"})
                return

            # BUG 2: should require `user["role"] == "admin" or task["owner"] == user["username"]`
            # but deletes unconditionally for any authenticated user.
            del TASKS[task_id]
            self._json(200, {"deleted": task_id})
            return

        self._json(404, {"error": "not found"})


def run(port=0):
    server = HTTPServer(("127.0.0.1", port), Handler)
    return server


if __name__ == "__main__":
    server = run(8421)
    print("task-manager running at http://127.0.0.1:8421")
    server.serve_forever()
