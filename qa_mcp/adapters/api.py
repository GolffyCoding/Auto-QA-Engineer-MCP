"""
Phase 3: Automation Engine - API Adapter
Abstraction สำหรับ API testing
รองรับ REST, k6 (load testing)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import asyncio
import json
import os
import shutil
import tempfile
import httpx


@dataclass
class APIResponse:
    status_code: int
    headers: Dict[str, str]
    body: Any
    duration_ms: float
    request: Dict[str, Any]


class APIAdapter(ABC):
    """Abstract base สำหรับ API testing"""

    @abstractmethod
    async def request(self, method: str, url: str, 
                      headers: Optional[Dict] = None,
                      body: Optional[Any] = None,
                      params: Optional[Dict] = None) -> APIResponse:
        pass

    @abstractmethod
    async def assert_status(self, response: APIResponse, expected: int) -> bool:
        pass

    @abstractmethod
    async def assert_schema(self, response: APIResponse, schema: Dict) -> bool:
        pass

    @abstractmethod
    async def assert_header(self, response: APIResponse, key: str, expected: str) -> bool:
        pass


class RESTAdapter(APIAdapter):
    """REST API adapter ใช้ httpx"""

    def __init__(self, base_url: str = "", default_headers: Optional[Dict] = None):
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self._client = None

    async def _get_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.default_headers,
                timeout=30.0,
            )
        return self._client

    async def request(self, method: str, url: str,
                      headers: Optional[Dict] = None,
                      body: Optional[Any] = None,
                      params: Optional[Dict] = None) -> APIResponse:
        client = await self._get_client()
        import time
        start = time.time()
        response = await client.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=body if isinstance(body, dict) else None,
            data=body if not isinstance(body, dict) else None,
            params=params,
        )
        duration = (time.time() - start) * 1000

        body_content = None
        try:
            body_content = response.json()
        except:
            body_content = response.text

        return APIResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=body_content,
            duration_ms=duration,
            request={
                "method": method,
                "url": str(response.request.url),
                "headers": dict(response.request.headers),
                "body": body,
            },
        )

    async def assert_status(self, response: APIResponse, expected: int) -> bool:
        return response.status_code == expected

    async def assert_schema(self, response: APIResponse, schema: Dict) -> bool:
        """Validate JSON schema (simplified)"""
        if not isinstance(response.body, dict):
            return False

        def validate(data, schema_def):
            if schema_def.get("type") == "object":
                if not isinstance(data, dict):
                    return False
                for key, prop in schema_def.get("properties", {}).items():
                    if key not in data and schema_def.get("required", []) and key in schema_def["required"]:
                        return False
                    if key in data:
                        if not validate(data[key], prop):
                            return False
            elif schema_def.get("type") == "array":
                if not isinstance(data, list):
                    return False
                for item in data:
                    if not validate(item, schema_def.get("items", {})):
                        return False
            elif schema_def.get("type") == "string":
                return isinstance(data, str)
            elif schema_def.get("type") == "integer":
                return isinstance(data, int)
            elif schema_def.get("type") == "boolean":
                return isinstance(data, bool)
            return True

        return validate(response.body, schema)

    async def assert_header(self, response: APIResponse, key: str, expected: str) -> bool:
        return response.headers.get(key.lower()) == expected

    async def close(self):
        if self._client:
            await self._client.aclose()


def _find_k6_binary() -> str:
    """หา k6 binary จริงในเครื่อง - รองรับทั้ง PATH ปกติและตำแหน่งติดตั้งแบบ user-local"""
    candidates = [
        os.environ.get("QA_MCP_K6_BIN"),
        shutil.which("k6"),
        str(Path.home() / ".local" / "bin" / "k6"),
        "/usr/local/bin/k6",
        "/usr/bin/k6",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        "ไม่พบ k6 binary ในเครื่อง - ติดตั้งจาก https://k6.io/docs/get-started/installation/ "
        "หรือกำหนด path ผ่าน environment variable QA_MCP_K6_BIN"
    )


class K6Adapter(APIAdapter):
    """k6 load-testing adapter - รัน `k6 run` จริงทุกครั้ง (ไม่ใช่ stub)

    k6 ทำงานต่างจาก REST adapter ตรงที่ผลลัพธ์ของมันคือสถิติของ virtual
    users หลายตัวยิงพร้อมกัน ไม่ใช่ response เดี่ยว ๆ `request()` ที่นี่รัน
    load test แบบสั้น (1 VU, 1 iteration) เพื่อให้ตรงกับ interface ของ
    `APIAdapter` แต่ถ้าต้องการรัน load test จริงแบบมี virtual users/duration
    ให้ใช้ `run_load_test()` โดยตรง (ต่อกับ tool `api.load_test`)
    """

    # test_type -> k6 execution pattern, per StrongQA's performance-testing
    # taxonomy (https://strongqa.com/qa-portal/knowledge-base/testing-types/performance-testing):
    #   load      - flat vus/duration at the expected volume (default, unchanged behavior)
    #   stress    - ramps well beyond `vus` in stages to find the breaking point
    #   stability - a much longer, flat run (endurance/soak) to catch leaks/degradation
    #   spike     - a short, sudden burst far above `vus` then back down
    VALID_TEST_TYPES = {"load", "stress", "stability", "soak", "spike"}

    def __init__(self, k6_bin: Optional[str] = None):
        self._k6_bin = k6_bin or _find_k6_binary()

    async def run_load_test(
        self,
        url: str,
        method: str = "GET",
        vus: int = 1,
        duration: Optional[str] = None,
        iterations: Optional[int] = None,
        headers: Optional[Dict] = None,
        body: Optional[Any] = None,
        test_type: str = "load",
    ) -> Dict[str, Any]:
        """รัน k6 load test จริงกับ url ที่กำหนด แล้วคืนสถิติจริงจาก k6

        test_type: "load" (default) | "stress" | "stability"/"soak" | "spike"
        - นอกจาก "load" ทุกแบบใช้ k6 `options.stages` แทน CLI --vus/--duration/
          --iterations (k6 ต้องกำหนด stage ผ่าน script ไม่ใช่ CLI flag) ดู
          knowledge.get_testing_type สำหรับคำนิยามของแต่ละแบบ
        """
        test_type = test_type.lower()
        if test_type not in self.VALID_TEST_TYPES:
            raise ValueError(f"Unknown test_type {test_type!r} - expected one of {sorted(self.VALID_TEST_TYPES)}")
        test_type = "stability" if test_type == "soak" else test_type

        if test_type == "load" and not duration and not iterations:
            iterations = 1

        script = self._build_script(url, method, headers, body, test_type=test_type, vus=vus, duration=duration)

        with tempfile.TemporaryDirectory(prefix="qa-mcp-k6-") as tmpdir:
            script_path = Path(tmpdir) / "script.js"
            summary_path = Path(tmpdir) / "summary.json"
            script_path.write_text(script)

            args = [self._k6_bin, "run", "--summary-export", str(summary_path)]
            if test_type == "load":
                # unchanged from before test_type existed: plain flat run via CLI flags
                args += ["--vus", str(vus)]
                if duration:
                    args += ["--duration", duration]
                if iterations:
                    args += ["--iterations", str(iterations)]
            # stress/stability/spike control vus/duration entirely via the
            # script's `options.stages` (or `options.vus`+`options.duration`
            # for stability) - k6 doesn't support staged ramps as CLI flags
            args.append(str(script_path))

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=600 if test_type == "stability" else 120)

            # k6 exits non-zero when thresholds fail - ยังอ่าน summary ได้ตามปกติ
            summary: Dict[str, Any] = {}
            if summary_path.exists():
                summary = json.loads(summary_path.read_text())

            metrics = summary.get("metrics", {})
            http_req_duration = metrics.get("http_req_duration", {})
            http_req_failed = metrics.get("http_req_failed", {})
            http_reqs = metrics.get("http_reqs", {})

            return {
                "test_type": test_type,
                "vus": vus,
                "duration": duration,
                "iterations": iterations,
                "requests": http_reqs.get("count", 0),
                "requests_per_sec": http_reqs.get("rate", 0),
                "failed_rate": http_req_failed.get("rate") or http_req_failed.get("value", 0),
                "duration_ms": {
                    "avg": http_req_duration.get("avg"),
                    "min": http_req_duration.get("min"),
                    "max": http_req_duration.get("max"),
                    "p95": http_req_duration.get("p(95)"),
                },
                "exit_code": proc.returncode,
                "raw_output_tail": stdout.decode(errors="ignore")[-1500:],
            }

    @staticmethod
    def _stages_for(test_type: str, vus: int, duration: Optional[str]) -> Optional[List[Dict[str, Any]]]:
        """k6 `options.stages` สำหรับแต่ละ test_type - None แปลว่าใช้ CLI flag แทน
        (เฉพาะ "load") ตัวเลขในแต่ละ stage มาจากคำนิยามจริงของแต่ละ testing
        type (ดู qa_mcp.knowledge.concepts.TESTING_TYPES):
        - stress: ไต่ระดับเกิน vus ที่ขอมาเรื่อย ๆ (2x, 3x) เพื่อหาจุดที่ระบบพัง
        - spike: พุ่งขึ้นสูงมาก (5x) แบบทันทีในช่วงสั้น ๆ แล้วลดกลับ
        """
        if test_type == "stress":
            # ต้องรวมกันสั้นกว่า subprocess timeout ด้านล่าง (120s) มาก
            # พอที่จะเหลือ headroom ให้ k6 startup + summary export - ทดสอบจริง
            # แล้วว่า stage รวม 3 นาทีตามที่ตั้งไว้แต่แรกชน timeout เดิมพอดี
            return [
                {"duration": "10s", "target": vus},
                {"duration": "15s", "target": vus * 2},
                {"duration": "15s", "target": vus * 3},
                {"duration": "10s", "target": 0},
            ]
        if test_type == "spike":
            return [
                {"duration": "10s", "target": vus},
                {"duration": "10s", "target": vus * 5},
                {"duration": "10s", "target": vus},
                {"duration": "10s", "target": 0},
            ]
        return None

    @classmethod
    def _build_script(
        cls, url: str, method: str, headers: Optional[Dict], body: Optional[Any],
        test_type: str = "load", vus: int = 1, duration: Optional[str] = None,
    ) -> str:
        """สร้าง k6 script (JS) แบบ inline - สำหรับ "load" ไม่มี `options` block
        เลย (CLI flag คุมทั้งหมด เหมือนพฤติกรรมเดิมก่อนมี test_type) ส่วนแบบอื่น
        ฝัง `export const options` ที่กำหนด stage/duration ตรงตาม test_type
        """
        params = {"method": method.upper(), "headers": headers or {}}
        payload = json.dumps(body) if body is not None else "undefined"

        options_block = ""
        stages = cls._stages_for(test_type, vus, duration)
        if stages is not None:
            options_block = f"export const options = {{ stages: {json.dumps(stages)} }};\n"
        elif test_type == "stability":
            options_block = f"export const options = {{ vus: {vus}, duration: {json.dumps(duration or '10m')} }};\n"

        return (
            "import http from 'k6/http';\n"
            "import { check } from 'k6';\n"
            f"{options_block}"
            f"const URL = {json.dumps(url)};\n"
            f"const PARAMS = {json.dumps(params)};\n"
            f"const BODY = {payload};\n"
            "export default function () {\n"
            "  const res = BODY !== undefined\n"
            "    ? http.request(PARAMS.method, URL, JSON.stringify(BODY), PARAMS)\n"
            "    : http.request(PARAMS.method, URL, null, PARAMS);\n"
            "  check(res, { 'status is 2xx/3xx': (r) => r.status < 400 });\n"
            "}\n"
        )

    async def request(self, method: str, url: str,
                      headers: Optional[Dict] = None,
                      body: Optional[Any] = None,
                      params: Optional[Dict] = None) -> APIResponse:
        result = await self.run_load_test(url=url, method=method, vus=1, iterations=1,
                                          headers=headers, body=body)
        avg = (result.get("duration_ms") or {}).get("avg") or 0.0
        failed = result.get("failed_rate") or 0
        return APIResponse(
            status_code=0 if failed else 200,
            headers={},
            body=result,
            duration_ms=avg,
            request={"method": method, "url": url},
        )

    async def assert_status(self, response: APIResponse, expected: int) -> bool:
        return response.status_code == expected

    async def assert_schema(self, response: APIResponse, schema: Dict) -> bool:
        return isinstance(response.body, dict)

    async def assert_header(self, response: APIResponse, key: str, expected: str) -> bool:
        return response.headers.get(key.lower()) == expected


# MCP Tools
async def api_request(method: str, url: str, headers: Optional[Dict] = None,
                      body: Optional[Any] = None) -> Dict[str, Any]:
    """MCP tool: api.request"""
    adapter = RESTAdapter()
    resp = await adapter.request(method, url, headers=headers, body=body)
    await adapter.close()
    return {
        "status_code": resp.status_code,
        "body": resp.body,
        "duration_ms": resp.duration_ms,
    }


async def api_assert_status(response: Dict, expected: int) -> bool:
    """MCP tool: api.assert_status"""
    return response.get("status_code") == expected


async def api_load_test(
    url: str,
    method: str = "GET",
    vus: int = 1,
    duration: Optional[str] = None,
    iterations: Optional[int] = None,
    headers: Optional[Dict] = None,
    body: Optional[Any] = None,
    test_type: str = "load",
) -> Dict[str, Any]:
    """MCP tool: api.load_test - รัน k6 load test จริง (ต้องมี k6 ติดตั้งในเครื่อง)

    test_type: "load" (default - flat vus at expected volume) | "stress"
    (ramps well beyond vus to find the breaking point) | "stability"/"soak"
    (long flat run to catch leaks/degradation - overrides duration to 10m
    if not given) | "spike" (short sudden burst to 5x vus then back down).
    เรียก knowledge.get_testing_type("stress") เป็นต้น เพื่อดูคำนิยามเต็ม
    """
    adapter = K6Adapter()
    return await adapter.run_load_test(
        url=url, method=method, vus=vus, duration=duration,
        iterations=iterations, headers=headers, body=body, test_type=test_type,
    )
