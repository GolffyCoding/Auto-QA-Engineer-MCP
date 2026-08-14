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
    ) -> Dict[str, Any]:
        """รัน k6 load test จริงกับ url ที่กำหนด แล้วคืนสถิติจริงจาก k6"""
        if not duration and not iterations:
            iterations = 1

        script = self._build_script(url, method, headers, body)

        with tempfile.TemporaryDirectory(prefix="qa-mcp-k6-") as tmpdir:
            script_path = Path(tmpdir) / "script.js"
            summary_path = Path(tmpdir) / "summary.json"
            script_path.write_text(script)

            args = [self._k6_bin, "run", "--vus", str(vus),
                    "--summary-export", str(summary_path)]
            if duration:
                args += ["--duration", duration]
            if iterations:
                args += ["--iterations", str(iterations)]
            args.append(str(script_path))

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)

            # k6 exits non-zero when thresholds fail - ยังอ่าน summary ได้ตามปกติ
            summary: Dict[str, Any] = {}
            if summary_path.exists():
                summary = json.loads(summary_path.read_text())

            metrics = summary.get("metrics", {})
            http_req_duration = metrics.get("http_req_duration", {})
            http_req_failed = metrics.get("http_req_failed", {})
            http_reqs = metrics.get("http_reqs", {})

            return {
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
    def _build_script(url: str, method: str, headers: Optional[Dict], body: Optional[Any]) -> str:
        """สร้าง k6 script (JS) แบบ inline สำหรับยิง request เดียวซ้ำตาม vus/iterations ที่กำหนด"""
        params = {"method": method.upper(), "headers": headers or {}}
        payload = json.dumps(body) if body is not None else "undefined"
        return (
            "import http from 'k6/http';\n"
            "import { check } from 'k6';\n"
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
) -> Dict[str, Any]:
    """MCP tool: api.load_test - รัน k6 load test จริง (ต้องมี k6 ติดตั้งในเครื่อง)"""
    adapter = K6Adapter()
    return await adapter.run_load_test(
        url=url, method=method, vus=vus, duration=duration,
        iterations=iterations, headers=headers, body=body,
    )
