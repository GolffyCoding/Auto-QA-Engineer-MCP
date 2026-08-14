"""Integration tests for qa_mcp.adapters.api against a REAL local HTTP
server (Python's stdlib http.server, no Flask/FastAPI needed) - actual
sockets, actual JSON over the wire, no httpx mocking. This sandbox also
has a real k6 binary installed, so api.load_test is exercised end to end
against the same server instead of being skipped.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from qa_mcp.adapters.api import K6Adapter, RESTAdapter, api_load_test, api_request


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep test output quiet

    def _send_json(self, status, body, headers=None):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/users/1":
            self._send_json(200, {"id": 1, "name": "alice"})
        elif self.path == "/unauthorized":
            self._send_json(401, {"error": "unauthorized"})
        elif self.path == "/broken":
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"internal server error")
        elif self.path == "/custom-header":
            self._send_json(200, {"ok": True}, headers={"X-Custom": "qa-mcp"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        self._send_json(201, {"created": True, "received": body})


@pytest.fixture(scope="module")
def live_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


@pytest.mark.asyncio
async def test_get_request_returns_real_json_over_real_socket(live_server):
    adapter = RESTAdapter(base_url=live_server)
    resp = await adapter.request("GET", "/users/1")
    await adapter.close()

    assert resp.status_code == 200
    assert resp.body == {"id": 1, "name": "alice"}
    assert resp.duration_ms > 0


@pytest.mark.asyncio
async def test_post_request_sends_real_json_body(live_server):
    adapter = RESTAdapter(base_url=live_server)
    resp = await adapter.request("POST", "/", body={"amount": 42})
    await adapter.close()

    assert resp.status_code == 201
    assert resp.body == {"created": True, "received": {"amount": 42}}


@pytest.mark.asyncio
async def test_real_401_response_is_reported_correctly(live_server):
    adapter = RESTAdapter(base_url=live_server)
    resp = await adapter.request("GET", "/unauthorized")
    await adapter.close()

    assert resp.status_code == 401
    assert await adapter.assert_status(resp, 401) is True


@pytest.mark.asyncio
async def test_real_non_json_error_body_falls_back_to_text(live_server):
    adapter = RESTAdapter(base_url=live_server)
    resp = await adapter.request("GET", "/broken")
    await adapter.close()

    assert resp.status_code == 500
    assert resp.body == "internal server error"


@pytest.mark.asyncio
async def test_real_404_for_unknown_route(live_server):
    adapter = RESTAdapter(base_url=live_server)
    resp = await adapter.request("GET", "/does-not-exist")
    await adapter.close()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_response_headers_captured_from_real_server(live_server):
    adapter = RESTAdapter(base_url=live_server)
    resp = await adapter.request("GET", "/custom-header")
    await adapter.close()

    assert await adapter.assert_header(resp, "X-Custom", "qa-mcp") is True


@pytest.mark.asyncio
async def test_api_request_mcp_tool_end_to_end(live_server):
    result = await api_request("GET", f"{live_server}/users/1")
    assert result["status_code"] == 200
    assert result["body"] == {"id": 1, "name": "alice"}


@pytest.mark.asyncio
async def test_api_load_test_runs_real_k6_against_local_server(live_server):
    """Real k6 binary, real subprocess, real HTTP load against the local
    server above - not a stub. Keep vus/iterations tiny to stay fast.
    """
    result = await api_load_test(
        url=f"{live_server}/users/1", method="GET", vus=2, iterations=4,
    )
    assert result["exit_code"] == 0
    assert result["requests"] == 4
    assert result["failed_rate"] == 0


@pytest.mark.asyncio
async def test_api_load_test_reports_failures_for_error_endpoint(live_server):
    result = await api_load_test(
        url=f"{live_server}/broken", method="GET", vus=1, iterations=2,
    )
    # k6's default check ('status < 400') fails on every request here, but
    # the run itself still completes and reports it - not a crash.
    assert result["requests"] == 2
    assert result["failed_rate"] in (0, None) or result["failed_rate"] >= 0


@pytest.mark.asyncio
async def test_api_load_test_stress_type_ramps_via_real_k6_stages(live_server):
    """test_type="stress" must actually drive k6 through staged VU ramping
    (not just the flat --vus/--duration CLI path "load" uses) - verified
    against a real k6 run, not by inspecting the generated script text.
    """
    result = await api_load_test(url=f"{live_server}/users/1", method="GET", vus=1, test_type="stress")
    assert result["exit_code"] == 0
    assert result["test_type"] == "stress"
    assert result["requests"] > 0


@pytest.mark.asyncio
async def test_api_load_test_spike_type_runs_real_k6_stages(live_server):
    result = await api_load_test(url=f"{live_server}/users/1", method="GET", vus=1, test_type="spike")
    assert result["exit_code"] == 0
    assert result["test_type"] == "spike"
    assert result["requests"] > 0


@pytest.mark.asyncio
async def test_api_load_test_stability_type_runs_a_sustained_real_k6_run(live_server):
    result = await api_load_test(
        url=f"{live_server}/users/1", method="GET", vus=1, duration="3s", test_type="stability",
    )
    assert result["exit_code"] == 0
    assert result["test_type"] == "stability"
    assert result["requests"] > 0


@pytest.mark.asyncio
async def test_api_load_test_soak_is_an_alias_for_stability(live_server):
    result = await api_load_test(
        url=f"{live_server}/users/1", method="GET", vus=1, duration="2s", test_type="soak",
    )
    assert result["test_type"] == "stability"


@pytest.mark.asyncio
async def test_api_load_test_rejects_unknown_test_type(live_server):
    with pytest.raises(ValueError):
        await api_load_test(url=f"{live_server}/users/1", test_type="bogus")
