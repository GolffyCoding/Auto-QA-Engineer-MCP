"""Unit tests for qa_mcp.fix_loop.engine - focuses on the approval gate,
since that is the module that writes to real source files and therefore
carries the highest blast radius of anything in this codebase.
"""
import os

import pytest

from qa_mcp.fix_loop.engine import FixEngine, FixStatus, fix_loop_apply_patch, _engine


@pytest.fixture
def engine(tmp_path):
    return FixEngine(read_only=True, state_path=str(tmp_path / "state.json"))


@pytest.fixture
def target_file(tmp_path):
    f = tmp_path / "target.py"
    f.write_text("def create(data):\n    return data\n")
    return f


async def _make_proposal(engine, target_file):
    diagnosis = {
        "category": "database",
        "root_cause": "foreign key violation",
        "confidence": 80.0,
    }
    return await engine.propose_patch(
        failure_id="f1",
        diagnosis=diagnosis,
        file_path=str(target_file),
        original_code=target_file.read_text(),
    )


@pytest.mark.asyncio
async def test_proposal_starts_pending_approval(engine, target_file):
    proposal = await _make_proposal(engine, target_file)
    assert proposal.status == FixStatus.PENDING_APPROVAL.value


@pytest.mark.asyncio
async def test_apply_rejected_without_approval(engine, target_file):
    proposal = await _make_proposal(engine, target_file)
    result = await engine.apply_patch(proposal.patch_id)
    assert result == {"error": "Patch not approved"}
    # file on disk must be untouched
    assert target_file.read_text() == "def create(data):\n    return data\n"


@pytest.mark.asyncio
async def test_approve_then_apply_in_read_only_mode_does_not_touch_disk(engine, target_file):
    proposal = await _make_proposal(engine, target_file)
    await engine.approve(proposal.patch_id, approved_by="alice")

    result = await engine.apply_patch(proposal.patch_id)

    assert result["status"] == "simulated"
    assert target_file.read_text() == "def create(data):\n    return data\n"


@pytest.mark.asyncio
async def test_approve_then_apply_writes_file_when_not_read_only(engine, target_file):
    proposal = await _make_proposal(engine, target_file)
    await engine.approve(proposal.patch_id, approved_by="alice")
    engine.read_only = False

    result = await engine.apply_patch(proposal.patch_id)

    assert result["status"] == "applied"
    assert target_file.read_text() != "def create(data):\n    return data\n"


@pytest.mark.asyncio
async def test_rejected_patch_cannot_be_applied(engine, target_file):
    proposal = await _make_proposal(engine, target_file)
    await engine.reject(proposal.patch_id, reason="wrong fix")

    result = await engine.apply_patch(proposal.patch_id)

    assert result == {"error": "Patch not approved"}


@pytest.mark.asyncio
async def test_apply_unknown_patch_id_errors(engine):
    result = await engine.apply_patch("does-not-exist")
    assert result == {"error": "Patch not found"}


@pytest.mark.asyncio
async def test_mcp_tool_blocks_auto_apply_without_env_var(monkeypatch, target_file):
    """The MCP-exposed tool must refuse read_only=False unless a human
    operator has set QA_MCP_ALLOW_AUTO_APPLY=1 outside of the agent's
    own tool calls - otherwise an LLM agent could call fix_loop_approve
    followed by fix_loop_apply_patch(read_only=False) in the same
    session and self-approve + self-apply a patch with no human involved.
    """
    monkeypatch.delenv("QA_MCP_ALLOW_AUTO_APPLY", raising=False)

    diagnosis = {"category": "database", "root_cause": "foreign key violation", "confidence": 80.0}
    proposal = await _engine.propose_patch(
        failure_id="f2",
        diagnosis=diagnosis,
        file_path=str(target_file),
        original_code=target_file.read_text(),
    )
    await _engine.approve(proposal.patch_id, approved_by="alice")

    result = await fix_loop_apply_patch(proposal.patch_id, read_only=False)

    assert result["error"] == "auto-apply disabled"
    assert target_file.read_text() == "def create(data):\n    return data\n"


@pytest.mark.asyncio
async def test_mcp_tool_allows_auto_apply_with_env_var(monkeypatch, target_file):
    monkeypatch.setenv("QA_MCP_ALLOW_AUTO_APPLY", "1")

    diagnosis = {"category": "database", "root_cause": "foreign key violation", "confidence": 80.0}
    proposal = await _engine.propose_patch(
        failure_id="f3",
        diagnosis=diagnosis,
        file_path=str(target_file),
        original_code=target_file.read_text(),
    )
    await _engine.approve(proposal.patch_id, approved_by="alice")

    result = await fix_loop_apply_patch(proposal.patch_id, read_only=False)

    assert result["status"] == "applied"
