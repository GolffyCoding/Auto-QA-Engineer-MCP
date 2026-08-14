"""
End-to-end qa_mcp demo: scan this sample app, generate a deterministic test
suite for its checkout feature, run a handful of real tests against it
(browser + API + database), and produce a full report - including two
intentional bugs in app.py so the report has real failures with real root
causes to show, not just a wall of green.

Run from the repo root:
    python3 sample-apps/checkout-demo/run_demo.py
"""
import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

DEMO_DIR = Path(__file__).parent
REPO_ROOT = DEMO_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from qa_mcp.mcp_server import QAMCPServer  # noqa: E402

APP_PORT = 8420
APP_URL = f"http://127.0.0.1:{APP_PORT}"

TESTS = [
    ("checkout-form-happy-path", "test_checkout_form_browser.py"),
    ("checkout-api-valid-order", "test_checkout_api_valid.py"),
    ("checkout-api-coupon-exceeds-amount", "test_checkout_negative_total_bug.py"),
    ("orders-api-404-for-missing-order", "test_orders_api_404_bug.py"),
    ("db-orders-fk-integrity", "test_db_fk_integrity.py"),
]


def start_app_server():
    sys.path.insert(0, str(DEMO_DIR))
    import app as demo_app

    server = demo_app.run(APP_PORT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def main():
    print(f"=== qa_mcp demo: checkout-demo ===\n")

    # 1. Seed the intentionally-broken database
    subprocess.run([sys.executable, str(DEMO_DIR / "seed_db.py")], check=True)

    # 2. Start the sample app (real HTTP server, real bugs included)
    server = start_app_server()
    print(f"1. Sample app running at {APP_URL} (2 intentional bugs included)\n")

    s = QAMCPServer()

    # 3. Understand: scan the sample app
    profile = await s.call("project.scan", project_path=str(DEMO_DIR))
    print(f"2. project.scan -> language={profile['language']}, name={profile['name']}\n")

    # 4. Design: generate the deterministic test suite for "checkout" -
    #    this is what an agent SHOULD be running, not just the 5 hand-picked
    #    tests below. Saved to disk so you can see the full suite qa_mcp
    #    would generate from these facts.
    suite = await s.call("test.generate", feature="checkout", fields=[
        {"name": "email", "type": "email", "required": True},
        {"name": "amount", "type": "number", "required": True},
        {"name": "coupon_code", "type": "text", "required": False, "max_length": 20},
    ], business_rules=[
        {"name": "no-negative-total", "rule": "order total must never go below 0",
         "violation": "Apply a coupon larger than the order amount"},
    ])
    suite_path = DEMO_DIR / "generated-test-cases.json"
    suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False))
    print(f"3. test.generate -> {suite['total']} deterministic test cases -> {suite_path.name}\n")

    # 5. Execute: run a representative slice of real tests (the negative-
    #    total and 404 cases below are exactly the kind of case
    #    test.generate's business_rules/fields dimensions produce - here
    #    they're run by hand against this sample app to keep the demo fast)
    run = await s.call("test.create_run", suite_name="checkout-demo")
    run_id = run["run_id"]
    print(f"4. test.create_run -> {run_id}\n")

    print("5. Running tests:")
    for test_id, script in TESTS:
        result = await s.call(
            "test.run", test_id=test_id,
            command=[sys.executable, str(DEMO_DIR / "tests" / script)],
            env={"CHECKOUT_APP_URL": APP_URL},
        )
        icon = "PASS" if result["status"] == "passed" else "FAIL"
        print(f"   [{icon}] {test_id}")
    print()

    # 6. Report: generate the full HTML report with root-cause diagnosis
    #    and executive summary for anything that failed
    html_report = await s.call("report.generate_html", run_id=run_id)
    report = await s.call("report.generate", run_id=run_id)

    print("6. report.generate_html ->", html_report["path"])
    print()
    print("=== Executive Summary ===")
    print(report["executive_summary"]["headline"])
    for risk in report["executive_summary"]["top_risks"]:
        print(f"  [{risk['severity']}] {risk['test_name']} ({risk['category']}): {risk['root_cause']}")

    server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
