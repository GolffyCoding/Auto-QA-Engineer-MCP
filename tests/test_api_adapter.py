"""Unit tests for qa_mcp.adapters.api - RESTAdapter is tested against a
fake in-process HTTP transport (httpx.MockTransport) so no real network
call happens. K6Adapter is tested at the level of its pure logic (script
generation, binary discovery) since actually running k6 needs the binary
installed.
"""
from pathlib import Path

import httpx
import pytest

from qa_mcp.adapters.api import K6Adapter, RESTAdapter, _find_k6_binary


_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    """Build an AsyncClient wired to a MockTransport instead of the network,
    matching the base_url/headers/timeout signature RESTAdapter._get_client uses.
    Must call the *original* AsyncClient class, not httpx.AsyncClient, since
    that name gets monkeypatched to this factory itself for the duration of
    the test (patching it recursively would call this factory again).
    """
    def factory(*, base_url="", headers=None, timeout=30.0):
        return _RealAsyncClient(
            base_url=base_url, headers=headers, timeout=timeout,
            transport=httpx.MockTransport(handler),
        )
    return factory


@pytest.mark.asyncio
async def test_request_returns_real_status_and_json_body(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("qa_mcp.adapters.api.httpx.AsyncClient", _mock_client(handler))

    adapter = RESTAdapter(base_url="https://api.example.com")
    resp = await adapter.request("GET", "/health")
    await adapter.close()

    assert resp.status_code == 200
    assert resp.body == {"ok": True}


@pytest.mark.asyncio
async def test_request_falls_back_to_text_body_on_non_json_response(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="internal server error")

    monkeypatch.setattr("qa_mcp.adapters.api.httpx.AsyncClient", _mock_client(handler))

    adapter = RESTAdapter(base_url="https://api.example.com")
    resp = await adapter.request("GET", "/broken")
    await adapter.close()

    assert resp.status_code == 500
    assert resp.body == "internal server error"


@pytest.mark.asyncio
async def test_assert_status_matches_expected_code():
    adapter = RESTAdapter()
    from qa_mcp.adapters.api import APIResponse
    resp = APIResponse(status_code=404, headers={}, body=None, duration_ms=1.0, request={})
    assert await adapter.assert_status(resp, 404) is True
    assert await adapter.assert_status(resp, 200) is False


@pytest.mark.asyncio
async def test_assert_schema_detects_missing_required_field():
    adapter = RESTAdapter()
    from qa_mcp.adapters.api import APIResponse

    schema = {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
    }
    missing_id = APIResponse(status_code=200, headers={}, body={"name": "alice"}, duration_ms=1.0, request={})
    has_id = APIResponse(status_code=200, headers={}, body={"id": 1, "name": "alice"}, duration_ms=1.0, request={})

    assert await adapter.assert_schema(missing_id, schema) is False
    assert await adapter.assert_schema(has_id, schema) is True


@pytest.mark.asyncio
async def test_assert_schema_detects_wrong_type():
    adapter = RESTAdapter()
    from qa_mcp.adapters.api import APIResponse

    schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
    wrong_type = APIResponse(status_code=200, headers={}, body={"id": "not-an-int"}, duration_ms=1.0, request={})

    assert await adapter.assert_schema(wrong_type, schema) is False


def test_k6_build_script_embeds_url_method_and_body():
    script = K6Adapter._build_script(
        "https://api.example.com/orders", "POST", {"X-Test": "1"}, {"amount": 10},
    )
    assert '"https://api.example.com/orders"' in script
    assert '"POST"' in script
    assert '"amount": 10' in script


def test_k6_build_script_handles_no_body():
    script = K6Adapter._build_script("https://api.example.com/health", "GET", None, None)
    assert "const BODY = undefined;" in script


def test_find_k6_binary_raises_when_not_installed(monkeypatch):
    monkeypatch.delenv("QA_MCP_K6_BIN", raising=False)
    monkeypatch.setattr("qa_mcp.adapters.api.shutil.which", lambda name: None)
    monkeypatch.setattr(Path, "is_file", lambda self: False)

    with pytest.raises(FileNotFoundError):
        _find_k6_binary()


def test_find_k6_binary_uses_env_var_when_set(monkeypatch, tmp_path):
    fake_k6 = tmp_path / "k6"
    fake_k6.write_text("#!/bin/sh\n")
    fake_k6.chmod(0o755)
    monkeypatch.setenv("QA_MCP_K6_BIN", str(fake_k6))

    assert _find_k6_binary() == str(fake_k6)
