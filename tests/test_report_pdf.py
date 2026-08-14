"""Unit tests for report.generate_pdf - renders the same HTML report
through real headless Chromium (Playwright, already a dependency) via
print-to-PDF, not a screenshot. Produces a real PDF file suitable for
emailing/filing as a document, not just a JSON blob.
"""
import sys

import pytest

from qa_mcp.mcp_server import QAMCPServer


@pytest.fixture
async def server_with_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = QAMCPServer()
    run = await s.call("test.create_run", suite_name="pdf-test-suite")
    run_id = run["run_id"]
    await s.call("test.run", test_id="t-pass", command=[sys.executable, "-c", "pass"])
    await s.call(
        "test.run", test_id="t-fail",
        command=[sys.executable, "-c",
                 "import sys; print('foreign key constraint violation', file=sys.stderr); sys.exit(1)"],
    )
    return s, run_id


@pytest.mark.asyncio
async def test_generate_pdf_writes_real_pdf_file(server_with_run, tmp_path):
    s, run_id = server_with_run
    result = await s.call("report.generate_pdf", run_id=run_id)

    assert "error" not in result
    pdf_path = tmp_path / result["path"].lstrip("./")
    assert pdf_path.exists()
    assert pdf_path.read_bytes()[:5] == b"%PDF-"
    assert pdf_path.stat().st_size > 1000


@pytest.mark.asyncio
async def test_generate_pdf_respects_custom_output_path(server_with_run, tmp_path):
    s, run_id = server_with_run
    custom_path = str(tmp_path / "custom-dir" / "my-report.pdf")

    result = await s.call("report.generate_pdf", run_id=run_id, output_path=custom_path)

    assert result["path"] == custom_path
    assert (tmp_path / "custom-dir" / "my-report.pdf").exists()


@pytest.mark.asyncio
async def test_generate_pdf_summary_matches_generate_html(server_with_run):
    s, run_id = server_with_run
    pdf_result = await s.call("report.generate_pdf", run_id=run_id)
    html_result = await s.call("report.generate_html", run_id=run_id)

    assert pdf_result["summary"] == html_result["summary"]
    assert pdf_result["executive_summary"]["risk_level"] == html_result["executive_summary"]["risk_level"]


@pytest.mark.asyncio
async def test_generate_pdf_errors_on_unknown_run():
    s = QAMCPServer()
    result = await s.call("report.generate_pdf", run_id="does-not-exist")
    assert "error" in result
