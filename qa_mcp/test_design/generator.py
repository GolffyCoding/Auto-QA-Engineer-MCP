"""
Phase 2: Test Design
ให้ LLM คิดแบบ QA Engineer ในการสร้าง test cases
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class TestCategory(Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    BOUNDARY = "Boundary"
    SECURITY = "Security"
    REGRESSION = "Regression"
    SMOKE = "Smoke"
    E2E = "E2E"
    API = "API"
    BUSINESS_LOGIC = "Business Logic"
    ACCESS_CONTROL = "Access Control"
    UX_STATE = "UX State"
    STATE_TRANSITION = "State Transition"


class TestPriority(Enum):
    CRITICAL = "P0 - Critical"
    HIGH = "P1 - High"
    MEDIUM = "P2 - Medium"
    LOW = "P3 - Low"


@dataclass
class TestCase:
    """Test case ที่สร้างขึ้น"""
    id: str
    title: str
    category: str
    priority: str
    preconditions: List[str]
    steps: List[str]
    expected_result: str
    automation_ready: bool = False
    target_framework: str = "playwright"
    tags: List[str] = field(default_factory=list)
    rationale: str = ""  # หลักการ/เหตุผลที่ระบบสร้าง case นี้ (BVA, Equivalence Partitioning, OWASP, ...)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestSuite:
    """ชุด test cases"""
    feature: str
    cases: List[TestCase] = field(default_factory=list)

    def add(self, case: TestCase):
        self.cases.append(case)

    def by_category(self, category: str) -> List[TestCase]:
        return [c for c in self.cases if c.category == category]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature,
            "total": len(self.cases),
            "cases": [c.to_dict() for c in self.cases],
        }


class TestDesigner:
    """ออกแบบ test cases ตามหลักการ QA

    หลักการที่ระบบใช้สร้าง edge case / worst case / security case แบบ
    deterministic (ไม่ต้องพึ่ง LLM คิดเอง เพื่อไม่ให้พลาดเคสพื้นฐาน):

    - Boundary Value Analysis (BVA): บั๊กมักอยู่ที่ขอบเขตของค่าที่รับได้
      (min-1, min, max, max+1) ไม่ใช่ตรงกลาง range
    - Equivalence Partitioning: แบ่ง input เป็นกลุ่ม (valid, empty,
      wrong-type) แล้วสุ่มตัวแทนกลุ่มละ 1 เคส แทนที่จะทดสอบทุกค่าที่เป็นไปได้
    - OWASP Top 10: ทุก field ที่รับ input จาก user คือช่องทาง injection
      ที่ต้องสมมติว่า "ไม่ปลอดภัยจนกว่าจะพิสูจน์ว่าปลอดภัย"
    - Worst-case/stress input: field ที่ไม่ประกาศ max length คือความเสี่ยง
      สูงสุดเรื่อง buffer/storage overflow เพราะไม่มีการป้องกันที่รู้ล่วงหน้า
    """

    # OWASP-mapped injection payloads - แต่ละตัวมี "why" (owasp) ติดไปด้วยเสมอ
    SECURITY_PAYLOADS = [
        {"name": "SQL Injection", "payload": "'; DROP TABLE users; --",
         "owasp": "OWASP A03:2021 Injection", "tag": "sql-injection"},
        {"name": "Cross-Site Scripting (XSS)", "payload": "<script>alert(1)</script>",
         "owasp": "OWASP A03:2021 Injection", "tag": "xss"},
        {"name": "Stored XSS via HTML attribute", "payload": "<img src=x onerror=alert(1)>",
         "owasp": "OWASP A03:2021 Injection", "tag": "xss"},
        {"name": "NoSQL Injection", "payload": "{\"$ne\": null}",
         "owasp": "OWASP A03:2021 Injection", "tag": "nosql-injection"},
        {"name": "Path Traversal", "payload": "../../../etc/passwd",
         "owasp": "OWASP A01:2021 Broken Access Control", "tag": "path-traversal"},
        {"name": "Server-Side Template Injection", "payload": "{{7*7}}",
         "owasp": "OWASP A03:2021 Injection", "tag": "ssti"},
        {"name": "OS Command Injection", "payload": "$(whoami)",
         "owasp": "OWASP A03:2021 Injection", "tag": "command-injection"},
        {"name": "Authentication Bypass via SQLi", "payload": "admin' OR '1'='1",
         "owasp": "OWASP A07:2021 Identification and Authentication Failures", "tag": "auth-bypass"},
    ]

    # Equivalence Partitioning: ตัวอย่าง "invalid class" ต่อ field type
    FIELD_TYPE_INVALID_SAMPLES: Dict[str, List[str]] = {
        "email": ["not-an-email", "missing-at-sign.com", "@no-local-part.com"],
        "number": ["abc", "1.2.3"],
        "integer": ["abc", "12.5"],
        "date": ["2026-13-45", "not-a-date"],
        "url": ["not a url", "javascript:alert(1)"],
        "phone": ["abc-def-ghij", "12"],
    }

    # field types ที่ระบบถือว่า "รับ input อิสระจาก user" จึงต้องผ่าน security probe
    # (select/checkbox/date ไม่รวม เพราะ user เลือกจากตัวเลือกที่กำหนดไว้แล้ว)
    INJECTABLE_FIELD_TYPES = {"text", "textarea", "email", "url", "search", "password", "phone"}

    def __init__(self, feature_name: str):
        self.suite = TestSuite(feature=feature_name)
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"TC-{self._counter:04d}"

    def generate_field_based_tests(self, fields: List[Dict[str, Any]], feature_name: Optional[str] = None) -> TestSuite:
        """สร้าง edge/worst/security case จาก field spec แบบมีหลักการ - นี่คือ
        baseline ที่ระบบรับผิดชอบเอง ไม่ต้องรอ LLM คิด

        fields: [{"name": "email", "type": "email", "required": True, "max_length": 255}, ...]
        type ที่รองรับ: text, textarea, email, password, number, integer, date, url, phone, select
        """
        feature_name = feature_name or self.suite.feature
        self.suite = TestSuite(feature=feature_name)

        # 1) Positive - Equivalence Partitioning: ตัวแทนของ "all-valid" class
        self.suite.add(TestCase(
            id=self._next_id(),
            title=f"{feature_name} - submit with all valid values",
            category=TestCategory.POSITIVE.value,
            priority=TestPriority.CRITICAL.value,
            preconditions=[f"{feature_name} is accessible"],
            steps=[f"Enter a valid value for '{f['name']}'" for f in fields] + ["Submit"],
            expected_result="Submission succeeds; data is persisted/processed correctly",
            automation_ready=True,
            rationale="Equivalence Partitioning: the 'all-valid' class is the baseline every other case is compared against",
            tags=[feature_name.lower(), "positive", "happy-path"],
        ))

        # 2) Negative - required field missing, tested ONE AT A TIME
        # (Equivalence Partitioning: isolate which field's validation actually fired,
        # so a bug in one field's check can't hide behind another field's check)
        for f in fields:
            if not f.get("required"):
                continue
            name = f["name"]
            self.suite.add(TestCase(
                id=self._next_id(),
                title=f"{feature_name} - missing required field '{name}'",
                category=TestCategory.NEGATIVE.value,
                priority=TestPriority.HIGH.value,
                preconditions=[f"{feature_name} is accessible"],
                steps=[f"Leave '{name}' empty", "Fill all other fields validly", "Submit"],
                expected_result=f"Validation error specifically on '{name}', submission blocked",
                automation_ready=True,
                rationale="Equivalence Partitioning: 'required field empty' is a distinct invalid class from a wrong-format value and must be rejected independently per field",
                tags=[feature_name.lower(), "negative", "required", name],
            ))

        # 3) Boundary Value Analysis - at/around declared length limits
        for f in fields:
            name = f["name"]
            max_len = f.get("max_length")
            min_len = f.get("min_length")

            if max_len:
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - '{name}' at max length ({max_len} chars)",
                    category=TestCategory.BOUNDARY.value,
                    priority=TestPriority.MEDIUM.value,
                    preconditions=[f"{feature_name} is accessible"],
                    steps=[f"Enter exactly {max_len} characters into '{name}'", "Submit"],
                    expected_result="Accepted - the declared limit itself is a valid value, not an error",
                    automation_ready=True,
                    rationale="Boundary Value Analysis: the upper boundary itself must be accepted, not just values comfortably below it",
                    tags=[feature_name.lower(), "boundary", name],
                ))
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - '{name}' exceeds max length ({max_len + 1} chars)",
                    category=TestCategory.BOUNDARY.value,
                    priority=TestPriority.HIGH.value,
                    preconditions=[f"{feature_name} is accessible"],
                    steps=[f"Enter {max_len + 1} characters into '{name}'", "Submit"],
                    expected_result="Rejected with a validation error, or safely truncated - never a raw overflow/crash/500",
                    automation_ready=True,
                    rationale="Boundary Value Analysis: one unit past the boundary is the single highest-yield invalid case for catching off-by-one validation bugs",
                    tags=[feature_name.lower(), "boundary", "overflow", name],
                ))
            else:
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - '{name}' with worst-case input (10,000 chars)",
                    category=TestCategory.BOUNDARY.value,
                    priority=TestPriority.HIGH.value,
                    preconditions=[f"{feature_name} is accessible"],
                    steps=[f"Enter 10,000 characters into '{name}'", "Submit"],
                    expected_result="Rejected gracefully or accepted within resource limits - never an unhandled crash/timeout/500",
                    automation_ready=True,
                    rationale="Worst-case/stress input: a field with no declared max length is the highest risk for buffer/storage overflow or DoS because no known limit protects it",
                    tags=[feature_name.lower(), "boundary", "worst-case", name],
                ))

            if min_len:
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - '{name}' below min length ({min_len - 1} chars)",
                    category=TestCategory.BOUNDARY.value,
                    priority=TestPriority.MEDIUM.value,
                    preconditions=[f"{feature_name} is accessible"],
                    steps=[f"Enter {max(min_len - 1, 0)} characters into '{name}'", "Submit"],
                    expected_result="Rejected with a validation error",
                    automation_ready=True,
                    rationale="Boundary Value Analysis: one unit below the lower boundary",
                    tags=[feature_name.lower(), "boundary", name],
                ))

        # 4) Negative - Equivalence Partitioning by declared data type
        for f in fields:
            name, ftype = f["name"], f.get("type", "text")
            for sample in self.FIELD_TYPE_INVALID_SAMPLES.get(ftype, [])[:2]:
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - '{name}' with malformed {ftype} ({sample!r})",
                    category=TestCategory.NEGATIVE.value,
                    priority=TestPriority.HIGH.value,
                    preconditions=[f"{feature_name} is accessible"],
                    steps=[f"Enter {sample!r} into '{name}' (declared type: {ftype})", "Submit"],
                    expected_result=f"Validation error - '{name}' rejects values outside the {ftype} format",
                    automation_ready=True,
                    rationale=f"Equivalence Partitioning: a malformed {ftype} is a distinct invalid class separate from 'empty' and must be caught by format validation, not just presence validation",
                    tags=[feature_name.lower(), "negative", "type-validation", name],
                ))

        # 5) Security - OWASP injection probes on every field that accepts free-form input
        for f in fields:
            name, ftype = f["name"], f.get("type", "text")
            if ftype not in self.INJECTABLE_FIELD_TYPES:
                continue
            for spec in self.SECURITY_PAYLOADS:
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - '{name}' {spec['name']}",
                    category=TestCategory.SECURITY.value,
                    priority=TestPriority.CRITICAL.value,
                    preconditions=[f"{feature_name} is accessible"],
                    steps=[f"Enter payload `{spec['payload']}` into '{name}'", "Submit"],
                    expected_result="Payload is sanitized/escaped/parameterized - no injection executed, no raw error/stack trace leaked",
                    automation_ready=True,
                    rationale=f"{spec['owasp']}: any user-controllable input reaching storage, a template renderer, a shell, or a query is a potential injection point - assume unsafe until proven otherwise",
                    tags=[feature_name.lower(), "security", spec["tag"], name],
                ))

        return self.suite

    # Template ของ UX state ที่พบบ่อย - LLM แค่บอกชื่อ state ("loading", "empty", ...)
    # ตามที่ feature นั้นมีจริง ระบบขยายเป็น test case ที่มี expected behavior มาตรฐานให้เอง
    UX_STATE_TEMPLATES: Dict[str, Dict[str, str]] = {
        "loading": {
            "steps": "Trigger the action and observe the UI before the response returns",
            "expected": "A loading indicator is shown; the trigger control is disabled to prevent duplicate submission",
            "rationale": "UX principle: an unindicated wait reads as a frozen/broken UI, and an un-disabled control invites duplicate/double-submit actions",
        },
        "empty": {
            "steps": "Load the view when there is no data to show",
            "expected": "An explicit empty state is shown (not a blank screen, not a spinner stuck forever)",
            "rationale": "UX principle: a blank screen is indistinguishable from a loading or broken state to the user",
        },
        "error": {
            "steps": "Trigger the action while the backend/network returns an error",
            "expected": "A user-facing error message is shown with a way to retry - not a raw stack trace or silent failure",
            "rationale": "UX principle: unhandled errors either crash the UI or fail silently, both of which hide real problems from the user and from QA",
        },
        "offline": {
            "steps": "Trigger the action with no network connectivity",
            "expected": "A clear offline/connectivity error is shown; no data loss and no indefinite hang",
            "rationale": "UX principle: network calls without a timeout/offline path hang indefinitely from the user's perspective",
        },
        "disabled": {
            "steps": "Attempt the action while its preconditions are not met (e.g. required fields incomplete)",
            "expected": "The control is disabled/blocked before submission, not after a failed round-trip",
            "rationale": "UX principle: catching invalid state client-side before submission is cheaper and clearer than a round-trip failure",
        },
        "success": {
            "steps": "Complete the action successfully",
            "expected": "Clear success confirmation is shown (message/redirect/state change) so the user knows the action actually happened",
            "rationale": "UX principle: silent success is indistinguishable from a swallowed failure to the user",
        },
        "concurrent": {
            "steps": "Trigger the same action twice in rapid succession (e.g. double-click submit)",
            "expected": "Only one submission is processed - duplicate is blocked or de-duplicated, not processed twice",
            "rationale": "UX + Business Logic: UI-level race conditions (double submit) are one of the most common production bugs in form-driven flows",
        },
    }

    def generate_flow_based_tests(
        self,
        feature_name: str,
        business_rules: Optional[List[Dict[str, Any]]] = None,
        roles: Optional[List[Dict[str, Any]]] = None,
        ux_states: Optional[List[str]] = None,
        states: Optional[Dict[str, Any]] = None,
        append: bool = False,
    ) -> TestSuite:
        """สร้าง test case จาก business logic / access control / UX state / state
        machine ที่ LLM เป็นคนเข้าใจ flow จริงของงานนั้น ๆ แล้วบอกมาเป็นโครงสร้าง
        (ไม่ใช่เขียน test case เอง) - ระบบรับผิดชอบขยายแต่ละอย่างให้เป็น test case
        ที่มี rationale กำกับเสมอ เหมือน generate_field_based_tests แต่คนละมิติ

        business_rules: [{"name": "...", "rule": "invariant ที่ต้องเป็นจริงเสมอ",
                           "violation": "วิธีที่จะพยายามละเมิด invariant นี้"}]
        roles:          [{"role": "admin", "should_access": True}, {"role": "guest", "should_access": False}]
        ux_states:      ["loading", "empty", "error", "offline", ...] (ดู UX_STATE_TEMPLATES)
        states:         {"initial": "pending", "transitions": [
                            {"from": "pending", "to": "paid", "action": "complete_payment"},
                            {"from": "paid", "to": "shipped", "action": "ship_order"},
                            ...
                         ]}
                         -> generate ครอบคลุม "ทุกเคส" ของ state × action matrix จริง
                         (ไม่ใช่แค่ transition ที่ valid) ดู _generate_state_cycle_cases
        append:         True = ต่อเข้า suite ที่มีอยู่แล้ว (เช่นจาก generate_field_based_tests)
                         แทนที่จะเริ่ม suite ใหม่ - ใช้ตอนอยาก generate field-level +
                         flow-level cases ให้เป็น suite เดียวกัน
        """
        if not (append and self.suite.feature == feature_name):
            self.suite = TestSuite(feature=feature_name)

        # Business Logic: แต่ละ rule ต้องมีทั้งเคสที่ invariant คงอยู่ (positive)
        # และเคสที่พยายามละเมิดแล้วต้องถูกระบบสกัดไว้ (negative)
        for rule in business_rules or []:
            name = rule["name"]
            invariant = rule["rule"]
            self.suite.add(TestCase(
                id=self._next_id(),
                title=f"{feature_name} - business rule holds: {name}",
                category=TestCategory.BUSINESS_LOGIC.value,
                priority=TestPriority.CRITICAL.value,
                preconditions=[f"{feature_name} is in normal operating state"],
                steps=["Perform the normal flow"],
                expected_result=f"Invariant holds: {invariant}",
                automation_ready=False,
                rationale="Business Logic invariant: this rule defines correctness for this feature and must be verified under normal operation, not assumed",
                tags=[feature_name.lower(), "business-logic", name],
            ))
            if rule.get("violation"):
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - reject violation of: {name}",
                    category=TestCategory.BUSINESS_LOGIC.value,
                    priority=TestPriority.CRITICAL.value,
                    preconditions=[f"{feature_name} is accessible"],
                    steps=[rule["violation"]],
                    expected_result=f"System blocks or safely rejects the attempt - invariant '{invariant}' is never violated, even transiently",
                    automation_ready=False,
                    rationale="Business Logic: an invariant that is only checked on the happy path isn't actually enforced - it must be proven to hold under an explicit attempt to break it",
                    tags=[feature_name.lower(), "business-logic", "negative", name],
                ))

        # Access Control: แต่ละ role ต้องมีเคสยืนยันสิทธิ์ตรงตามที่ระบุ (OWASP A01)
        for r in roles or []:
            role, should_access = r["role"], r.get("should_access", False)
            expected = (
                f"Access granted - role '{role}' can perform this action"
                if should_access else
                f"Access denied (403/redirect) - role '{role}' must NOT be able to perform this action"
            )
            self.suite.add(TestCase(
                id=self._next_id(),
                title=f"{feature_name} - access as role '{role}' ({'allowed' if should_access else 'denied'})",
                category=TestCategory.ACCESS_CONTROL.value,
                priority=TestPriority.CRITICAL.value,
                preconditions=[f"User is authenticated with role '{role}'"],
                steps=[f"Attempt to perform {feature_name} as role '{role}'"],
                expected_result=expected,
                automation_ready=False,
                rationale="OWASP A01:2021 Broken Access Control: authorization must be verified explicitly per role - an endpoint that merely checks authentication (not authorization) silently permits privilege escalation",
                tags=[feature_name.lower(), "access-control", role],
            ))

        # UX states: LLM บอกแค่ชื่อ state ที่ feature นี้มีจริง ระบบขยาย expected behavior ให้
        for state in ux_states or []:
            template = self.UX_STATE_TEMPLATES.get(state.lower())
            if not template:
                continue
            self.suite.add(TestCase(
                id=self._next_id(),
                title=f"{feature_name} - UX state: {state}",
                category=TestCategory.UX_STATE.value,
                priority=TestPriority.MEDIUM.value,
                preconditions=[f"{feature_name} is accessible"],
                steps=[template["steps"]],
                expected_result=template["expected"],
                automation_ready=False,
                rationale=template["rationale"],
                tags=[feature_name.lower(), "ux", state.lower()],
            ))

        # State cycle: exhaustive state x action matrix, not just the happy path
        if states:
            self._generate_state_cycle_cases(feature_name, states)

        return self.suite

    def _generate_state_cycle_cases(self, feature_name: str, states: Dict[str, Any]) -> None:
        """สร้าง test case ครอบคลุม state machine แบบ 'ครบทุกเคส' จริง ๆ:

        1. Valid transition coverage - ทุก transition ที่ประกาศไว้ต้องมีเคสยืนยันว่าทำงานได้
        2. Invalid transition coverage (exhaustive) - สำหรับทุก action ที่มีอยู่ใน state
           machine นี้ ลองใช้ action นั้นจากทุก state ที่ "ไม่ใช่" from-state ที่ถูกต้อง
           แล้วต้องถูกระบบบล็อค - นี่คือส่วนที่ทำให้ coverage เป็น "ทุกเคส" จริง ไม่ใช่
           สุ่มทดสอบแค่บาง transition
        3. Unreachable state detection - หา state ที่ไม่มีทางไปถึงได้จาก initial state
           (BFS) แล้ว flag เป็นเคส Regression เพื่อให้ QA ไปตรวจสอบว่าเป็น dead state
           จริงหรือ transition ตกหล่นไป
        """
        initial = states["initial"]
        transitions = states["transitions"]

        all_states = {initial}
        all_actions = set()
        valid_pairs = {}  # (from_state, action) -> to_state
        for t in transitions:
            all_states.add(t["from"])
            all_states.add(t["to"])
            all_actions.add(t["action"])
            valid_pairs[(t["from"], t["action"])] = t["to"]

        # 1) Valid transitions - positive coverage
        for t in transitions:
            self.suite.add(TestCase(
                id=self._next_id(),
                title=f"{feature_name} - transition {t['from']} -> {t['to']} via '{t['action']}'",
                category=TestCategory.STATE_TRANSITION.value,
                priority=TestPriority.CRITICAL.value,
                preconditions=[f"{feature_name} is in state '{t['from']}'"],
                steps=[f"Perform action '{t['action']}'"],
                expected_result=f"State transitions from '{t['from']}' to '{t['to']}'",
                automation_ready=False,
                rationale="State transition coverage: every declared transition must be proven to actually happen, not just assumed from the state diagram",
                tags=[feature_name.lower(), "state-transition", t["action"]],
            ))

        # 2) Invalid transitions - EXHAUSTIVE: every (state, action) pair that is
        # NOT a declared valid transition must be proven blocked. This is the
        # "every case" part - covers the full state x action matrix, not a sample.
        for state in sorted(all_states):
            for action in sorted(all_actions):
                if (state, action) in valid_pairs:
                    continue
                self.suite.add(TestCase(
                    id=self._next_id(),
                    title=f"{feature_name} - reject '{action}' while in state '{state}'",
                    category=TestCategory.STATE_TRANSITION.value,
                    priority=TestPriority.HIGH.value,
                    preconditions=[f"{feature_name} is in state '{state}'"],
                    steps=[f"Attempt action '{action}' (not a valid transition from '{state}')"],
                    expected_result=f"Action is rejected; state remains '{state}' - no undeclared transition occurs",
                    automation_ready=False,
                    rationale="State transition coverage: an action valid from one state must be explicitly rejected from every other state - otherwise the state machine can be forced into an invalid/inconsistent state",
                    tags=[feature_name.lower(), "state-transition", "negative", state, action],
                ))

        # 3) Unreachable state detection (BFS from initial)
        reachable = {initial}
        frontier = [initial]
        while frontier:
            current = frontier.pop()
            for (from_state, _action), to_state in valid_pairs.items():
                if from_state == current and to_state not in reachable:
                    reachable.add(to_state)
                    frontier.append(to_state)

        unreachable = sorted(all_states - reachable)
        if unreachable:
            self.suite.add(TestCase(
                id=self._next_id(),
                title=f"{feature_name} - investigate unreachable state(s): {', '.join(unreachable)}",
                category=TestCategory.REGRESSION.value,
                priority=TestPriority.MEDIUM.value,
                preconditions=[],
                steps=[f"Review whether state(s) {unreachable} should be reachable from '{initial}', and add the missing transition(s) if so"],
                expected_result="Either every declared state is reachable, or unreachable states are confirmed dead/deprecated and removed",
                automation_ready=False,
                rationale="State coverage analysis (graph reachability from initial state): an unreachable state is either dead code or a missing transition - both are bugs worth surfacing before they're found in production",
                tags=[feature_name.lower(), "state-transition", "coverage-gap"],
            ))

    # Built-in field spec for the (extremely common) login form - lets
    # test.generate("login") work out of the box without the caller having
    # to describe the form, while still going through the same principled
    # field-based engine as any other feature.
    LOGIN_FIELDS_PRESET = [
        {"name": "email", "type": "email", "required": True, "max_length": 255},
        {"name": "password", "type": "password", "required": True, "min_length": 8, "max_length": 128},
    ]

    def generate_login_tests(self) -> TestSuite:
        """สร้าง test cases สำหรับ Login: baseline จาก field-based engine +
        flow-level cases ที่เฉพาะกับ auth (rate limiting, session fixation, ...)
        ซึ่งเป็น domain knowledge ที่ field spec เพียงอย่างเดียวบอกไม่ได้
        """
        self.generate_field_based_tests(self.LOGIN_FIELDS_PRESET, feature_name="Login")
        self._add_login_flow_cases()
        return self.suite

    def _add_login_flow_cases(self) -> None:
        """Flow-level cases เฉพาะของ authentication ที่ field spec ทั่วไปบอกไม่ได้
        (ไม่ใช่ผลจาก field type/length แต่มาจาก business rule ของระบบ auth)
        """
        self.suite.add(TestCase(
            id=self._next_id(),
            title="Login with Remember Me enabled",
            category=TestCategory.POSITIVE.value,
            priority=TestPriority.HIGH.value,
            preconditions=["User account exists"],
            steps=["Enter valid credentials", "Check 'Remember Me'", "Click Login"],
            expected_result="Session persists after browser restart",
            automation_ready=True,
            rationale="Domain knowledge: 'Remember Me' changes session lifetime behavior and isn't derivable from field validation rules alone",
            tags=["login", "remember-me", "session"],
        ))
        self.suite.add(TestCase(
            id=self._next_id(),
            title="Session persistence across tabs",
            category=TestCategory.POSITIVE.value,
            priority=TestPriority.HIGH.value,
            preconditions=["User is logged in"],
            steps=["Login successfully", "Open new tab", "Navigate to an authenticated page"],
            expected_result="User remains authenticated in the new tab",
            automation_ready=True,
            rationale="Domain knowledge: session sharing across tabs is a common auth implementation bug class",
            tags=["login", "session", "persistence"],
        ))
        self.suite.add(TestCase(
            id=self._next_id(),
            title="Login with wrong password (correct email)",
            category=TestCategory.NEGATIVE.value,
            priority=TestPriority.CRITICAL.value,
            preconditions=["User account exists"],
            steps=["Enter valid email", "Enter wrong password", "Click Login"],
            expected_result="Generic 'Invalid credentials' error - must NOT reveal whether the email or password was wrong",
            automation_ready=True,
            rationale="OWASP A07:2021 Identification and Authentication Failures: field-specific error messages let an attacker enumerate valid accounts",
            tags=["login", "negative", "user-enumeration"],
        ))
        self.suite.add(TestCase(
            id=self._next_id(),
            title="Login with locked account",
            category=TestCategory.NEGATIVE.value,
            priority=TestPriority.HIGH.value,
            preconditions=["Account is locked after N failed attempts"],
            steps=["Enter valid credentials for a locked account", "Click Login"],
            expected_result="Clear 'account locked' error, login blocked even with correct credentials",
            automation_ready=True,
            rationale="Domain knowledge: account lockout state is a business rule, not a field-level validation concern",
            tags=["login", "security", "lockout"],
        ))
        self.suite.add(TestCase(
            id=self._next_id(),
            title="Brute-force rate limiting",
            category=TestCategory.SECURITY.value,
            priority=TestPriority.CRITICAL.value,
            preconditions=["Rate limiting is enabled"],
            steps=["Attempt login 10+ times with wrong password within 1 minute"],
            expected_result="Account locked or IP/requester throttled after a threshold - not unlimited attempts",
            automation_ready=True,
            rationale="OWASP A07:2021: unlimited login attempts make credential-stuffing and brute-force attacks trivial",
            tags=["login", "security", "brute-force", "rate-limit"],
        ))
        self.suite.add(TestCase(
            id=self._next_id(),
            title="Session fixation protection",
            category=TestCategory.SECURITY.value,
            priority=TestPriority.HIGH.value,
            preconditions=["User has a pre-login session ID"],
            steps=["Capture session ID before login", "Login with valid credentials", "Check session ID after login"],
            expected_result="Session ID is regenerated after successful login, not reused",
            automation_ready=True,
            rationale="OWASP A07:2021: reusing the pre-auth session ID lets an attacker who fixed that ID hijack the authenticated session",
            tags=["login", "security", "session-fixation"],
        ))

    def generate_api_tests(self, endpoint: str, method: str = "GET") -> TestSuite:
        """สร้าง API test cases"""
        self.suite = TestSuite(feature=f"API {method} {endpoint}")

        self.suite.add(TestCase(
            id=self._next_id(),
            title=f"{method} {endpoint} - Valid request",
            category=TestCategory.API.value,
            priority=TestPriority.CRITICAL.value,
            preconditions=["API is running", "Valid auth token"],
            steps=[
                f"Send {method} request to {endpoint}",
                "Include valid headers",
            ],
            expected_result="HTTP 200 with valid JSON schema",
            automation_ready=True,
            target_framework="postman",
            tags=["api", "positive"],
        ))

        self.suite.add(TestCase(
            id=self._next_id(),
            title=f"{method} {endpoint} - Unauthorized",
            category=TestCategory.API.value,
            priority=TestPriority.CRITICAL.value,
            preconditions=["API is running"],
            steps=[
                f"Send {method} request without auth header",
            ],
            expected_result="HTTP 401 Unauthorized",
            automation_ready=True,
            target_framework="postman",
            tags=["api", "negative", "auth"],
        ))

        self.suite.add(TestCase(
            id=self._next_id(),
            title=f"{method} {endpoint} - Invalid payload",
            category=TestCategory.API.value,
            priority=TestPriority.HIGH.value,
            preconditions=["API is running", "Valid auth token"],
            steps=[
                f"Send {method} request with malformed JSON",
            ],
            expected_result="HTTP 400 Bad Request with validation details",
            automation_ready=True,
            target_framework="postman",
            tags=["api", "negative", "validation"],
        ))

        return self.suite

    def analyze_coverage(
        self,
        existing_tests: List[Dict[str, Any]],
        feature: str,
        fields: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """วิเคราะห์ coverage หา missing cases - เทียบกับ reference suite ที่
        ตรงกับ feature จริง (ต้องมี fields ยกเว้น feature == "login" ที่มี preset ในตัว)
        """
        if fields:
            ref = self.generate_field_based_tests(fields, feature)
        elif feature.lower() == "login":
            ref = self.generate_login_tests()
        else:
            return {
                "error": (
                    f"ไม่มี reference suite สำหรับ feature '{feature}' - ต้องระบุ 'fields' "
                    "(list ของ field พร้อม type/required/max_length) เพื่อสร้าง reference "
                    "ที่ตรงกับ feature นี้จริง ๆ"
                )
            }

        existing_categories = set()
        for t in existing_tests:
            existing_categories.add(t.get("category", ""))

        missing = []
        for case in ref.cases:
            if case.category not in existing_categories:
                missing.append(case.to_dict())

        return {
            "feature": feature,
            "existing_count": len(existing_tests),
            "reference_count": len(ref.cases),
            "coverage_percent": round(len(existing_tests) / len(ref.cases) * 100, 1),
            "missing_categories": list(set(c.category for c in ref.cases if c.category not in existing_categories)),
            "suggested_cases": missing[:5],
        }

    @staticmethod
    def prioritize(cases: List[Any]) -> List[Dict[str, Any]]:
        """จัดลำดับความสำคัญ

        รับได้ทั้ง TestCase object และ plain dict - ในทางปฏิบัติ caller ทุกตัว
        ที่มาผ่าน MCP/CLI (JSON) ส่ง dict มาเสมอ (เช่น cases ที่ได้กลับมาจาก
        test.generate เอง) เดิม method นี้เรียก c.priority ตรง ๆ ซึ่ง crash
        ทันทีถ้า caller ส่ง dict มา - เป็น workflow ที่เกิดขึ้นจริงบ่อยที่สุด
        (generate แล้วต่อ prioritize) จึงต้อง fail-fast น้อยที่สุดคือรองรับ
        ทั้งสองแบบ และคืนเป็น dict เสมอเพื่อให้ JSON-serializable ผ่าน MCP
        """
        priority_order = {
            TestPriority.CRITICAL.value: 0,
            TestPriority.HIGH.value: 1,
            TestPriority.MEDIUM.value: 2,
            TestPriority.LOW.value: 3,
        }

        def as_dict(c):
            return c.to_dict() if hasattr(c, "to_dict") else c

        def priority_of(c):
            return c.get("priority") if isinstance(c, dict) else getattr(c, "priority", None)

        dict_cases = [as_dict(c) for c in cases]
        return sorted(dict_cases, key=lambda c: priority_order.get(priority_of(c), 99))


# MCP Tools
async def test_generate(
    feature: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    business_rules: Optional[List[Dict[str, Any]]] = None,
    roles: Optional[List[Dict[str, Any]]] = None,
    ux_states: Optional[List[str]] = None,
    states: Optional[Dict[str, Any]] = None,
    method: str = "GET",
) -> Dict[str, Any]:
    """MCP tool: test.generate

    ระบบรับผิดชอบสร้าง baseline edge case / worst case / security case /
    business logic / access control / UX state / state-cycle เอง ตามหลักการที่
    ยอมรับกันในวงการ QA (Boundary Value Analysis, Equivalence Partitioning,
    OWASP Top 10, UX heuristics, exhaustive state-machine coverage) - LLM ไม่
    ต้องคิด test case เอง มีหน้าที่แค่ "รายงานข้อเท็จจริง" ของ feature นั้นจากการ
    อ่านโค้ด/UI/spec จริง แล้วส่งเป็นโครงสร้างมาให้:

    - fields: field ของฟอร์ม/feature นี้ -> ได้ Positive/Negative/Boundary/Security
    - business_rules: invariant ทางธุรกิจที่ระบบต้องรักษาไว้เสมอ -> ได้ Business Logic
    - roles: role ที่เข้าถึง feature นี้ได้/ไม่ได้ -> ได้ Access Control
    - ux_states: state ของ UI ที่ feature นี้มีจริง (loading/empty/error/...) -> ได้ UX State
    - states: state machine (initial + transitions) ของ entity นี้ (เช่น order
      status) -> ได้ State Transition ครบทุก (state x action) combination จริง
      ไม่ใช่แค่ transition ที่ valid เท่านั้น

    ทุกมิติ optional และ**รวมกันเป็น suite เดียว**ได้ - ยิ่งบอกเยอะ ยิ่งได้ coverage กว้างขึ้น

    - ถ้า feature == "login" และไม่ส่ง fields มา: ใช้ built-in preset ทันที
    - ถ้า feature ขึ้นต้นด้วย "/" หรือ "http" และไม่ส่ง fields มา: ถือเป็น API endpoint
    - อื่น ๆ ต้องส่งอย่างน้อยหนึ่งใน fields/business_rules/roles/ux_states/states
    """
    designer = TestDesigner(feature)
    has_flow_input = business_rules or roles or ux_states or states

    if fields:
        suite = designer.generate_field_based_tests(fields, feature)
        if has_flow_input:
            suite = designer.generate_flow_based_tests(
                feature, business_rules=business_rules, roles=roles,
                ux_states=ux_states, states=states, append=True,
            )
    elif feature.lower() == "login" and not has_flow_input:
        suite = designer.generate_login_tests()
    elif feature.startswith("/") or feature.lower().startswith("http"):
        suite = designer.generate_api_tests(feature, method=method)
    elif has_flow_input:
        suite = designer.generate_flow_based_tests(
            feature, business_rules=business_rules, roles=roles, ux_states=ux_states, states=states,
        )
    else:
        return {
            "error": (
                f"ไม่รู้จัก feature '{feature}' - กรุณาระบุอย่างน้อยหนึ่งใน 'fields' / "
                "'business_rules' / 'roles' / 'ux_states' เพื่อให้ระบบ generate test case "
                "ให้เองตามหลักการ (ไม่ต้องคิด test case เอง แค่บอกข้อเท็จจริงของ feature นี้)"
            ),
            "example": {
                "fields": [{"name": "email", "type": "email", "required": True, "max_length": 255}],
                "business_rules": [{"name": "no-negative-balance", "rule": "account balance must never go below 0",
                                     "violation": "Attempt to withdraw more than the current balance"}],
                "roles": [{"role": "admin", "should_access": True}, {"role": "guest", "should_access": False}],
                "ux_states": ["loading", "empty", "error"],
                "states": {
                    "initial": "pending",
                    "transitions": [
                        {"from": "pending", "to": "paid", "action": "complete_payment"},
                        {"from": "paid", "to": "shipped", "action": "ship_order"},
                    ],
                },
            },
        }
    return suite.to_dict()


async def test_analyze_coverage(
    existing_tests: List[Dict],
    feature: str,
    fields: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """MCP tool: test.analyze_coverage"""
    designer = TestDesigner(feature)
    return designer.analyze_coverage(existing_tests, feature, fields=fields)
