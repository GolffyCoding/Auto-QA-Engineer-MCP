"""
Core: ReportGenerator
สร้างรายงานการทดสอบ
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


class ReportGenerator:
    """สร้าง test report พร้อม root-cause diagnosis และ executive summary
    สำหรับแต่ละ failed test - ไม่ใช่แค่ pass/fail table เฉย ๆ
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

        return {
            "risk_level": risk_level,
            "headline": headline,
            "failures_by_severity": dict(by_severity),
            "failures_by_category": dict(by_category),
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

    def generate(self, test_run: Dict[str, Any]) -> Dict[str, Any]:
        """สร้าง report จาก test run พร้อม root-cause diagnosis ต่อ failed
        test และ executive summary ระดับความเสี่ยง
        """
        results = test_run.get("results", [])
        run_id = test_run.get("run_id", "")

        passed = [r for r in results if r.get("status") == "passed"]
        failed = [r for r in results if r.get("status") in ("failed", "error")]

        summary = {
            "total": len(results),
            "passed": len(passed),
            "failed": len([r for r in results if r.get("status") == "failed"]),
            "errors": len([r for r in results if r.get("status") == "error"]),
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

        return {
            "report_id": f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "run_id": run_id,
            "suite_name": test_run.get("suite_name"),
            "generated_at": datetime.now().isoformat(),
            "summary": summary,
            "executive_summary": self._executive_summary(summary, failed_tests),
            "failed_tests": failed_tests,
            "all_results": results,
        }

    def generate_html(self, report: Dict[str, Any]) -> str:
        """สร้าง HTML report พร้อม executive summary และ root cause ต่อ failed test"""
        summary = report["summary"]
        exec_summary = report["executive_summary"]

        risk_class = exec_summary["risk_level"].lower()
        severity_rows = "".join(
            f"<tr><td>{sev}</td><td>{count}</td></tr>"
            for sev, count in sorted(
                exec_summary["failures_by_severity"].items(),
                key=lambda kv: _SEVERITY_ORDER.get(kv[0], 99),
            )
        )
        top_risk_rows = "".join(
            f"""<tr>
            <td class="sev-{r['severity'].lower()}">{r['severity']}</td>
            <td>{r['test_name']}</td>
            <td>{r['category']}</td>
            <td>{r['root_cause']}</td>
        </tr>"""
            for r in exec_summary["top_risks"]
        )

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>QA Report - {report['suite_name']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; color: #222; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 8px; }}
        .exec-summary {{ padding: 20px; border-radius: 8px; margin-top: 20px; border-left: 6px solid #999; }}
        .exec-summary.critical {{ background: #fdecea; border-left-color: #c0392b; }}
        .exec-summary.high {{ background: #fdf3e7; border-left-color: #d68910; }}
        .exec-summary.medium {{ background: #fdf7e3; border-left-color: #b7950b; }}
        .exec-summary.none {{ background: #eafaf1; border-left-color: #229954; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        .error {{ color: orange; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #333; color: white; }}
        .sev-critical {{ color: #c0392b; font-weight: bold; }}
        .sev-high {{ color: #d68910; font-weight: bold; }}
        .sev-medium {{ color: #b7950b; }}
        .sev-low {{ color: #666; }}
        .suggested-fix {{ font-style: italic; color: #444; }}
        .report-meta {{ color: #666; font-size: 0.9em; margin-top: -10px; margin-bottom: 20px; }}
        @media print {{
            body {{ margin: 20px; }}
            .exec-summary, .summary {{ break-inside: avoid; }}
            tr {{ break-inside: avoid; }}
            @page {{ size: A4; margin: 18mm 14mm; }}
        }}
    </style>
</head>
<body>
    <h1>QA Test Report</h1>
    <p class="report-meta">Report ID: {report['report_id']} &middot; Run: {report['run_id']} &middot; Generated: {report['generated_at']}</p>

    <div class="exec-summary {risk_class}">
        <h2>Executive Summary</h2>
        <p><strong>{exec_summary['headline']}</strong></p>
        <table>
            <tr><th>Severity</th><th>Count</th></tr>
            {severity_rows or '<tr><td colspan="2">No failures</td></tr>'}
        </table>
        {"<h3>Top Risks</h3><table><tr><th>Severity</th><th>Test</th><th>Category</th><th>Root Cause</th></tr>" + top_risk_rows + "</table>" if exec_summary["top_risks"] else ""}
    </div>

    <div class="summary">
        <h2>Summary</h2>
        <p>Suite: {report['suite_name']}</p>
        <p>Total: {summary['total']}</p>
        <p class="passed">Passed: {summary['passed']}</p>
        <p class="failed">Failed: {summary['failed']}</p>
        <p class="error">Errors: {summary['errors']}</p>
        <p>Pass Rate: {summary['pass_rate']}%</p>
        <p>Duration: {summary['duration_ms']:.0f}ms</p>
    </div>

    <h2>Failed Tests</h2>
    <table>
        <tr><th>Test ID</th><th>Name</th><th>Severity</th><th>Category</th><th>Root Cause</th><th>Suggested Fix</th></tr>
"""
        for ft in report.get("failed_tests", []):
            html += f"""        <tr>
            <td>{ft['test_id']}</td>
            <td>{ft['test_name']}</td>
            <td class="sev-{ft['severity'].lower()}">{ft['severity']}</td>
            <td>{ft['category']}</td>
            <td>{ft['root_cause']}</td>
            <td class="suggested-fix">{ft['suggested_fix']}</td>
        </tr>
"""
        html += """    </table>
</body>
</html>"""
        return html


_reporter = ReportGenerator()


# MCP Tools
async def report_generate(run_id: str) -> Dict[str, Any]:
    """MCP tool: report.generate - สร้างรายงานสรุปจาก test run ที่รันไว้ (ผ่าน test.create_run + test.run/test.rerun)
    ใช้ได้แม้ run นั้นถูกสร้างใน process ก่อนหน้า (persist ไว้แล้ว) - รายงานมี
    root-cause diagnosis ต่อ failed test และ executive summary ระดับความเสี่ยง
    """
    from qa_mcp.execution.executor import _executor

    run = _executor.get_run_dict(run_id)
    if run is None:
        return {"error": f"Run '{run_id}' not found - เรียก test.create_run แล้ว test.run ก่อน"}
    return _reporter.generate(run)


async def report_generate_html(run_id: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """MCP tool: report.generate_html - สร้าง HTML report จาก test run แล้วเซฟไฟล์จริงลงดิสก์"""
    from qa_mcp.execution.executor import _executor

    run = _executor.get_run_dict(run_id)
    if run is None:
        return {"error": f"Run '{run_id}' not found - เรียก test.create_run แล้ว test.run ก่อน"}

    report = _reporter.generate(run)
    html = _reporter.generate_html(report)

    path = output_path or f"./reports/{report['report_id']}.html"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return {"report_id": report["report_id"], "path": path, "summary": report["summary"],
             "executive_summary": report["executive_summary"]}


async def report_generate_pdf(run_id: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """MCP tool: report.generate_pdf - สร้าง PDF report จริงลงดิสก์ (ไฟล์ที่เอาไป
    แนบอีเมล/ส่ง stakeholder/เก็บเป็นเอกสารอ้างอิงได้ตรง ๆ ไม่ต้องแปลงเอง) ใช้
    headless Chromium ของ Playwright (dependency ที่มีอยู่แล้วในโปรเจกต์) render
    HTML report เดียวกับ report.generate_html เป็น PDF จริง - ไม่ใช่ screenshot
    ของหน้าเว็บ แต่เป็น print-to-PDF จริงพร้อม page break ที่ถูกต้อง (@page CSS)
    """
    from qa_mcp.execution.executor import _executor

    run = _executor.get_run_dict(run_id)
    if run is None:
        return {"error": f"Run '{run_id}' not found - เรียก test.create_run แล้ว test.run ก่อน"}

    report = _reporter.generate(run)
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
