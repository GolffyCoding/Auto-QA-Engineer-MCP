"""Unit tests for qa_mcp.execution.executor - real subprocess execution,
timeout handling, and TestRun bookkeeping. Uses `python3 -c ...` as the
test command so these run anywhere without external fixtures.
"""
import sys

import pytest

from qa_mcp.execution.executor import EnvironmentManager, TestExecutor, TestStatus


@pytest.fixture
def executor(tmp_path):
    return TestExecutor(artifacts_dir=str(tmp_path / "artifacts"), state_path=str(tmp_path / "state.json"))


@pytest.mark.asyncio
async def test_run_test_passes_and_captures_stdout(executor, tmp_path):
    await executor.create_run("suite-1")
    result = await executor.run_test(
        "t1", "prints hello",
        command=[sys.executable, "-c", "print('hello')"],
    )
    assert result.status == TestStatus.PASSED.value
    assert "hello" in result.stdout
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_run_test_fails_on_nonzero_exit(executor):
    await executor.create_run("suite-1")
    result = await executor.run_test(
        "t2", "exits nonzero",
        command=[sys.executable, "-c", "import sys; sys.exit(1)"],
    )
    assert result.status == TestStatus.FAILED.value
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_run_test_errors_on_timeout(executor):
    await executor.create_run("suite-1")
    result = await executor.run_test(
        "t3", "sleeps too long",
        command=[sys.executable, "-c", "import time; time.sleep(5)"],
        timeout=1,
    )
    assert result.status == TestStatus.ERROR.value
    assert "timed out" in result.error_message


@pytest.mark.asyncio
async def test_run_test_writes_stdout_artifact_to_disk(executor, tmp_path):
    await executor.create_run("suite-1")
    result = await executor.run_test(
        "t4", "prints hello",
        command=[sys.executable, "-c", "print('artifact check')"],
    )
    log_artifacts = [a for a in result.artifacts if a.type == "log"]
    assert log_artifacts
    assert (tmp_path / "artifacts" / "t4" / "stdout.log").read_text().strip() == "artifact check"


@pytest.mark.asyncio
async def test_current_run_accumulates_pass_fail_counts(executor):
    await executor.create_run("suite-1")
    await executor.run_test("a", "a", command=[sys.executable, "-c", "pass"])
    await executor.run_test("b", "b", command=[sys.executable, "-c", "import sys; sys.exit(1)"])

    run = executor.current_run
    assert run.total_tests == 2
    assert run.passed == 1
    assert run.failed == 1


@pytest.mark.asyncio
async def test_run_persists_and_is_readable_after_new_executor_instance(tmp_path):
    state_path = str(tmp_path / "state.json")
    first = TestExecutor(artifacts_dir=str(tmp_path / "artifacts"), state_path=state_path)
    run = await first.create_run("suite-1")
    await first.run_test("a", "a", command=[sys.executable, "-c", "pass"])

    second = TestExecutor(artifacts_dir=str(tmp_path / "artifacts"), state_path=state_path)
    reloaded = second.get_run_dict(run.run_id)
    assert reloaded["total_tests"] == 1
    assert reloaded["passed"] == 1


@pytest.mark.asyncio
async def test_retry_returns_immediately_on_first_pass(executor, monkeypatch):
    async def no_sleep(*_a, **_kw):
        return None
    monkeypatch.setattr("qa_mcp.execution.executor.asyncio.sleep", no_sleep)

    await executor.create_run("suite-1")
    result = await executor.retry(
        "t5", max_retries=3, command=[sys.executable, "-c", "pass"],
    )
    assert result.status == TestStatus.PASSED.value
    assert result.retry_count == 1


@pytest.mark.asyncio
async def test_retry_exhausts_attempts_when_always_failing(executor, monkeypatch):
    async def no_sleep(*_a, **_kw):
        return None
    monkeypatch.setattr("qa_mcp.execution.executor.asyncio.sleep", no_sleep)

    await executor.create_run("suite-1")
    result = await executor.retry(
        "t6", max_retries=2, command=[sys.executable, "-c", "import sys; sys.exit(1)"],
    )
    assert result.status == TestStatus.FAILED.value
    assert result.retry_count == 2


@pytest.mark.asyncio
async def test_environment_manager_start_stop_reset():
    mgr = EnvironmentManager()
    started = await mgr.start("staging", {"url": "https://staging.example.com"})
    assert started["status"] == "running"

    stopped = await mgr.stop("staging")
    assert stopped["status"] == "stopped"

    reset = await mgr.reset("staging")
    assert reset["status"] == "running"
    assert reset["config"] == {"url": "https://staging.example.com"}
