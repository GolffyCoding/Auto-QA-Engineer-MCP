"""
Phase 5: Failure Analysis
สร้าง Failure Evidence, วิเคราะห์สาเหตุ, หา root cause
"""
import json
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class FailureEvidence:
    """Evidence ที่เก็บเมื่อ test fail"""
    failure_id: str
    test_name: str
    expected: str
    actual: str
    screenshot: Optional[str] = None
    trace_file: Optional[str] = None
    console_log: Optional[str] = None
    network_requests: List[Dict] = field(default_factory=list)
    response_body: Optional[str] = None
    server_log: Optional[str] = None
    database_state: Optional[Dict] = None
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FailureDiagnosis:
    """ผลการวิเคราะห์ failure"""
    failure_id: str
    category: str  # UI, API, Database, Network, Logic, Environment
    likely_cause: str
    root_cause: str
    confidence: float  # 0-100%
    suggested_fix: str
    related_files: List[str] = field(default_factory=list)
    similar_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FailureAnalyzer:
    """วิเคราะห์ failure จาก evidence

    Classification ใช้ weighted pattern matching แทน plain count: pattern ที่
    เจาะจง (เช่น "HTTP 500", "OutOfMemoryError") ได้ weight สูง ส่วน pattern
    ทั่วไปที่ใช้ร่วมกันได้หลาย category (เช่น "timeout") ได้ weight ต่ำ เพื่อไม่ให้
    เกิด tie-break แบบสุ่มเวลาข้อความ error สั้น ๆ ไปแมตช์หลาย category พร้อมกัน
    """

    # (category, pattern, weight) - weight สูง = เจาะจง เชื่อถือได้มากกว่า
    ERROR_PATTERNS: List[tuple] = [
        # --- Database ---
        ("database", r"foreign key constraint", 3),
        ("database", r"unique constraint", 3),
        ("database", r"deadlock detected", 3),
        ("database", r"column .* does not exist", 3),
        ("database", r"relation .* does not exist", 3),
        ("database", r"duplicate key value", 3),
        ("database", r"connection pool exhausted", 3),
        ("database", r"(too many connections|max_connections)", 2),
        ("database", r"database is locked", 2),
        ("database", r"(connection refused|could not connect to server)", 1),
        ("database", r"query timeout", 2),

        # --- API / HTTP ---
        ("api", r"HTTP[/ ]?5\d\d", 3),
        ("api", r"HTTP[/ ]?404", 3),
        ("api", r"HTTP[/ ]?400", 2),
        ("api", r"(internal server error|unhandled exception)", 3),
        ("api", r"malformed (json|response)", 2),
        ("api", r"schema validation failed", 2),
        ("api", r"connection reset", 1),

        # --- Auth / Authorization ---
        ("auth", r"HTTP[/ ]?401", 3),
        ("auth", r"HTTP[/ ]?403", 3),
        ("auth", r"(unauthorized|not authenticated)", 2),
        ("auth", r"(invalid|expired) (token|jwt|session)", 3),
        ("auth", r"forbidden", 2),
        ("auth", r"permission denied", 2),
        ("auth", r"csrf token (invalid|mismatch|missing)", 3),

        # --- Validation ---
        ("validation", r"validation (error|failed)", 3),
        ("validation", r"required field .* (missing|not provided)", 3),
        ("validation", r"(invalid|malformed) (input|payload|request body)", 2),
        ("validation", r"type mismatch", 2),
        ("validation", r"value (too long|out of range|exceeds maximum)", 2),

        # --- UI ---
        ("ui", r"(element|locator) not found", 3),
        ("ui", r"(timeout|waiting for) (element|selector|locator)", 3),
        ("ui", r"stale element reference", 3),
        ("ui", r"element not interactable", 3),
        ("ui", r"element (is )?not (visible|clickable)", 2),
        ("ui", r"detached from (the )?dom", 2),

        # --- Browser / Rendering ---
        ("browser", r"page crash(ed)?", 3),
        ("browser", r"renderer (process )?(crash|hang)", 3),
        ("browser", r"(uncaught|unhandled) exception", 2),
        ("browser", r"target (closed|crashed)", 2),
        ("browser", r"navigation timeout", 2),

        # --- Network ---
        ("network", r"net::err", 3),
        ("network", r"failed to fetch", 2),
        ("network", r"cors (error|policy)", 3),
        ("network", r"(dns|name) resolution failed", 3),
        ("network", r"connection (timed out|timeout)", 2),
        ("network", r"ssl/tls (error|handshake failed)", 3),
        ("network", r"network error", 1),

        # --- Concurrency / Race Conditions ---
        ("concurrency", r"race condition", 3),
        ("concurrency", r"lock (timeout|wait timeout|acquisition failed)", 3),
        ("concurrency", r"(double|duplicate) submission", 2),
        ("concurrency", r"optimistic (lock|concurrency) (error|failure)", 3),
        ("concurrency", r"deadlock", 2),

        # --- Memory / Resource ---
        ("resource", r"out ?of ?memory", 3),
        ("resource", r"(heap|stack) overflow", 3),
        ("resource", r"(memory|resource) limit exceeded", 3),
        ("resource", r"too many open files", 3),
        ("resource", r"disk (full|space)", 3),
        ("resource", r"quota exceeded", 2),

        # --- Filesystem / IO ---
        ("filesystem", r"no such file or directory", 3),
        ("filesystem", r"enoent", 3),
        ("filesystem", r"permission denied", 1),  # overlaps auth wording, low weight
        ("filesystem", r"file not found", 2),

        # --- Configuration / Environment ---
        ("configuration", r"(environment variable|env var) .* (not set|missing)", 3),
        ("configuration", r"(config|configuration) (file )?not found", 3),
        ("configuration", r"missing required (config|setting)", 3),
        ("configuration", r"module not found", 2),
        ("configuration", r"import error", 2),

        # --- Third-party / External services ---
        ("third_party", r"rate limit exceeded", 3),
        ("third_party", r"(webhook|callback) failed", 2),
        ("third_party", r"upstream (error|service unavailable)", 3),
        ("third_party", r"third[- ]party (api|service) (error|unavailable)", 3),
        ("third_party", r"payment (gateway|provider) (error|declined)", 3),

        # --- Mobile ---
        ("mobile", r"app (has )?crashed", 3),
        ("mobile", r"anr \(application not responding\)", 3),
        ("mobile", r"appium (session|driver) (not (initialized|found)|error)", 3),
        ("mobile", r"no such (element|context)", 2),

        # --- Security (detected during testing, not the injection attempt itself) ---
        ("security", r"sql syntax.*error", 3),
        ("security", r"you have an error in your sql syntax", 3),
        ("security", r"stack trace (leaked|exposed)", 3),
        ("security", r"blocked by (waf|firewall)", 2),

        # --- Logic / Assertion ---
        ("logic", r"assertion (failed|error)", 3),
        ("logic", r"expected .* but got", 3),
        ("logic", r"expected .* to (equal|be|contain)", 2),
        ("logic", r"does not match", 1),

        # --- Generic fallback (kept low-weight, applies across categories) ---
        ("api", r"timeout", 1),
        ("database", r"timeout", 1),
        ("network", r"timeout", 1),
    ]

    def __init__(self, state_path: str = ""):
        from qa_mcp.core.persistence import PersistentStore

        self._store = PersistentStore(state_path)
        self._evidence_ns = self._store.namespace("failure_evidence")
        self._history: List[FailureDiagnosis] = []
        self._evidence: Dict[str, FailureEvidence] = {
            failure_id: FailureEvidence(**data) for failure_id, data in self._evidence_ns.items()
        }

    def inspect(self, evidence: FailureEvidence) -> FailureDiagnosis:
        """ตรวจสอบ failure evidence"""
        category = self._classify(evidence)
        likely_cause = self._find_likely_cause(evidence, category)
        root_cause = self._find_root_cause(evidence, category, likely_cause)
        confidence = self._calculate_confidence(evidence, category)

        diagnosis = FailureDiagnosis(
            failure_id=evidence.failure_id,
            category=category,
            likely_cause=likely_cause,
            root_cause=root_cause,
            confidence=confidence,
            suggested_fix=self._suggest_fix(category, root_cause),
            related_files=self._find_related_files(evidence),
        )

        self._history.append(diagnosis)
        self._evidence[evidence.failure_id] = evidence
        self._evidence_ns[evidence.failure_id] = evidence.to_dict()
        self._store.save()
        return diagnosis

    def _classify(self, evidence: FailureEvidence) -> str:
        """จัดหมวดหมู่ failure ด้วย weighted pattern matching (ดู ERROR_PATTERNS
        - pattern เจาะจงมี weight สูงกว่า pattern ทั่วไปที่ overlap กันได้หลาย
        category เพื่อกัน tie-break แบบสุ่ม)
        """
        text_to_check = " ".join(filter(None, [
            evidence.actual,
            evidence.server_log or "",
            evidence.console_log or "",
            evidence.response_body or "",
        ])).lower()

        scores: Dict[str, int] = {}
        for category, pattern, weight in self.ERROR_PATTERNS:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                scores[category] = scores.get(category, 0) + weight

        if not scores:
            return "unknown"

        return max(scores, key=scores.get)

    def _find_likely_cause(self, evidence: FailureEvidence, category: str) -> str:
        """หาสาเหตุที่น่าจะเป็น"""
        if category == "database":
            if "foreign key" in (evidence.server_log or "").lower():
                return "Invalid foreign key value"
            if "unique constraint" in (evidence.server_log or "").lower():
                return "Duplicate data insertion"
            if "timeout" in (evidence.server_log or "").lower():
                return "Database connection timeout"
            return "Database error"

        elif category == "api":
            if "500" in evidence.actual:
                return "Internal server error"
            if "404" in evidence.actual:
                return "Endpoint not found"
            if "403" in evidence.actual:
                return "Authorization failed"
            return "API error"

        elif category == "ui":
            if "not found" in evidence.actual.lower():
                return "Element selector changed or element not rendered"
            if "timeout" in evidence.actual.lower():
                return "Page load timeout or async operation not complete"
            return "UI interaction error"

        elif category == "network":
            return "Network connectivity or CORS issue"

        elif category == "auth":
            if "401" in evidence.actual or "unauthorized" in evidence.actual.lower():
                return "Missing or invalid authentication credentials"
            if "403" in evidence.actual or "forbidden" in evidence.actual.lower():
                return "Authenticated but not authorized for this action"
            if "token" in evidence.actual.lower() or "jwt" in evidence.actual.lower():
                return "Expired or malformed auth token"
            return "Authentication/authorization failure"

        elif category == "validation":
            return "Input failed server-side validation - client sent data outside accepted format/range"

        elif category == "browser":
            return "Browser process crashed or navigation did not complete before the next action"

        elif category == "concurrency":
            if "deadlock" in evidence.actual.lower():
                return "Two operations acquired locks in conflicting order"
            if "double" in evidence.actual.lower() or "duplicate" in evidence.actual.lower():
                return "Action was submitted more than once without de-duplication"
            return "Race condition between concurrent operations"

        elif category == "resource":
            return "Process exceeded available memory/disk/file-handle limits"

        elif category == "filesystem":
            return "Expected file/path does not exist or is not accessible"

        elif category == "configuration":
            return "Required environment variable or config value is missing"

        elif category == "third_party":
            return "External/third-party service returned an error or rate-limited the request"

        elif category == "mobile":
            return "Mobile app crashed, hung (ANR), or the Appium session was not properly initialized"

        elif category == "security":
            return "Backend leaked internal error details or a security control blocked the request unexpectedly"

        elif category == "logic":
            return "Actual result diverged from expected - assertion or business logic mismatch"

        return "Unknown cause"

    def _find_root_cause(self, evidence: FailureEvidence, category: str, likely_cause: str) -> str:
        """หา root cause ลึกขึ้น"""
        # ตัวอย่าง: ถ้า database FK error
        if category == "database" and "foreign key" in likely_cause.lower():
            if evidence.database_state:
                # ตรวจสอบว่า FK value = 0 หรือ null
                for table, data in evidence.database_state.items():
                    for row in data:
                        for col, val in row.items():
                            if val == 0 and "id" in col.lower():
                                return f"{col} = 0 is invalid foreign key reference in table {table}"
            return "Backend sends invalid FK value or missing validation"

        if category == "api" and "500" in likely_cause:
            if evidence.server_log:
                # หา stack trace ล่าสุด
                lines = evidence.server_log.split("\n")
                for line in lines:
                    if "Error:" in line or "Exception" in line:
                        return f"Server exception: {line.strip()}"
            return "Unhandled server exception"

        if category == "ui":
            if evidence.screenshot:
                return "UI state mismatch - check screenshot for visual regression"
            return "Element state changed during test execution"

        return likely_cause

    def _calculate_confidence(self, evidence: FailureEvidence, category: str) -> float:
        """คำนวณความมั่นใจ"""
        confidence = 50.0

        # มี screenshot → +10
        if evidence.screenshot:
            confidence += 10

        # มี server log → +15
        if evidence.server_log:
            confidence += 15

        # มี database state → +15
        if evidence.database_state:
            confidence += 15

        # มี console log → +5
        if evidence.console_log:
            confidence += 5

        # มี network requests → +5
        if evidence.network_requests:
            confidence += 5

        return min(confidence, 99.0)

    def _suggest_fix(self, category: str, root_cause: str) -> str:
        """เสนอการแก้ไข"""
        suggestions = {
            "database": "Add FK validation before insert/update. Check referenced table exists.",
            "api": "Add error handling and input validation. Check server logs for exception details.",
            "ui": "Update selector or add wait conditions. Check for dynamic content loading.",
            "network": "Check CORS configuration, API endpoint availability, and network stability.",
            "logic": "Review assertion logic and expected values. Check data setup.",
            "auth": "Verify token refresh/expiry handling and that authorization checks match the intended role/permission model.",
            "validation": "Align client-side and server-side validation rules; return field-level error details instead of a generic 400.",
            "browser": "Add explicit navigation/wait conditions; check for JS errors or excessive memory use causing renderer crashes.",
            "concurrency": "Add locking/transaction isolation or idempotency keys to prevent duplicate/racing operations.",
            "resource": "Profile memory/file-handle usage; add resource limits and graceful degradation instead of a hard crash.",
            "filesystem": "Verify the expected path exists in this environment and that the process has the required permissions.",
            "configuration": "Add startup validation that fails fast with a clear message when required config/env vars are missing.",
            "third_party": "Add retry/backoff and circuit-breaking around the third-party call; verify current rate limits and credentials.",
            "mobile": "Check device/emulator logs for the crash/ANR stack trace; verify the Appium session was created before interacting.",
            "security": "Ensure errors are caught and sanitized before reaching the client; review WAF/security rules against legitimate traffic.",
        }
        return suggestions.get(category, "Review code and logs for root cause.")

    def _find_related_files(self, evidence: FailureEvidence) -> List[str]:
        """หาไฟล์ที่เกี่ยวข้อง"""
        files = []
        if evidence.server_log:
            # หา file paths จาก stack trace
            import re
            matches = re.findall(r'File "([^"]+)"', evidence.server_log)
            files.extend(matches)
        return list(set(files))[:5]

    def compare_runs(self, run1: Dict[str, Any], run2: Dict[str, Any]) -> Dict[str, Any]:
        """เปรียบเทียบผลลัพธ์ระหว่าง 2 test runs จริง (รับ TestRun.to_dict() ของทั้งคู่)

        - new_failures: test ที่ผ่านใน run1 แต่ fail ใน run2
        - fixed_failures: test ที่ fail ใน run1 แต่ผ่านใน run2
        - regressions: alias ของ new_failures (มุมมอง "สิ่งที่พังเพิ่ม")
        - still_failing: fail ทั้งสอง run
        """
        status1 = {r["test_id"]: r["status"] for r in run1.get("results", [])}
        status2 = {r["test_id"]: r["status"] for r in run2.get("results", [])}

        new_failures, fixed_failures, still_failing = [], [], []
        for test_id, s2 in status2.items():
            s1 = status1.get(test_id)
            if s1 == "passed" and s2 in ("failed", "error"):
                new_failures.append(test_id)
            elif s1 in ("failed", "error") and s2 == "passed":
                fixed_failures.append(test_id)
            elif s1 in ("failed", "error") and s2 in ("failed", "error"):
                still_failing.append(test_id)

        return {
            "run1": run1.get("run_id"),
            "run2": run2.get("run_id"),
            "new_failures": new_failures,
            "fixed_failures": fixed_failures,
            "still_failing": still_failing,
            "regressions": new_failures,
        }

    def find_regression(self, current_results: List[Dict], baseline_results: List[Dict]) -> List[Dict]:
        """หา regression"""
        baseline_passed = {r["test_id"] for r in baseline_results if r["status"] == "passed"}
        regressions = []
        for r in current_results:
            if r["test_id"] in baseline_passed and r["status"] == "failed":
                regressions.append(r)
        return regressions

    def get_evidence(self, failure_id: str) -> Optional[FailureEvidence]:
        """ดึง evidence จริงที่เก็บไว้ตอน inspect() (เก็บใน memory ของ process นี้)"""
        return self._evidence.get(failure_id)


# MCP Tools
# Shared singleton so get_evidence/compare_runs can see evidence recorded by
# earlier failure.inspect calls in the same session, instead of each call
# getting a blank analyzer with no history.
_analyzer = FailureAnalyzer()


async def failure_inspect(failure_id: str, test_name: str, expected: str, actual: str,
                          screenshot: Optional[str] = None,
                          server_log: Optional[str] = None,
                          console_log: Optional[str] = None) -> Dict[str, Any]:
    """MCP tool: failure.inspect"""
    evidence = FailureEvidence(
        failure_id=failure_id,
        test_name=test_name,
        expected=expected,
        actual=actual,
        screenshot=screenshot,
        server_log=server_log,
        console_log=console_log,
        timestamp=datetime.now().isoformat(),
    )
    diagnosis = _analyzer.inspect(evidence)
    return diagnosis.to_dict()


async def failure_classify(failure_id: str, actual: str) -> str:
    """MCP tool: failure.classify"""
    evidence = FailureEvidence(
        failure_id=failure_id,
        test_name="",
        expected="",
        actual=actual,
        timestamp=datetime.now().isoformat(),
    )
    return _analyzer._classify(evidence)


async def failure_find_root_cause(failure_id: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    """MCP tool: failure.find_root_cause"""
    ev = FailureEvidence(**evidence)
    diagnosis = _analyzer.inspect(ev)
    return {
        "root_cause": diagnosis.root_cause,
        "confidence": diagnosis.confidence,
        "suggested_fix": diagnosis.suggested_fix,
    }


async def failure_get_evidence(failure_id: str) -> Dict[str, Any]:
    """MCP tool: failure.get_evidence - ดึง evidence จริงที่เคยเก็บไว้ตอน inspect()"""
    evidence = _analyzer.get_evidence(failure_id)
    if evidence is None:
        return {"error": f"No evidence found for '{failure_id}' - เรียก failure.inspect ก่อน"}
    return evidence.to_dict()


async def failure_compare_runs(run1_id: str, run2_id: str) -> Dict[str, Any]:
    """MCP tool: failure.compare_runs - เทียบ 2 test run จริง (ต้องรันผ่าน test.create_run มาก่อน) หา new_failures/fixed_failures/regressions
    ใช้ได้แม้ run นั้นถูกสร้างใน process ก่อนหน้า (persist ไว้แล้ว)
    """
    from qa_mcp.execution.executor import _executor

    run1 = _executor.get_run_dict(run1_id)
    run2 = _executor.get_run_dict(run2_id)
    if run1 is None or run2 is None:
        missing = run1_id if run1 is None else run2_id
        return {"error": f"Run '{missing}' not found - เรียก test.create_run แล้ว test.run ก่อน"}
    return _analyzer.compare_runs(run1, run2)
