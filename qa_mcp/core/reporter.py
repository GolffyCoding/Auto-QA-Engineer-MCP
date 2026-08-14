"""
Core: ReportGenerator - produces a real Test Summary Report (the document
shape a QA team actually files/sends: document control, scope, test
environment, summary metrics, defect details, a release recommendation,
and a sign-off block) instead of a bare CI pass/fail table.
"""
import os
from collections import Counter
from typing import Dict, List, Optional, Any
from datetime import datetime


# Severity tier ต่อ failure category (จาก qa_mcp.failure_analysis.analyzer.
# FailureAnalyzer.ERROR_PATTERNS) - ใช้จัดลำดับความสำคัญใน executive summary
# ไม่ใช่ทุก failure สำคัญเท่ากัน: bug ที่ auth/database/security คือความเสี่ยง
# ทางธุรกิจจริง (ข้อมูลรั่ว/เสีย) ส่วน ui/browser มักเป็นแค่ selector เปลี่ยน
CRITICAL_CATEGORIES = {"security", "auth", "database"}
HIGH_CATEGORIES = {"api", "logic", "concurrency", "resource", "third_party"}
# ที่เหลือ (validation, ui, browser, network, mobile, configuration,
# filesystem, unknown) ถือเป็น medium/low โดย default


def _severity_of(category: str) -> str:
    if category in CRITICAL_CATEGORIES:
        return "Critical"
    if category in HIGH_CATEGORIES:
        return "High"
    if category == "unknown":
        return "Low"
    return "Medium"


_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

_RECOMMENDATION = {
    "Critical": ("NOT RECOMMENDED FOR RELEASE",
                 "One or more Critical-severity defects were found (auth/database/security). "
                 "These must be resolved and re-verified before this build proceeds."),
    "High": ("NOT RECOMMENDED FOR RELEASE",
             "High-severity defects were found. Resolve and re-verify before this build proceeds, "
             "or obtain an explicit risk acceptance sign-off if release cannot wait."),
    "Medium": ("CONDITIONAL — RELEASE WITH TRACKED DEFECTS",
               "Only Medium/Low-severity defects were found. Not release-blocking on their own, "
               "but should be triaged and tracked to resolution."),
    "None": ("RECOMMENDED FOR RELEASE",
             "All executed tests passed. No open defects from this run."),
}


class ReportGenerator:
    """สร้าง Test Summary Report แบบมาตรฐาน (document control, scope, test
    environment, summary metrics, defect detail พร้อม root cause, release
    recommendation, sign-off) - ไม่ใช่แค่ pass/fail table
    """

    def _diagnose_failure(self, result: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        """วิเคราะห์สาเหตุของ failed test ตัวหนึ่งโดยใช้ classification logic
        เดียวกับ failure_analysis.FailureAnalyzer - เรียกเฉพาะ pure method
        (ไม่เรียก .inspect()) เพื่อไม่ให้การสร้างรายงาน (ควรเป็น read-only)
        มีผลข้างเคียงเขียนลง persistence store โดยไม่มีใครคาดคิด
        """
        from qa_mcp.failure_analysis.analyzer import FailureEvidence, _analyzer

        log_parts = [p for p in (result.get("stdout", ""), result.get("stderr", "")) if p]
        evidence = FailureEvidence(
            failure_id=f"{run_id}-{result['test_id']}",
            test_name=result.get("test_name", result["test_id"]),
            expected="exit code 0 (test passes)",
            actual=result.get("error_message") or f"exit code {result.get('exit_code')}",
            server_log="\n".join(log_parts) or None,
            screenshot=next(
                (a["path"] for a in result.get("artifacts", []) if a.get("type") == "screenshot"),
                None,
            ),
            timestamp=result.get("end_time", ""),
        )
        category = _analyzer._classify(evidence)
        likely_cause = _analyzer._find_likely_cause(evidence, category)
        root_cause = _analyzer._find_root_cause(evidence, category, likely_cause)
        return {
            "category": category,
            "severity": _severity_of(category),
            "root_cause": root_cause,
            "suggested_fix": _analyzer._suggest_fix(category, root_cause),
            "confidence": _analyzer._calculate_confidence(evidence, category),
        }

    def _executive_summary(self, summary: Dict[str, Any], failed_tests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """สรุประดับ business-risk สำหรับคนที่ไม่มีเวลาอ่านตาราง test ทั้งหมด
        (PM/stakeholder) - deterministic ทั้งหมด ไม่ใช่ text ที่ LLM แต่งขึ้นเอง
        """
        by_category = Counter(t["category"] for t in failed_tests)
        by_severity = Counter(t["severity"] for t in failed_tests)

        if by_severity.get("Critical"):
            risk_level = "Critical"
        elif by_severity.get("High"):
            risk_level = "High"
        elif failed_tests:
            risk_level = "Medium"
        else:
            risk_level = "None"

        top_risks = sorted(
            failed_tests,
            key=lambda t: (_SEVERITY_ORDER.get(t["severity"], 99), -t["confidence"]),
        )[:5]

        total_failures = summary["failed"] + summary["errors"]
        if total_failures == 0:
            headline = f"All {summary['total']} tests passed ({summary['pass_rate']}% pass rate)."
        else:
            critical_count = by_severity.get("Critical", 0)
            critical_note = f", {critical_count} Critical" if critical_count else ""
            headline = (
                f"{total_failures} of {summary['total']} tests failing "
                f"({summary['pass_rate']}% pass rate){critical_note} — risk level: {risk_level}."
            )

        recommendation_title, recommendation_detail = _RECOMMENDATION[risk_level]

        return {
            "risk_level": risk_level,
            "headline": headline,
            "failures_by_severity": dict(by_severity),
            "failures_by_category": dict(by_category),
            "recommendation": recommendation_title,
            "recommendation_detail": recommendation_detail,
            "top_risks": [
                {
                    "test_id": t["test_id"],
                    "test_name": t["test_name"],
                    "severity": t["severity"],
                    "category": t["category"],
                    "root_cause": t["root_cause"],
                }
                for t in top_risks
            ],
        }

    def generate(
        self,
        test_run: Dict[str, Any],
        project_name: Optional[str] = None,
        version: str = "1.0",
        prepared_by: str = "qa_mcp (automated)",
        test_environment: Optional[str] = None,
        reviewers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """สร้าง Test Summary Report จาก test run

        project_name: ชื่อโปรเจกต์/ระบบที่ทดสอบ (แสดงใน document header) -
            default ใช้ suite_name ถ้าไม่ระบุ
        version: version ของ report/build ที่ทดสอบ (ตั้งเองได้ เช่น "2.4.1")
        prepared_by: ชื่อ/ทีมที่ generate report นี้
        test_environment: อธิบาย environment ที่ทดสอบ (เช่น "Staging -
            Chrome 120, Ubuntu 22.04, api.staging.example.com") - ใส่เพื่อ
            ให้คนอ่าน report ย้อนหลังรู้ว่าผลนี้มาจากสภาพแวดล้อมไหน
        reviewers: รายชื่อ/ตำแหน่งคนที่ต้อง sign-off (เช่น ["QA Lead",
            "Engineering Manager"]) - ใส่เป็น blank sign-off line ในรายงาน
            ให้เซ็นจริงหลัง generate (deterministic placeholder ไม่ใช่ signature จริง)
        """
        results = test_run.get("results", [])
        run_id = test_run.get("run_id", "")
        suite_name = test_run.get("suite_name") or "(unnamed suite)"

        passed = [r for r in results if r.get("status") == "passed"]
        failed = [r for r in results if r.get("status") in ("failed", "error")]
        skipped = [r for r in results if r.get("status") == "skipped"]

        summary = {
            "total": len(results),
            "passed": len(passed),
            "failed": len([r for r in results if r.get("status") == "failed"]),
            "errors": len([r for r in results if r.get("status") == "error"]),
            "skipped": len(skipped),
            "pass_rate": test_run.get("pass_rate", 0),
            "duration_ms": sum(r.get("duration_ms", 0) for r in results),
        }

        failed_tests = []
        for r in failed:
            diagnosis = self._diagnose_failure(r, run_id)
            failed_tests.append({
                "test_id": r["test_id"],
                "test_name": r["test_name"],
                "error": r.get("error_message", ""),
                "artifacts": [a["path"] for a in r.get("artifacts", [])],
                **diagnosis,
            })

        detailed_results = [
            {
                "test_id": r["test_id"],
                "test_name": r["test_name"],
                "status": r.get("status", "unknown"),
                "duration_ms": r.get("duration_ms", 0),
            }
            for r in results
        ]

        report_id = f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        return {
            "report_id": report_id,
            "run_id": run_id,
            "suite_name": suite_name,
            "generated_at": datetime.now().isoformat(),
            "document_control": {
                "project_name": project_name or suite_name,
                "version": version,
                "prepared_by": prepared_by,
                "status": "Final",
                "test_environment": test_environment,
                "reviewers": reviewers or [],
            },
            "summary": summary,
            "executive_summary": self._executive_summary(summary, failed_tests),
            "detailed_results": detailed_results,
            "failed_tests": failed_tests,
            "all_results": results,
        }

    def generate_html(self, report: Dict[str, Any]) -> str:
        """สร้าง HTML Test Summary Report แบบมาตรฐาน: document control, scope,
        test environment, summary metrics, detailed results, defect detail
        พร้อม root cause, release recommendation, sign-off
        """
        summary = report["summary"]
        exec_summary = report["executive_summary"]
        doc = report["document_control"]

        risk_class = exec_summary["risk_level"].lower()
        rec_class = "ok" if exec_summary["risk_level"] == "None" else (
            "caution" if exec_summary["risk_level"] == "Medium" else "block"
        )

        severity_rows = "".join(
            f"<tr><td>{sev}</td><td>{count}</td></tr>"
            for sev, count in sorted(
                exec_summary["failures_by_severity"].items(),
                key=lambda kv: _SEVERITY_ORDER.get(kv[0], 99),
            )
        )

        status_class = {"passed": "passed", "failed": "failed", "error": "error", "skipped": "skipped"}
        detailed_rows = "".join(
            f"""<tr>
            <td>{r['test_id']}</td>
            <td>{r['test_name']}</td>
            <td class="{status_class.get(r['status'], '')}">{r['status'].upper()}</td>
            <td>{r['duration_ms']:.0f}ms</td>
        </tr>"""
            for r in report.get("detailed_results", [])
        )

        defect_rows = "".join(
            f"""<tr>
            <td>DEF-{i+1:03d}</td>
            <td>{ft['test_name']}</td>
            <td class="sev-{ft['severity'].lower()}">{ft['severity']}</td>
            <td>{ft['category']}</td>
            <td>{ft['root_cause']}</td>
            <td class="suggested-fix">{ft['suggested_fix']}</td>
        </tr>"""
            for i, ft in enumerate(report.get("failed_tests", []))
        )

        env_row = (
            f"<tr><th>Test Environment</th><td>{doc['test_environment']}</td></tr>"
            if doc.get("test_environment") else ""
        )

        signoff_rows = "".join(
            f"""<tr>
            <td>{role}</td>
            <td class="signoff-blank"></td>
            <td class="signoff-blank"></td>
        </tr>"""
            for role in doc.get("reviewers", [])
        ) or '<tr><td colspan="3">No reviewers specified for this report</td></tr>'

        total_executed = summary["total"] - summary["skipped"]
        scope_text = (
            f"This report summarizes the results of test suite &ldquo;{report['suite_name']}&rdquo; "
            f"(run {report['run_id']}). {total_executed} test case(s) were executed"
            + (f", {summary['skipped']} skipped" if summary["skipped"] else "")
            + f". Categories covered: {', '.join(sorted(set(exec_summary['failures_by_category']))) or 'no failures to categorize'}."
        )

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Test Summary Report - {doc['project_name']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; color: #222; line-height: 1.5; }}
        h1 {{ margin-bottom: 4px; }}
        h2 {{ border-bottom: 2px solid #333; padding-bottom: 4px; margin-top: 32px; }}
        .subtitle {{ color: #555; margin-top: 0; }}
        .doc-control {{ width: 100%; border-collapse: collapse; margin: 16px 0 24px; }}
        .doc-control th {{ text-align: left; background: #eee; color: #222; width: 220px; padding: 8px 12px; border: 1px solid #ccc; }}
        .doc-control td {{ padding: 8px 12px; border: 1px solid #ccc; }}
        .recommendation {{ padding: 20px; border-radius: 8px; margin: 16px 0; border-left: 6px solid #999; }}
        .recommendation.ok {{ background: #eafaf1; border-left-color: #229954; }}
        .recommendation.caution {{ background: #fdf7e3; border-left-color: #b7950b; }}
        .recommendation.block {{ background: #fdecea; border-left-color: #c0392b; }}
        .recommendation h3 {{ margin: 0 0 6px; }}
        .exec-summary {{ padding: 20px; border-radius: 8px; margin-top: 20px; border-left: 6px solid #999; }}
        .exec-summary.critical {{ background: #fdecea; border-left-color: #c0392b; }}
        .exec-summary.high {{ background: #fdf3e7; border-left-color: #d68910; }}
        .exec-summary.medium {{ background: #fdf7e3; border-left-color: #b7950b; }}
        .exec-summary.none {{ background: #eafaf1; border-left-color: #229954; }}
        .passed {{ color: #229954; font-weight: bold; }}
        .failed {{ color: #c0392b; font-weight: bold; }}
        .error {{ color: #d68910; font-weight: bold; }}
        .skipped {{ color: #888; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #333; color: white; }}
        .sev-critical {{ color: #c0392b; font-weight: bold; }}
        .sev-high {{ color: #d68910; font-weight: bold; }}
        .sev-medium {{ color: #b7950b; }}
        .sev-low {{ color: #666; }}
        .suggested-fix {{ font-style: italic; color: #444; }}
        .report-meta {{ color: #666; font-size: 0.9em; margin-top: -6px; margin-bottom: 20px; }}
        .signoff-blank {{ min-width: 160px; }}
        @media print {{
            body {{ margin: 20px; }}
            .exec-summary, .recommendation, .doc-control {{ break-inside: avoid; }}
            tr {{ break-inside: avoid; }}
            @page {{ size: A4; margin: 18mm 14mm; }}
        }}
    </style>
</head>
<body>
    <h1>Test Summary Report</h1>
    <p class="subtitle">{doc['project_name']}</p>
    <p class="report-meta">Report ID: {report['report_id']} &middot; Run: {report['run_id']} &middot; Generated: {report['generated_at']}</p>

    <table class="doc-control">
        <tr><th>Project / System Under Test</th><td>{doc['project_name']}</td></tr>
        <tr><th>Report Version</th><td>{doc['version']}</td></tr>
        <tr><th>Prepared By</th><td>{doc['prepared_by']}</td></tr>
        <tr><th>Status</th><td>{doc['status']}</td></tr>
        {env_row}
    </table>

    <h2>1. Introduction &amp; Scope</h2>
    <p>{scope_text}</p>

    <h2>2. Test Summary</h2>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Total test cases</td><td>{summary['total']}</td></tr>
        <tr><td class="passed">Passed</td><td>{summary['passed']}</td></tr>
        <tr><td class="failed">Failed</td><td>{summary['failed']}</td></tr>
        <tr><td class="error">Errors</td><td>{summary['errors']}</td></tr>
        <tr><td class="skipped">Skipped</td><td>{summary['skipped']}</td></tr>
        <tr><td>Pass rate</td><td>{summary['pass_rate']}%</td></tr>
        <tr><td>Total duration</td><td>{summary['duration_ms']:.0f}ms</td></tr>
    </table>

    <h2>3. Defect Summary</h2>
    <div class="exec-summary {risk_class}">
        <p><strong>{exec_summary['headline']}</strong></p>
        <table>
            <tr><th>Severity</th><th>Count</th></tr>
            {severity_rows or '<tr><td colspan="2">No defects found</td></tr>'}
        </table>
    </div>

    <h2>4. Detailed Test Results</h2>
    <table>
        <tr><th>Test ID</th><th>Name</th><th>Status</th><th>Duration</th></tr>
        {detailed_rows or '<tr><td colspan="4">No tests executed in this run</td></tr>'}
    </table>

    <h2>5. Defect Details</h2>
    <table>
        <tr><th>Defect ID</th><th>Test</th><th>Severity</th><th>Category</th><th>Root Cause</th><th>Suggested Fix</th></tr>
        {defect_rows or '<tr><td colspan="6">No defects found</td></tr>'}
    </table>

    <h2>6. Recommendation</h2>
    <div class="recommendation {rec_class}">
        <h3>{exec_summary['recommendation']}</h3>
        <p>{exec_summary['recommendation_detail']}</p>
    </div>

    <h2>7. Sign-off</h2>
    <table>
        <tr><th>Role</th><th>Name</th><th>Date</th></tr>
        {signoff_rows}
    </table>
</body>
</html>"""
        return html


_reporter = ReportGenerator()


# MCP Tools
async def report_generate(
    run_id: str,
    project_name: Optional[str] = None,
    version: str = "1.0",
    prepared_by: str = "qa_mcp (automated)",
    test_environment: Optional[str] = None,
    reviewers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """MCP tool: report.generate - สร้าง Test Summary Report จาก test run ที่รันไว้
    (ผ่าน test.create_run + test.run/test.rerun) ใช้ได้แม้ run นั้นถูกสร้างใน
    process ก่อนหน้า (persist ไว้แล้ว) - report มี document control, scope,
    test environment, summary metrics, defect detail พร้อม root cause,
    release recommendation (go/no-go), และ sign-off block

    project_name/version/prepared_by/test_environment/reviewers: metadata
    เสริมสำหรับ document header และ sign-off - ไม่ใส่ก็ได้ (มี default ที่ใช้งานได้)
    """
    from qa_mcp.execution.executor import _executor

    run = _executor.get_run_dict(run_id)
    if run is None:
        return {"error": f"Run '{run_id}' not found - เรียก test.create_run แล้ว test.run ก่อน"}
    return _reporter.generate(
        run, project_name=project_name, version=version, prepared_by=prepared_by,
        test_environment=test_environment, reviewers=reviewers,
    )


async def report_generate_html(
    run_id: str,
    output_path: Optional[str] = None,
    project_name: Optional[str] = None,
    version: str = "1.0",
    prepared_by: str = "qa_mcp (automated)",
    test_environment: Optional[str] = None,
    reviewers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """MCP tool: report.generate_html - สร้าง Test Summary Report เป็น HTML แล้ว
    เซฟไฟล์จริงลงดิสก์ (ดู report.generate สำหรับความหมายของ metadata param)
    """
    from qa_mcp.execution.executor import _executor

    run = _executor.get_run_dict(run_id)
    if run is None:
        return {"error": f"Run '{run_id}' not found - เรียก test.create_run แล้ว test.run ก่อน"}

    report = _reporter.generate(
        run, project_name=project_name, version=version, prepared_by=prepared_by,
        test_environment=test_environment, reviewers=reviewers,
    )
    html = _reporter.generate_html(report)

    path = output_path or f"./reports/{report['report_id']}.html"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return {"report_id": report["report_id"], "path": path, "summary": report["summary"],
             "executive_summary": report["executive_summary"]}


async def report_generate_pdf(
    run_id: str,
    output_path: Optional[str] = None,
    project_name: Optional[str] = None,
    version: str = "1.0",
    prepared_by: str = "qa_mcp (automated)",
    test_environment: Optional[str] = None,
    reviewers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """MCP tool: report.generate_pdf - สร้าง Test Summary Report เป็น PDF จริงลง
    ดิสก์ (ไฟล์ที่เอาไปแนบอีเมล/ส่ง stakeholder/เก็บเป็นเอกสารอ้างอิงได้ตรง ๆ
    ไม่ต้องแปลงเอง) ใช้ headless Chromium ของ Playwright (dependency ที่มีอยู่
    แล้วในโปรเจกต์) render HTML report เดียวกับ report.generate_html เป็น PDF
    จริง - ไม่ใช่ screenshot ของหน้าเว็บ แต่เป็น print-to-PDF จริงพร้อม page
    break ที่ถูกต้อง (@page CSS) - ดู report.generate สำหรับความหมายของ
    metadata param
    """
    from qa_mcp.execution.executor import _executor

    run = _executor.get_run_dict(run_id)
    if run is None:
        return {"error": f"Run '{run_id}' not found - เรียก test.create_run แล้ว test.run ก่อน"}

    report = _reporter.generate(
        run, project_name=project_name, version=version, prepared_by=prepared_by,
        test_environment=test_environment, reviewers=reviewers,
    )
    html = _reporter.generate_html(report)

    path = output_path or f"./reports/{report['report_id']}.pdf"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    import tempfile
    from playwright.async_api import async_playwright

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        html_path = f.name

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(f"file://{html_path}")
            await page.pdf(path=path, format="A4", print_background=True,
                            margin={"top": "18mm", "bottom": "18mm", "left": "14mm", "right": "14mm"})
            await browser.close()
    finally:
        os.unlink(html_path)

    return {"report_id": report["report_id"], "path": path, "summary": report["summary"],
             "executive_summary": report["executive_summary"]}
