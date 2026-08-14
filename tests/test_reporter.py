"""Unit tests for qa_mcp.core.reporter - root-cause diagnosis attached to
each failed test, and the deterministic executive summary (severity/risk
rollup) built from those diagnoses. No LLM-authored text: every string in
the executive summary is built from fixed templates and real classification
data, matching this project's fail-fast/no-guessing philosophy elsewhere.
"""
from qa_mcp.core.reporter import ReportGenerator


def _test_run(results):
    total = len(results)
    passed = len([r for r in results if r["status"] == "passed"])
    return {
        "run_id": "run-1",
        "suite_name": "checkout-suite",
        "results": results,
        "pass_rate": round(passed / total * 100, 2) if total else 0,
    }


def _result(test_id, status, stderr="", error_message=None):
    return {
        "test_id": test_id,
        "test_name": test_id,
        "status": status,
        "duration_ms": 10.0,
        "stdout": "",
        "stderr": stderr,
        "exit_code": 0 if status == "passed" else 1,
        "artifacts": [],
        "error_message": error_message,
        "end_time": "",
    }


def test_generate_all_passing_has_no_risk():
    run = _test_run([_result("t1", "passed")])
    report = ReportGenerator().generate(run)

    assert report["executive_summary"]["risk_level"] == "None"
    assert report["failed_tests"] == []
    assert "All 1" in report["executive_summary"]["headline"]


def test_failed_test_gets_real_root_cause_not_generic_message():
    run = _test_run([
        _result("t1", "passed"),
        _result("t2", "failed", stderr="foreign key constraint violation"),
    ])
    report = ReportGenerator().generate(run)

    failed = report["failed_tests"][0]
    assert failed["category"] == "database"
    assert failed["root_cause"] != ""
    assert "FK" in failed["suggested_fix"] or "foreign" in failed["suggested_fix"].lower()


def test_database_failure_is_critical_severity():
    run = _test_run([_result("t1", "failed", stderr="foreign key constraint violation")])
    report = ReportGenerator().generate(run)

    assert report["failed_tests"][0]["severity"] == "Critical"
    assert report["executive_summary"]["risk_level"] == "Critical"


def test_ui_failure_is_medium_severity_not_critical():
    run = _test_run([_result("t1", "failed", stderr="element not found: #submit-btn")])
    report = ReportGenerator().generate(run)

    assert report["failed_tests"][0]["severity"] == "Medium"
    assert report["executive_summary"]["risk_level"] == "Medium"


def test_mixed_severities_risk_level_follows_the_worst_one():
    run = _test_run([
        _result("t1", "failed", stderr="foreign key constraint violation"),  # Critical
        _result("t2", "failed", stderr="element not found: #btn"),  # Medium
    ])
    report = ReportGenerator().generate(run)

    assert report["executive_summary"]["risk_level"] == "Critical"
    assert report["executive_summary"]["failures_by_severity"] == {"Critical": 1, "Medium": 1}


def test_top_risks_are_sorted_critical_first():
    run = _test_run([
        _result("t-ui", "failed", stderr="element not found: #btn"),
        _result("t-db", "failed", stderr="foreign key constraint violation"),
    ])
    report = ReportGenerator().generate(run)

    top_risks = report["executive_summary"]["top_risks"]
    assert top_risks[0]["test_id"] == "t-db"
    assert top_risks[0]["severity"] == "Critical"


def test_headline_mentions_failure_count_and_pass_rate():
    run = _test_run([
        _result("t1", "passed"),
        _result("t2", "failed", stderr="foreign key constraint violation"),
    ])
    report = ReportGenerator().generate(run)

    headline = report["executive_summary"]["headline"]
    assert "1 of 2" in headline
    assert "50.0%" in headline


def test_generate_html_includes_root_cause_and_suggested_fix():
    run = _test_run([_result("t1", "failed", stderr="foreign key constraint violation")])
    report = ReportGenerator().generate(run)
    html = ReportGenerator().generate_html(report)

    assert "Defect Summary" in html
    assert "Backend sends invalid FK value" in html
    assert "Add FK validation" in html


def test_generate_html_all_passing_has_no_defects_and_recommends_release():
    run = _test_run([_result("t1", "passed")])
    report = ReportGenerator().generate(run)
    html = ReportGenerator().generate_html(report)

    assert "No defects found" in html
    assert "RECOMMENDED FOR RELEASE" in html


def test_generate_html_critical_defect_blocks_release_recommendation():
    run = _test_run([_result("t1", "failed", stderr="foreign key constraint violation")])
    report = ReportGenerator().generate(run)
    html = ReportGenerator().generate_html(report)

    assert "NOT RECOMMENDED FOR RELEASE" in html


def test_generate_includes_document_control_metadata():
    run = _test_run([_result("t1", "passed")])
    report = ReportGenerator().generate(
        run, project_name="Acme Checkout", version="2.4.1",
        prepared_by="QA Team", test_environment="Staging - Chrome 120",
        reviewers=["QA Lead", "Engineering Manager"],
    )
    html = ReportGenerator().generate_html(report)

    assert report["document_control"]["project_name"] == "Acme Checkout"
    assert "Acme Checkout" in html
    assert "2.4.1" in html
    assert "Staging - Chrome 120" in html
    assert "QA Lead" in html
    assert "Engineering Manager" in html


def test_generate_document_control_has_sensible_defaults_when_unset():
    run = _test_run([_result("t1", "passed")])
    report = ReportGenerator().generate(run)

    assert report["document_control"]["project_name"] == "checkout-suite"
    assert report["document_control"]["test_environment"] is None


def test_error_status_counted_as_failure_for_risk_purposes():
    run = _test_run([_result("t1", "error", error_message="Test timed out after 30s")])
    report = ReportGenerator().generate(run)

    assert len(report["failed_tests"]) == 1
    assert report["executive_summary"]["risk_level"] != "None"
