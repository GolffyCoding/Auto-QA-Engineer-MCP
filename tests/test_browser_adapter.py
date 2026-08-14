"""Unit tests for qa_mcp.adapters.browser - runs against a real headless
Chromium via Playwright (already a hard dependency of this project) and a
local static HTML fixture (tests/fixtures/form.html), so no network access
or mocking is needed. Covers both the PlaywrightAdapter directly and the
MCP tool functions / BrowserFactory singleton behavior that browser.open ->
browser.click -> browser.fill rely on to share one live page across calls.
"""
from pathlib import Path

import pytest

from qa_mcp.adapters.browser import BrowserFactory, PlaywrightAdapter

FIXTURE_URL = f"file://{(Path(__file__).parent / 'fixtures' / 'form.html').resolve()}"


@pytest.fixture
async def page(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    adapter = PlaywrightAdapter(headless=True)
    yield adapter
    await adapter.close()


@pytest.mark.asyncio
async def test_open_returns_real_title_and_url(page):
    result = await page.open(FIXTURE_URL)
    assert result["title"] == "QA-MCP Test Fixture"
    assert result["url"] == FIXTURE_URL


@pytest.mark.asyncio
async def test_fill_and_click_updates_real_dom(page):
    await page.open(FIXTURE_URL)
    await page.fill("#name", "Alice")
    await page.click("#submit")
    text = await page.get_text("#result")
    assert text == "Hello, Alice"


@pytest.mark.asyncio
async def test_assert_text_matches_real_dom_content(page):
    await page.open(FIXTURE_URL)
    await page.fill("#name", "Bob")
    await page.click("#submit")
    assert await page.assert_text("#result", "Bob") is True
    assert await page.assert_text("#result", "Charlie") is False


@pytest.mark.asyncio
async def test_assert_visible_true_for_visible_element(page):
    await page.open(FIXTURE_URL)
    assert await page.assert_visible("#heading") is True


@pytest.mark.asyncio
async def test_assert_visible_false_for_element_that_never_appears(page):
    await page.open(FIXTURE_URL)
    assert await page.assert_visible("#does-not-exist") is False


@pytest.mark.asyncio
async def test_hidden_element_becomes_visible_after_real_interaction(page):
    await page.open(FIXTURE_URL)
    assert await page.assert_visible("#hidden") is False
    await page.fill("#name", "Dana")
    await page.click("#submit")
    assert await page.assert_visible("#hidden") is True


@pytest.mark.asyncio
async def test_select_dropdown_option(page):
    await page.open(FIXTURE_URL)
    result = await page.select("#plan", "pro")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_screenshot_writes_real_png_to_disk(page, tmp_path):
    await page.open(FIXTURE_URL)
    evidence = await page.screenshot("checkout")
    path = Path(evidence.path)
    assert path.exists()
    assert path.stat().st_size > 0
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_console_logs_captured_from_real_page(page):
    await page.open(FIXTURE_URL)
    logs = await page.get_console_logs()
    assert any("page loaded" in entry["text"] for entry in logs)


@pytest.mark.asyncio
async def test_wait_times_out_gracefully_for_selector_that_never_appears(page):
    await page.open(FIXTURE_URL)
    found = await page.wait("#never-appears", timeout=500)
    assert found is False


@pytest.mark.asyncio
async def test_browser_factory_reuses_same_session_across_calls(tmp_path, monkeypatch):
    """browser.open -> browser.click -> browser.fill must operate on the
    same live page, not a fresh browser each time - otherwise no element
    from a previous action would ever exist for the next one.
    """
    monkeypatch.chdir(tmp_path)
    from qa_mcp.adapters import browser as browser_module

    try:
        result = await browser_module.browser_open(FIXTURE_URL, framework="playwright")
        assert result["title"] == "QA-MCP Test Fixture"

        await browser_module.browser_fill("#name", "Erin", framework="playwright")
        await browser_module.browser_click("#submit", framework="playwright")

        assertion = await browser_module.browser_assert("#result", framework="playwright")
        assert assertion["visible"] is True
    finally:
        await BrowserFactory.close("playwright")


@pytest.mark.asyncio
async def test_browser_close_tool_reports_false_when_nothing_open():
    from qa_mcp.adapters import browser as browser_module
    result = await browser_module.browser_close(framework="playwright")
    assert result["closed"] is False
