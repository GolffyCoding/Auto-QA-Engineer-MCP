"""Unit tests for qa_mcp.knowledge.base.KnowledgeBase - the mechanism for
teaching a company/project's own conventions to the agent once and having
them persist across every future session (state via the same
PersistentStore every other stateful module uses, not the raw
unlocked json.dump/load the original implementation had).
"""
import pytest

from qa_mcp.knowledge.base import KnowledgeBase


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(state_path=str(tmp_path / "state.json"))


def test_add_and_get_project_rule(kb):
    kb.add_project_rule("default_framework", "Always use Playwright, never Selenium")
    rules = kb.get_project_rules()
    assert rules["default_framework"]["rule"] == "Always use Playwright, never Selenium"


def test_project_rules_persist_across_new_instance(tmp_path):
    path = str(tmp_path / "state.json")
    first = KnowledgeBase(state_path=path)
    first.add_project_rule("staging_url", "https://staging.acme.internal")

    second = KnowledgeBase(state_path=path)
    assert second.get_project_rules()["staging_url"]["rule"] == "https://staging.acme.internal"


def test_add_failure_pattern_and_find_similar(kb):
    kb.add_failure_pattern(
        pattern="connection pool exhausted",
        fix="This is a retry-storm from the payment webhook, not a real DB issue - check the webhook retry config",
        confidence=0.9,
    )
    similar = kb.get_similar_failures("Error: connection pool exhausted after 30s")
    assert len(similar) == 1
    assert "retry-storm" in similar[0]["fix"]


def test_get_similar_failures_returns_empty_for_unrelated_error(kb):
    kb.add_failure_pattern(pattern="connection pool exhausted", fix="...")
    assert kb.get_similar_failures("element not found: #submit-btn") == []


def test_multiple_failure_patterns_do_not_overwrite_each_other(kb):
    kb.add_failure_pattern(pattern="pattern-a", fix="fix-a")
    kb.add_failure_pattern(pattern="pattern-b", fix="fix-b")
    assert len(kb.get_similar_failures("pattern-a")) == 1
    assert len(kb.get_similar_failures("pattern-b")) == 1


def test_add_and_get_decision(kb):
    kb.add_decision(
        context="visual regression testing",
        decision="not doing it",
        rationale="design changes too frequently for it to be worth the maintenance cost",
    )
    decisions = kb.get_decisions()
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "not doing it"


@pytest.mark.asyncio
async def test_mcp_tools_round_trip(tmp_path, monkeypatch):
    from qa_mcp.knowledge import base as kb_module

    # the MCP tool functions use a module-level singleton pointed at the
    # default state path - swap it for an isolated one so this test can't
    # pollute (or be polluted by) the real ./qa-mcp-state.json
    monkeypatch.setattr(kb_module, "_kb", KnowledgeBase(state_path=str(tmp_path / "state.json")))

    result = await kb_module.knowledge_add_rule("test_rule", "test value")
    assert result["rule"] == "test value"

    rules = await kb_module.knowledge_get_rules()
    assert "test_rule" in rules
