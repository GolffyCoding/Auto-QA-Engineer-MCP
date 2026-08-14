"""Integration tests for qa_mcp.server - the REAL MCP server an LLM client
(Claude Desktop, Claude Code, or any MCP client) actually connects to,
as opposed to qa_mcp.mcp_server (the debug-only `qa-mcp --call` CLI).

Before this file existed, qa_mcp.server had zero test coverage and the
`mcp` package wasn't even installed in this environment - meaning the
module that is the entire point of this project (an LLM connects to it)
had never actually been verified to import, let alone run. It doesn't
just import cleanly: report.generate_pdf and test.generate_api existed in
mcp_server.py's CLI tool table but were missing from server.py's real
TOOLS dict, so an LLM client could see and use them via `qa-mcp --call`
but not through the real MCP server. Fixed by adding both.
"""
import re

import pytest

from qa_mcp.mcp_server import QAMCPServer
from qa_mcp.server import TOOLS, create_server


def test_create_server_succeeds():
    server = create_server()
    assert server.name == "qa-mcp"


@pytest.mark.asyncio
async def test_all_registered_tools_are_visible_to_a_real_mcp_client():
    server = create_server()
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == set(TOOLS.keys())


def test_pdf_report_tool_is_registered_for_real_llm_clients():
    """Regression: report.generate_pdf was added to the CLI tool table
    (mcp_server.py) but not to the real server's TOOLS dict - an LLM
    connected via qa-mcp-serve couldn't see or call it at all, even though
    `qa-mcp --list-tools` showed it as available.
    """
    assert "report.generate_pdf" in TOOLS


def test_cli_tool_table_and_real_server_tool_table_stay_in_sync():
    """Every dotted tool name in mcp_server.py's CLI dispatch table (used
    by `qa-mcp --call` for debugging one tool at a time) must also be
    reachable through qa_mcp.server's TOOLS dict (used by the real MCP
    server an LLM actually connects to) - otherwise a tool works for
    debugging but silently doesn't exist for the thing this project is
    actually for. The one documented exception is test.run_single, which
    takes a Python `Callable` argument that can't be expressed over JSON
    at all (over stdio *or* via the --call CLI), so it can't be a real
    MCP tool either way.
    """
    cli_server = QAMCPServer()
    cli_tool_names = set(cli_server.tools.keys())
    real_server_tool_names = set(TOOLS.keys())

    known_cli_only_exceptions = {"test.run_single"}
    missing = cli_tool_names - real_server_tool_names - known_cli_only_exceptions
    assert missing == set(), f"Tools debuggable via CLI but unreachable from a real LLM client: {missing}"


@pytest.mark.asyncio
async def test_real_stdio_mcp_session_end_to_end(tmp_path):
    """Spawns `python -m qa_mcp.server` as a real subprocess and drives it
    exactly as an LLM client (Claude Desktop, Claude Code, ...) would:
    initialize, list_tools, call_tool over real stdio - not an in-process
    shortcut. This is the closest thing to actually verifying "an LLM can
    connect to this and use it" without a real LLM in the loop.
    """
    import os
    import sys
    from pathlib import Path

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    repo_root = str(Path(__file__).resolve().parents[1])
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "qa_mcp.server"], cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": repo_root},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert "project.scan" in names
            assert "report.generate_pdf" in names

            (tmp_path / "main.py").write_text("print('hi')\n")
            result = await session.call_tool("project.scan", {"project_path": str(tmp_path)})
            text = result.content[0].text
            assert "\"language\": \"Python\"" in text
