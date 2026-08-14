"""
Real MCP (Model Context Protocol) server - stdio transport.

Unlike the ad-hoc `--call` CLI in mcp_server.py (one process per call, no
memory between calls), this runs as ONE long-lived process that an LLM
client (Claude Desktop, Claude Code, or any MCP client) connects to over
stdio. Because it's a single process, tool state persists naturally across
calls in the same session - open a browser, click, screenshot, close;
propose a patch, approve it, apply it, verify it - exactly the loop an
autonomous QA agent needs to run.
"""
from typing import Any, Dict, List, Optional

from mcp.server import MCPServer

from qa_mcp.project_intelligence.scanner import ProjectScanner, project_scan, project_structure
from qa_mcp.test_design.generator import (
    TestDesigner,
    test_generate,
    test_analyze_coverage,
)
from qa_mcp.adapters.browser import (
    browser_open,
    browser_click,
    browser_fill,
    browser_screenshot,
    browser_assert,
    browser_close,
)
from qa_mcp.adapters.api import api_request, api_assert_status, api_load_test
from qa_mcp.adapters.mobile import (
    mobile_launch,
    mobile_tap,
    mobile_swipe,
    mobile_type_text,
    mobile_assert_element,
    mobile_close,
)
from qa_mcp.execution.executor import (
    test_create,
    test_create_run,
    test_run,
    test_rerun,
    test_get_run,
    environment_start,
    environment_stop,
)
from qa_mcp.core.reporter import report_generate, report_generate_html, report_generate_pdf
from qa_mcp.analyzers.database_analyzer import db_get_table_state, db_check_fk_integrity, db_query
from qa_mcp.knowledge.base import (
    knowledge_add_rule,
    knowledge_get_rules,
    knowledge_add_failure_pattern,
    knowledge_get_similar_failures,
    knowledge_add_decision,
    knowledge_get_decisions,
)
from qa_mcp.failure_analysis.analyzer import (
    failure_inspect,
    failure_classify,
    failure_find_root_cause,
    failure_get_evidence,
    failure_compare_runs,
)
from qa_mcp.fix_loop.engine import (
    fix_loop_diagnose,
    fix_loop_propose,
    fix_loop_approve,
    fix_loop_apply_patch,
    fix_loop_verify,
)
from qa_mcp.defect_cicd.defect_manager import (
    defect_create,
    defect_attach_evidence,
    git_status,
    git_diff,
    git_create_branch,
    git_commit,
    ci_detect,
    ci_run,
    ci_get_status,
)


async def project_detect_stack(project_path: str) -> Dict[str, Any]:
    """MCP tool: project.detect_stack - ตรวจ tech stack แบบเร็ว (ไม่สแกน routes/components เต็มรูปแบบ)"""
    scanner = ProjectScanner(project_path)
    return scanner.detect_stack()


async def test_prioritize(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """MCP tool: test.prioritize - จัดลำดับความสำคัญของ test cases ตาม priority"""
    from qa_mcp.test_design.generator import TestCase

    typed_cases = [TestCase(**c) for c in cases]
    ordered = TestDesigner.prioritize(typed_cases)
    return [c.to_dict() for c in ordered]


# name -> (function, description override)
# Grouped to mirror the 7 phases in README.md; each is registered under its
# dotted MCP tool name (e.g. "project.scan") so behavior matches the CLI
# dispatch table in mcp_server.py.
TOOLS = {
    # Phase 1: Project Intelligence
    "project.scan": project_scan,
    "project.structure": project_structure,
    "project.detect_stack": project_detect_stack,
    # Phase 2: Test Design
    "test.generate": test_generate,
    "test.generate_api": test_generate,  # same engine; aliases kept in sync with mcp_server.py's CLI tool list
    "test.generate_e2e": test_generate,
    "test.analyze_coverage": test_analyze_coverage,
    "test.prioritize": test_prioritize,
    # Phase 3: Automation Engine
    "browser.open": browser_open,
    "browser.click": browser_click,
    "browser.fill": browser_fill,
    "browser.screenshot": browser_screenshot,
    "browser.assert": browser_assert,
    "browser.close": browser_close,
    "api.request": api_request,
    "api.assert_status": api_assert_status,
    "api.load_test": api_load_test,
    "mobile.launch": mobile_launch,
    "mobile.tap": mobile_tap,
    "mobile.swipe": mobile_swipe,
    "mobile.type_text": mobile_type_text,
    "mobile.assert_element": mobile_assert_element,
    "mobile.close": mobile_close,
    # Phase 4: Execution
    "test.create": test_create,
    "test.create_run": test_create_run,
    "test.run": test_run,
    "test.rerun": test_rerun,
    "test.get_run": test_get_run,
    "environment.start": environment_start,
    "environment.stop": environment_stop,
    # Phase 5: Failure Analysis
    "failure.inspect": failure_inspect,
    "failure.classify": failure_classify,
    "failure.find_root_cause": failure_find_root_cause,
    "failure.get_evidence": failure_get_evidence,
    "failure.compare_runs": failure_compare_runs,
    # Phase 6: Fix Loop
    "fix_loop.diagnose": fix_loop_diagnose,
    "fix_loop.propose": fix_loop_propose,
    "fix_loop.approve": fix_loop_approve,
    "fix_loop.apply_patch": fix_loop_apply_patch,
    "fix_loop.verify": fix_loop_verify,
    # Phase 7: Defect / CI/CD
    "defect.create": defect_create,
    "defect.attach_evidence": defect_attach_evidence,
    "git.status": git_status,
    "git.diff": git_diff,
    "git.create_branch": git_create_branch,
    "git.commit": git_commit,
    "ci.detect": ci_detect,
    "ci.run": ci_run,
    "ci.get_status": ci_get_status,
    # Phase 8: Reporting
    "report.generate": report_generate,
    "report.generate_html": report_generate_html,
    "report.generate_pdf": report_generate_pdf,
    # Phase 9: Database Validation
    "db.get_table_state": db_get_table_state,
    "db.check_fk_integrity": db_check_fk_integrity,
    "db.query": db_query,
    # Phase 10: Knowledge Base (company/project-specific conventions)
    "knowledge.add_rule": knowledge_add_rule,
    "knowledge.get_rules": knowledge_get_rules,
    "knowledge.add_failure_pattern": knowledge_add_failure_pattern,
    "knowledge.get_similar_failures": knowledge_get_similar_failures,
    "knowledge.add_decision": knowledge_add_decision,
    "knowledge.get_decisions": knowledge_get_decisions,
}

_BASE_INSTRUCTIONS = (
    "Autonomous QA Engineer runtime. Typical loop: project.scan the "
    "target repo, test.generate cases, browser.open/click/fill/"
    "screenshot/assert to execute them (call browser.close when "
    "done), failure.inspect + fix_loop.diagnose/propose/approve/"
    "apply_patch/verify to fix failures, then defect.create to "
    "report anything unresolved."
)


def _build_instructions() -> str:
    """ประกอบ instructions ที่ LLM เห็นตอน connect - เริ่มจาก base instructions
    แล้วต่อท้ายด้วย company/project convention 2 แหล่ง เพื่อให้ agent ไม่ต้อง
    ถูกสอนบริบทเดิมซ้ำทุกเซสชัน:

    1. `knowledge.add_rule` ที่เคยบันทึกไว้ (persist ผ่าน QA_MCP_STATE_DB -
       เพิ่มครั้งเดียว เห็นทุก session ต่อไป ไม่ต้องแก้โค้ด)
    2. ไฟล์ที่ชี้ผ่าน env var `QA_MCP_INSTRUCTIONS_FILE` ถ้ามี (เช่น
       "เราใช้ Playwright เท่านั้น", "staging URL คือ https://...",
       "severity mapping ของทีมนี้คือ ...") - เขียนเป็น markdown/text ธรรมดา
       ไม่ต้องเรียก tool เลย เหมาะกับ convention ที่รู้ตั้งแต่ต้นและไม่เปลี่ยนบ่อย
    """
    import os

    from qa_mcp.knowledge.base import _kb

    parts = [_BASE_INSTRUCTIONS]

    rules = _kb.get_project_rules()
    if rules:
        rule_lines = "\n".join(f"- {name}: {r['rule']}" for name, r in rules.items())
        parts.append(f"Project/company conventions (from knowledge.add_rule):\n{rule_lines}")

    instructions_file = os.environ.get("QA_MCP_INSTRUCTIONS_FILE")
    if instructions_file and os.path.exists(instructions_file):
        with open(instructions_file, "r", encoding="utf-8") as f:
            parts.append(f.read().strip())

    return "\n\n".join(parts)


def create_server() -> MCPServer:
    """สร้าง MCPServer พร้อมลงทะเบียนทุก tool จาก TOOLS

    ใช้ฟังก์ชันจริง (ไม่ใช่ generic **kwargs wrapper) เพื่อให้ MCP สร้าง
    JSON schema ของ input ให้ LLM เห็น argument ที่ถูกต้องจริง ๆ
    """
    server = MCPServer(name="qa-mcp", instructions=_build_instructions())
    for name, fn in TOOLS.items():
        server.add_tool(fn, name=name)
    return server


def main() -> None:
    """Entry point: รัน MCP server ผ่าน stdio ให้ LLM client ต่อเข้ามาแบบ long-running"""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
