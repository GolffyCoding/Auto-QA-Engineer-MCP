"""
Phase 4: Execution
ควบคุม lifecycle ของการทดสอบ: create, run, retry, stop
เก็บ stdout, stderr, screenshots, videos, traces, network, console, logs
"""
import asyncio
import json
import os
import subprocess
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime


class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    RETRYING = "retrying"


@dataclass
class TestArtifact:
    """Evidence ที่เก็บระหว่างการทดสอบ"""
    type: str  # screenshot, video, trace, network, console, log, dom
    path: str
    timestamp: str
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """ผลลัพธ์ของการทดสอบ"""
    test_id: str
    test_name: str
    status: str
    duration_ms: float
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    artifacts: List[TestArtifact] = field(default_factory=list)
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    start_time: str = ""
    end_time: str = ""
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestRun:
    """การรัน test suite ครั้งหนึ่ง"""
    run_id: str
    suite_name: str
    started_at: str
    completed_at: Optional[str] = None
    results: List[TestResult] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return round(self.passed / self.total_tests * 100, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "suite_name": self.suite_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "pass_rate": self.pass_rate,
            "environment": self.environment,
            "results": [r.to_dict() for r in self.results],
        }


class TestExecutor:
    """ควบคุมการรัน tests พร้อมเก็บ evidence"""

    def __init__(self, artifacts_dir: str = "./test-artifacts", state_path: str = ""):
        from qa_mcp.core.persistence import PersistentStore

        self.artifacts_dir = artifacts_dir
        os.makedirs(artifacts_dir, exist_ok=True)
        self._runs: Dict[str, TestRun] = {}
        self._current_run: Optional[TestRun] = None
        self._observers: List[Callable] = []

        # TestRun มี nested dataclass (TestResult -> TestArtifact) จึงเก็บ
        # persisted form เป็น plain dict แทนการ reconstruct กลับเป็น object -
        # เพียงพอสำหรับอ่านย้อนหลัง (report/compare_runs) ข้าม process restart
        self._store = PersistentStore(state_path)
        self._runs_ns = self._store.namespace("test_runs")

    def _persist_current_run(self) -> None:
        if self._current_run:
            self._runs_ns[self._current_run.run_id] = self._current_run.to_dict()
            self._store.save()

    def add_observer(self, callback: Callable[[TestResult], None]):
        """เพิ่ม observer สำหรับ real-time monitoring"""
        self._observers.append(callback)

    async def create_run(self, suite_name: str, run_id: Optional[str] = None) -> TestRun:
        """สร้าง test run ใหม่"""
        run_id = run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        run = TestRun(
            run_id=run_id,
            suite_name=suite_name,
            started_at=datetime.now().isoformat(),
            environment={
                "python_version": os.sys.version,
                "platform": os.sys.platform,
                "cwd": os.getcwd(),
            },
        )
        self._runs[run_id] = run
        self._current_run = run
        self._persist_current_run()
        return run

    def get_run_dict(self, run_id: str) -> Optional[Dict[str, Any]]:
        """ดึง run เป็น dict - ใช้ได้ทั้ง run ที่ยังอยู่ใน memory (process นี้)
        และ run ที่ persist ไว้จาก process ก่อนหน้า (รอด restart)
        """
        if run_id in self._runs:
            return self._runs[run_id].to_dict()
        return self._runs_ns.get(run_id)

    async def run_test(self, test_id: str, test_name: str,
                       command: List[str],
                       timeout: int = 120,
                       capture_artifacts: bool = True) -> TestResult:
        """รัน test แบบ subprocess พร้อมเก็บ evidence"""
        start_time = datetime.now().isoformat()
        start_ts = time.time()

        result = TestResult(
            test_id=test_id,
            test_name=test_name,
            status=TestStatus.RUNNING.value,
            duration_ms=0,
            start_time=start_time,
        )

        # สร้าง artifacts directory สำหรับ test นี้
        test_artifact_dir = os.path.join(self.artifacts_dir, test_id)
        os.makedirs(test_artifact_dir, exist_ok=True)

        try:
            # รัน command
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            result.stdout = stdout.decode("utf-8", errors="replace")
            result.stderr = stderr.decode("utf-8", errors="replace")
            result.exit_code = proc.returncode
            result.duration_ms = round((time.time() - start_ts) * 1000, 2)
            result.end_time = datetime.now().isoformat()

            if proc.returncode == 0:
                result.status = TestStatus.PASSED.value
            else:
                result.status = TestStatus.FAILED.value
                result.error_message = result.stderr[:500] if result.stderr else "Test failed"

            # เก็บ logs
            if result.stdout:
                log_path = os.path.join(test_artifact_dir, "stdout.log")
                with open(log_path, "w") as f:
                    f.write(result.stdout)
                result.artifacts.append(TestArtifact(
                    type="log",
                    path=log_path,
                    timestamp=datetime.now().isoformat(),
                    size_bytes=len(result.stdout),
                ))

            if result.stderr:
                err_path = os.path.join(test_artifact_dir, "stderr.log")
                with open(err_path, "w") as f:
                    f.write(result.stderr)
                result.artifacts.append(TestArtifact(
                    type="log",
                    path=err_path,
                    timestamp=datetime.now().isoformat(),
                    size_bytes=len(result.stderr),
                ))

        except asyncio.TimeoutError:
            result.status = TestStatus.ERROR.value
            result.error_message = f"Test timed out after {timeout}s"
            result.exit_code = -1
            if proc:
                proc.kill()
        except Exception as e:
            result.status = TestStatus.ERROR.value
            result.error_message = str(e)
            result.stack_trace = getattr(e, "__traceback__", None)
            result.exit_code = -1

        # แจ้ง observers
        for obs in self._observers:
            try:
                obs(result)
            except:
                pass

        # เพิ่มเข้า current run
        if self._current_run:
            self._current_run.results.append(result)
            self._current_run.total_tests += 1
            if result.status == TestStatus.PASSED.value:
                self._current_run.passed += 1
            elif result.status == TestStatus.FAILED.value:
                self._current_run.failed += 1
            elif result.status == TestStatus.SKIPPED.value:
                self._current_run.skipped += 1
            self._persist_current_run()

        return result

    async def run_single(self, test_id: str, test_func: Callable, *args, **kwargs) -> TestResult:
        """รัน test function โดยตรง (ไม่ผ่าน subprocess)"""
        start_time = datetime.now().isoformat()
        start_ts = time.time()

        result = TestResult(
            test_id=test_id,
            test_name=test_func.__name__,
            status=TestStatus.RUNNING.value,
            duration_ms=0,
            start_time=start_time,
        )

        try:
            await test_func(*args, **kwargs)
            result.status = TestStatus.PASSED.value
        except AssertionError as e:
            result.status = TestStatus.FAILED.value
            result.error_message = str(e)
        except Exception as e:
            result.status = TestStatus.ERROR.value
            result.error_message = str(e)
            result.stack_trace = str(e.__traceback__)
        finally:
            result.duration_ms = round((time.time() - start_ts) * 1000, 2)
            result.end_time = datetime.now().isoformat()

        if self._current_run:
            self._current_run.results.append(result)
            self._current_run.total_tests += 1
            if result.status == TestStatus.PASSED.value:
                self._current_run.passed += 1
            elif result.status == TestStatus.FAILED.value:
                self._current_run.failed += 1
            self._persist_current_run()

        return result

    async def retry(self, test_id: str, max_retries: int = 3,
                    command: Optional[List[str]] = None,
                    test_func: Optional[Callable] = None) -> TestResult:
        """รัน test ใหม่ถ้า fail"""
        for attempt in range(max_retries):
            if command:
                result = await self.run_test(test_id, f"{test_id}-retry-{attempt+1}", command)
            elif test_func:
                result = await self.run_single(f"{test_id}-retry-{attempt+1}", test_func)
            else:
                raise ValueError("Either command or test_func must be provided")

            result.retry_count = attempt + 1

            if result.status == TestStatus.PASSED.value:
                return result

            await asyncio.sleep(2 ** attempt)  # exponential backoff

        return result

    async def stop_run(self, run_id: Optional[str] = None) -> TestRun:
        """หยุด test run"""
        run = self._runs.get(run_id) if run_id else self._current_run
        if run:
            run.completed_at = datetime.now().isoformat()
        return run

    def get_run(self, run_id: str) -> Optional[TestRun]:
        return self._runs.get(run_id)

    def get_all_runs(self) -> List[TestRun]:
        return list(self._runs.values())

    @property
    def current_run(self) -> Optional[TestRun]:
        return self._current_run


class EnvironmentManager:
    """จัดการ test environment"""

    def __init__(self):
        self._environments: Dict[str, Dict[str, Any]] = {}

    async def start(self, env_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """เริ่ม environment"""
        self._environments[env_name] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "config": config,
        }
        return self._environments[env_name]

    async def stop(self, env_name: str) -> Dict[str, Any]:
        """หยุด environment"""
        if env_name in self._environments:
            self._environments[env_name]["status"] = "stopped"
            self._environments[env_name]["stopped_at"] = datetime.now().isoformat()
        return self._environments.get(env_name)

    async def reset(self, env_name: str) -> Dict[str, Any]:
        """รีเซ็ต environment"""
        await self.stop(env_name)
        config = self._environments.get(env_name, {}).get("config", {})
        return await self.start(env_name, config)


# MCP Tools
# Shared singletons so test.run / test.rerun calls in the same session
# accumulate into the same TestRun (needed for report.generate to have
# more than one result to report on), instead of each call getting a
# throwaway TestExecutor with no suite context.
_executor = TestExecutor()
_env_manager = EnvironmentManager()


async def test_create(test_id: str, test_name: str) -> Dict[str, Any]:
    """MCP tool: test.create"""
    return {
        "test_id": test_id,
        "test_name": test_name,
        "status": "created",
        "created_at": datetime.now().isoformat(),
    }


async def test_create_run(suite_name: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """MCP tool: test.create_run - เริ่ม test suite ใหม่ (ผลจาก test.run/test.rerun หลังจากนี้จะรวมเข้า run นี้)"""
    run = await _executor.create_run(suite_name, run_id=run_id)
    return run.to_dict()


async def test_run(test_id: str, command: List[str]) -> Dict[str, Any]:
    """MCP tool: test.run"""
    if _executor.current_run is None:
        await _executor.create_run(f"suite-{test_id}")
    result = await _executor.run_test(test_id, test_id, command)
    return result.to_dict()


async def test_rerun(test_id: str, command: List[str], max_retries: int = 3) -> Dict[str, Any]:
    """MCP tool: test.rerun"""
    if _executor.current_run is None:
        await _executor.create_run(f"suite-{test_id}")
    result = await _executor.retry(test_id, max_retries=max_retries, command=command)
    return result.to_dict()


async def test_get_run(run_id: str) -> Dict[str, Any]:
    """MCP tool: test.get_run - ดึง test run ทั้งหมด (รวม results) ตาม run_id
    (ใช้ได้แม้ run นั้นถูกสร้างใน process ก่อนหน้า เพราะ persist ไว้ในดิสก์แล้ว)
    """
    run = _executor.get_run_dict(run_id)
    if run is None:
        return {"error": f"Run '{run_id}' not found"}
    return run


async def environment_start(env_name: str, config: Optional[Dict] = None) -> Dict[str, Any]:
    """MCP tool: environment.start"""
    return await _env_manager.start(env_name, config or {})


async def environment_stop(env_name: str) -> Dict[str, Any]:
    """MCP tool: environment.stop"""
    return await _env_manager.stop(env_name)
