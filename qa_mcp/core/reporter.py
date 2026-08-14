"""
Core: ReportGenerator
สร้างรายงานการทดสอบ
"""
import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


class ReportGenerator:
    """สร้าง test report"""

    def generate(self, test_run: Dict[str, Any]) -> Dict[str, Any]:
        """สร้าง report จาก test run"""
        results = test_run.get("results", [])

        passed = [r for r in results if r.get("status") == "passed"]
        failed = [r for r in results if r.get("status") == "failed"]
        errors = [r for r in results if r.get("status") == "error"]

        return {
            "report_id": f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "run_id": test_run.get("run_id"),
            "suite_name": test_run.get("suite_name"),
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "passed": len(passed),
                "failed": len(failed),
                "errors": len(errors),
                "pass_rate": test_run.get("pass_rate", 0),
                "duration_ms": sum(r.get("duration_ms", 0) for r in results),
            },
            "failed_tests": [
                {
                    "test_id": r["test_id"],
                    "test_name": r["test_name"],
                    "error": r.get("error_message", ""),
                    "artifacts": [a["path"] for a in r.get("artifacts", [])],
                }
                for r in failed
            ],
            "all_results": results,
        }

    def generate_html(self, report: Dict[str, Any]) -> str:
        """สร้าง HTML report"""
        summary = report["summary"]
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>QA Report - {report['suite_name']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 8px; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        .error {{ color: orange; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #333; color: white; }}
    </style>
</head>
<body>
    <h1>QA Test Report</h1>
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
        <tr><th>Test ID</th><th>Name</th><th>Error</th></tr>
"""
        for ft in report.get("failed_tests", []):
            html += f"""        <tr>
            <td>{ft['test_id']}</td>
            <td>{ft['test_name']}</td>
            <td>{ft['error'][:100]}</td>
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
    ใช้ได้แม้ run นั้นถูกสร้างใน process ก่อนหน้า (persist ไว้แล้ว)
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

    return {"report_id": report["report_id"], "path": path, "summary": report["summary"]}
