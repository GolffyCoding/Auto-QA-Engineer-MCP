"""Unit tests for qa_mcp.defect_cicd.defect_manager - DefectTracker CRUD,
CI provider detection, and CIManager's fail-fast behavior when credentials
are missing (no real network call must happen in that case). GitManager is
tested against a real throwaway git repo since `git` is a hard dependency
of the environment this project runs in anyway.
"""
import subprocess

import pytest

from qa_mcp.defect_cicd.defect_manager import CIManager, DefectStatus, DefectTracker, GitManager


@pytest.fixture
def tracker(tmp_path):
    return DefectTracker(state_path=str(tmp_path / "state.json"))


@pytest.mark.asyncio
async def test_create_defect_starts_as_new(tracker):
    defect = await tracker.create("Login button broken", "Clicking submit does nothing")
    assert defect.status == DefectStatus.NEW.value
    assert defect.defect_id.startswith("BUG-")


@pytest.mark.asyncio
async def test_attach_evidence_appends_to_list(tracker):
    defect = await tracker.create("Bug", "desc")
    await tracker.attach_evidence(defect.defect_id, "screenshot.png")
    updated = tracker.get(defect.defect_id)
    assert updated.evidence == ["screenshot.png"]


@pytest.mark.asyncio
async def test_add_comment_records_author_and_text(tracker):
    defect = await tracker.create("Bug", "desc")
    await tracker.add_comment(defect.defect_id, author="alice", text="looking into it")
    updated = tracker.get(defect.defect_id)
    assert updated.comments[0]["author"] == "alice"
    assert updated.comments[0]["text"] == "looking into it"


@pytest.mark.asyncio
async def test_update_status_changes_state(tracker):
    defect = await tracker.create("Bug", "desc")
    await tracker.update_status(defect.defect_id, DefectStatus.IN_PROGRESS.value)
    updated = tracker.get(defect.defect_id)
    assert updated.status == DefectStatus.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_defect_persists_across_new_tracker_instance(tmp_path):
    path = str(tmp_path / "state.json")
    first = DefectTracker(state_path=path)
    defect = await first.create("Bug", "desc")

    second = DefectTracker(state_path=path)
    reloaded = second.get(defect.defect_id)
    assert reloaded is not None
    assert reloaded.title == "Bug"


def test_ci_detect_finds_github_actions(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    assert CIManager().detect(str(tmp_path)) == "github_actions"


def test_ci_detect_finds_gitlab_ci(tmp_path):
    (tmp_path / ".gitlab-ci.yml").write_text("stages: []")
    assert CIManager().detect(str(tmp_path)) == "gitlab_ci"


def test_ci_detect_returns_unknown_for_no_ci_config(tmp_path):
    assert CIManager().detect(str(tmp_path)) == "unknown"


@pytest.mark.asyncio
async def test_ci_run_github_fails_fast_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = await CIManager().run("github_actions", "deploy.yml", repo="acme/widgets")
    assert "GITHUB_TOKEN" in result["error"]


@pytest.mark.asyncio
async def test_ci_run_github_fails_fast_without_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    result = await CIManager().run("github_actions", "deploy.yml", repo=None)
    assert "repo" in result["error"]


@pytest.mark.asyncio
async def test_ci_run_gitlab_fails_fast_without_token(monkeypatch):
    monkeypatch.delenv("GITLAB_TRIGGER_TOKEN", raising=False)
    result = await CIManager().run("gitlab_ci", "pipeline", repo="123")
    assert "error" in result


@pytest.mark.asyncio
async def test_ci_run_unsupported_provider_errors():
    result = await CIManager().run("jenkins", "pipeline")
    assert "error" in result


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return repo


@pytest.mark.asyncio
async def test_git_status_reports_untracked_file(git_repo):
    (git_repo / "new.txt").write_text("new\n")
    manager = GitManager(repo_path=str(git_repo))
    status = await manager.status()
    assert any("new.txt" in line for line in status["untracked"])


@pytest.mark.asyncio
async def test_git_log_returns_initial_commit(git_repo):
    manager = GitManager(repo_path=str(git_repo))
    commits = await manager.log(n=5)
    assert len(commits) == 1
    assert commits[0]["message"] == "initial"


@pytest.mark.asyncio
async def test_git_commit_records_change(git_repo):
    (git_repo / "file.txt").write_text("changed\n")
    manager = GitManager(repo_path=str(git_repo))
    result = await manager.commit("update file", files=["file.txt"])
    assert result["success"] is True

    commits = await manager.log(n=5)
    assert commits[0]["message"] == "update file"
