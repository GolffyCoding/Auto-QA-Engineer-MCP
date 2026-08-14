"""
End-to-end qa_mcp demo #2: a small internal task-tracker app with login,
roles, and a task state machine - exercises test.generate's `roles` and
`states` dimensions, which checkout-demo (sample-apps/checkout-demo)
doesn't touch. Same pattern as checkout-demo: real bugs left in on
purpose, real tests run against a real (if tiny) app, a real report at
the end.

Run from the repo root:
    python3 sample-apps/task-manager/run_demo.py
"""
import asyncio
import json
import os
import sys
import threading
from pathlib import Path

DEMO_DIR = Path(__file__).parent
REPO_ROOT = DEMO_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from qa_mcp.mcp_server import QAMCPServer  # noqa: E402

APP_PORT = 8421
APP_URL = f"http://127.0.0.1:{APP_PORT}"

TESTS = [
    ("dashboard-login-browser", "test_login_dashboard_browser.py"),
    ("login-rejects-wrong-password", "test_login_invalid_credentials.py"),
    ("task-state-machine-valid-path", "test_task_state_machine_valid.py"),
    ("task-skip-state-transition", "test_task_skip_state_bug.py"),
    ("delete-requires-owner-or-admin", "test_delete_access_control_bug.py"),
]


def start_app_server():
    sys.path.insert(0, str(DEMO_DIR))
    import app as demo_app

    server = demo_app.run(APP_PORT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def main():
    print("=== qa_mcp demo: task-manager ===\n")

    server = start_app_server()
    print(f"1. Sample app running at {APP_URL} (2 intentional bugs included)\n")

    s = QAMCPServer()

    profile = await s.call("project.scan", project_path=str(DEMO_DIR))
    print(f"2. project.scan -> language={profile['language']}, name={profile['name']}\n")

    # This app has roles and a real state machine, so this demo generates
    # from those dimensions too (not just fields, like checkout-demo does) -
    # showing the same test.generate call covering fields + roles + states
    # together in one suite.
    suite = await s.call(
        "test.generate", feature="task-management",
        fields=[{"name": "title", "type": "text", "required": True, "max_length": 200}],
        roles=[
            {"role": "admin", "should_access": True},
            {"role": "member", "should_access": False},
        ],
        states={
            "initial": "todo",
            "transitions": [
                {"from": "todo", "to": "in_progress", "action": "start"},
                {"from": "in_progress", "to": "done", "action": "complete"},
                {"from": "done", "to": "todo", "action": "reopen"},
            ],
        },
    )
    suite_path = DEMO_DIR / "generated-test-cases.json"
    suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False))
    print(f"3. test.generate -> {suite['total']} deterministic test cases (fields + roles + states) -> {suite_path.name}\n")

    run = await s.call("test.create_run", suite_name="task-manager-demo")
    run_id = run["run_id"]
    print(f"4. test.create_run -> {run_id}\n")

    print("5. Running tests:")
    for test_id, script in TESTS:
        result = await s.call(
            "test.run", test_id=test_id,
            command=[sys.executable, str(DEMO_DIR / "tests" / script)],
            env={"TASK_APP_URL": APP_URL},
        )
        icon = "PASS" if result["status"] == "passed" else "FAIL"
        print(f"   [{icon}] {test_id}")
    print()

    html_report = await s.call("report.generate_html", run_id=run_id)
    pdf_report = await s.call("report.generate_pdf", run_id=run_id)
    report = await s.call("report.generate", run_id=run_id)

    print("6. report.generate_html ->", html_report["path"])
    print("   report.generate_pdf  ->", pdf_report["path"])
    print()
    print("=== Executive Summary ===")
    print(report["executive_summary"]["headline"])
    for risk in report["executive_summary"]["top_risks"]:
        print(f"  [{risk['severity']}] {risk['test_name']} ({risk['category']}): {risk['root_cause']}")

    server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
