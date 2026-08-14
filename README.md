# Autonomous QA Engineer MCP

**Give an LLM agent a real QA engineer's workflow** — scan a project, design test cases by the book, run them across browser/API/mobile, diagnose failures, propose a fix, get human sign-off, apply it, and verify — all as [MCP](https://modelcontextprotocol.io/) tools any MCP-compatible agent (Claude Desktop, Claude Code, or your own agent loop) can call.

The core idea: **the LLM should never be the one deciding what counts as a complete test suite.** It reports facts about a feature (its fields, its business rules, its roles, its states); this project deterministically expands those facts into a suite that follows Boundary Value Analysis, Equivalence Partitioning, OWASP Top 10, and exhaustive state-machine coverage — every time, the same way, with a `rationale` attached to every case. LLMs forget edge cases under load; a rules engine doesn't.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-124%20passing-brightgreen)
![Validated](https://img.shields.io/badge/validated-real%20browser%20%7C%20real%20network%20%7C%20real%20device-informational)

---

## Why this, not just "ask the LLM to write tests"

| | Ask an LLM to write tests | This project |
|---|---|---|
| Edge case coverage | Whatever it remembers to think of, varies run to run | Deterministic: BVA, Equivalence Partitioning, OWASP Top 10, exhaustive state × action matrix |
| Security cases | Only if prompted, inconsistent payloads | 8 OWASP-mapped injection payloads on every free-text field, automatically |
| State machine testing | Usually just the happy path | Every declared transition **and** every invalid transition from every state, plus automatic unreachable-state detection |
| Executing the tests | Another manual step | Same agent session drives Playwright/Selenium/Robot/Cypress, API, and mobile directly |
| Fixing what it finds | Freeform patch, no guardrail | Diagnose → propose → **human approval required** → apply → verify, with the auto-apply path hard-blocked unless a human sets an env var outside the agent's reach |
| State across a session | Lost between calls | Persists to disk, survives a restart, safe for concurrent writers |

---

## Quick start

```bash
pip install -e .

# See every tool the agent can call
qa-mcp --list-tools

# Try one tool directly (useful for debugging a single tool in isolation)
qa-mcp --call project.scan --args '{"project_path": "."}'
```

**For real use, run it as a long-lived MCP server** (state persists across tool calls within a session — the one-shot `qa-mcp --call` CLI above is for debugging a single tool, not for driving a real workflow):

```bash
qa-mcp-serve
```

Point an MCP client at it — e.g. add to `claude_desktop_config.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "qa-mcp": { "command": "qa-mcp-serve" }
  }
}
```

Or drive it from your own agent loop:

```python
import asyncio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    params = StdioServerParameters(command="qa-mcp-serve")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("browser.open", {"url": "https://example.com"})
            await session.call_tool("browser.click", {"selector": "a"})
            await session.call_tool("browser.screenshot", {"name": "proof"})
            await session.call_tool("browser.close")

asyncio.run(main())
```

**Want to see it work against something real before wiring it into your own project?**

```bash
python3 sample-apps/checkout-demo/run_demo.py    # fields + business_rules
python3 sample-apps/task-manager/run_demo.py     # fields + roles + states (login, RBAC, a state machine)
```

Each one scans a small sample app with intentional bugs, generates a full deterministic test suite, runs a handful of real tests against it (real headless-Chromium browser test, real HTTP API calls, real SQLite check), and produces HTML **and PDF** reports with an executive risk summary. Takes under a minute each, no extra setup. See [`sample-apps/`](sample-apps/) for exactly what each one demonstrates.

---

## The pipeline

| Phase | What it does |
|---|---|
| **Understand** | `project.scan` detects language, framework, database, auth, existing tests, CI/CD |
| **Design** | `test.generate` builds a full suite from field/business-rule/role/UX-state/state-machine facts the agent reports |
| **Execute** | Drives Playwright, Selenium, Robot Framework, or Cypress for browser; REST + k6 for API; Appium or Maestro for mobile |
| **Observe** | Screenshots, console logs, network logs, stdout/stderr captured per test |
| **Diagnose** | `failure.inspect` classifies failures into 15 categories via weighted pattern matching, with a category-specific root cause and fix suggestion |
| **Fix** | `fix_loop` proposes a patch — **blocked from auto-applying without human approval** |
| **Verify** | Re-runs the target test and compares against the baseline run to confirm the fix and catch new regressions |
| **Report** | Self-contained HTML/JSON report with an executive risk summary and a real root cause + suggested fix on every failed test — not a bare pass/fail table; defect tracking; CI/CD trigger (GitHub Actions, GitLab CI) |

---

## Test case generation: what the LLM does vs. what the engine does

`test.generate` never lets the LLM invent edge/security/business-logic/state cases — it reports facts, the engine expands them:

| The agent reports | The engine generates | Method |
|---|---|---|
| `fields` | Positive case, per-field required-negative, boundary (at-limit and one-past-limit), type-mismatch negative, security injection probes | Boundary Value Analysis, Equivalence Partitioning, OWASP Top 10 |
| `business_rules` | A case proving the invariant holds, and a case that actively tries to break it | Business Logic invariant testing |
| `roles` | Access-granted / access-denied cases per role | OWASP A01:2021 Broken Access Control |
| `ux_states` | Loading / empty / error / offline / disabled / success / concurrent-submit cases with standard expected behavior | Nielsen UX heuristics |
| `states` | **Every (state × action) combination** — every declared transition, every invalid transition from every other state, and automatic unreachable-state detection | Exhaustive state-machine coverage (graph reachability) |

```python
await session.call_tool("test.generate", {
    "feature": "checkout",
    "fields": [
        {"name": "coupon_code", "type": "text", "required": False, "max_length": 20},
        {"name": "amount", "type": "number", "required": True},
    ],
    "business_rules": [
        {"name": "no-negative-total", "rule": "order total must never go below 0",
         "violation": "Apply a coupon larger than the order subtotal"},
    ],
    "roles": [
        {"role": "customer", "should_access": True},
        {"role": "guest", "should_access": False},
    ],
    "ux_states": ["loading", "empty", "error", "concurrent"],
})
```

→ 25 test cases across 7 categories, each with a `rationale`, e.g.:

> *Business Logic:* "an invariant that is only checked on the happy path isn't actually enforced — it must be proven to hold under an explicit attempt to break it"
> *Access Control:* "OWASP A01:2021: an endpoint that merely checks authentication (not authorization) silently permits privilege escalation"

If the agent calls `test.generate` with no dimensions and the feature isn't `"login"` or an API path, it **fails fast with an example payload** rather than silently guessing — a generated suite you didn't ask for is worse than an error telling you what to send.

**State machine example** — 5 declared transitions across 5 states × 4 actions (20-cell matrix) generates 20 cases: 5 positive (every declared transition) and 15 negative (every undeclared combination, proven blocked) — the full matrix, not a sample. An intentionally unreachable state gets flagged as a Regression case automatically.

---

## Framework support

Not just browser — four categories of tools, each with its own `*.*` prefix. Within a category, the underlying engine is just a `framework` parameter; swap it without changing how you call the tool.

| Category | Tools | Engine | `framework=` | Requires |
|---|---|---|---|---|
| **Browser** | `browser.open` / `.click` / `.fill` / `.screenshot` / `.assert` / `.close` | Playwright | `"playwright"` (default) | `playwright install` |
| | | Selenium | `"selenium"` | Chrome + ChromeDriver |
| | | Robot Framework | `"robot"` | Chrome (via `SeleniumLibrary` directly — no `.robot` files needed) |
| | | Cypress | `"cypress"` | Node.js + `npx` |
| **API** | `api.request` (REST) | httpx | — | nothing extra |
| | `api.load_test` (load testing) | [k6](https://k6.io/) | — | `k6` binary (or set `QA_MCP_K6_BIN`) |
| **Mobile** | `mobile.launch` / `.tap` / `.swipe` / `.type_text` / `.assert_element` / `.close` | Appium | `"appium"` (default) | running Appium server + a device/emulator reachable via `adb` |
| | | Maestro | `"maestro"` | Maestro CLI + a device/emulator |
| **Database** | `db.get_table_state` / `.check_fk_integrity` / `.query` | SQLAlchemy | — | any DB SQLAlchemy supports (Postgres, MySQL, SQLite, …) |

Notes:

- **Cypress** has no interactive session across commands, so each new action replays every prior action in the session as one spec and reruns it — correct results, but it gets slower as a session grows. For long workflows, prefer Playwright/Selenium/Robot.
- **Appium and Maestro** were both validated against a real physical Android device; see [CHANGELOG.md](CHANGELOG.md) for what that surfaced and how it was fixed.
- **Database** tools allowlist table/column identifiers against SQL injection and are used to verify row state and foreign-key integrity after an E2E test — not a general query tool.

---

## Reporting: built to hand to a stakeholder, not just a CI dashboard

```python
run = await session.call_tool("test.create_run", {"suite_name": "checkout-suite"})
await session.call_tool("test.run", {"test_id": "t1", "command": ["pytest", "test_login.py"]})
await session.call_tool("test.run", {"test_id": "t2", "command": ["pytest", "test_checkout.py"]})
report = await session.call_tool("report.generate_html", {"run_id": run_id})
# -> {"report_id": "...", "path": "./reports/report-....html", "summary": {...}, "executive_summary": {...}}
```

Every failed test in the report is automatically run through the same classification engine `failure_analysis` uses — you don't have to call `failure.inspect` yourself first. Each one gets a real category (one of 15, from `database` to `security` to `logic`), a specific root cause, and a suggested fix, instead of a bare error string.

The report also carries a **deterministic executive summary** — no LLM-authored prose, just fixed templates over real classification data — meant for someone who doesn't have time to read every test result:

- A one-line headline: *"2 of 10 tests failing (80% pass rate), 1 Critical — risk level: Critical."*
- A `risk_level` (`None` / `Medium` / `High` / `Critical`) driven by the worst failure category present — a `database`/`auth`/`security` failure is Critical, `api`/`logic`/`concurrency` is High, everything else is Medium
- Failures broken down by severity and by category
- The top 5 risks worth looking at first, sorted by severity

`report.generate_html` writes a self-contained HTML file to `./reports/` — open it straight in a browser. **`report.generate_pdf`** renders that same report to a real PDF (via headless Chromium print-to-PDF, not a screenshot — proper page breaks, A4, print-safe colors) so you have something you can actually email, attach to a ticket, or file as a dated record without converting anything yourself.

---

## Built for a team, not a demo

**State survives a restart.** Test runs, defects, failure evidence, and patch proposals persist to a JSON store (`qa_mcp/core/persistence.py`, atomic writes). Kill the `qa-mcp-serve` process, start a new one, and `test.get_run` / `failure.get_evidence` / `report.generate` still return everything.

**Safe for concurrent writers.** If your whole team points `QA_MCP_STATE_DB` at the same file to share defects/runs, writes are protected by a cross-process file lock, merged at the entry level (not a namespace-level replace), and IDs include a random suffix to avoid same-second collisions. Verified with 8 processes writing concurrently to the same file: 8/8 survive.

**CI/CD is a real trigger, not a stub.** `ci.run`/`ci.get_status` call the real GitHub Actions (`workflow_dispatch`) and GitLab CI (`trigger/pipeline`) REST APIs — set `GITHUB_TOKEN` or `GITLAB_TRIGGER_TOKEN`/`GITLAB_API_TOKEN`. No token, no repo, or a bad token all produce a real, actionable error instead of a fake success.

**A patch can't apply itself.** `fix_loop` requires an explicit `fix_loop.approve` before `fix_loop.apply_patch` will touch the filesystem, and even then `read_only=False` is refused unless a human has set `QA_MCP_ALLOW_AUTO_APPLY=1` in the environment *ahead of time* — something the agent cannot do from inside its own tool calls. **Don't leave that variable set permanently**; set it only for the moment a human is actually approving, or gate it behind a real approval workflow (e.g. a CI job that only sets it after a reviewer approves a PR).

---

## Running the test suite

```bash
pip install -e .
python -m pytest tests/ -v
```

108 tests, and wherever the environment allowed it, they exercise **real infrastructure instead of mocks**:

| Test file | Runs against |
|---|---|
| `test_fix_loop_engine.py` | Approval-gate logic, auto-apply block |
| `test_persistence.py` | Real disk I/O, process-restart simulation |
| `test_test_design_generator.py` | BVA/security/state-matrix generation logic |
| `test_failure_analyzer.py` | Pattern-matching classification, evidence persistence |
| `test_executor.py` | Real subprocesses (pass/fail/timeout), real artifact files |
| `test_defect_manager.py` | Real git repo (`git init`/status/log/commit), fail-fast CI checks |
| `test_database_analyzer.py` | Real SQLite database, real orphaned-FK detection |
| `test_reporter.py` | Root-cause diagnosis attached to failed tests, executive-summary risk rollup |
| `test_report_pdf.py` | **Real PDF generation via headless Chromium** — verifies actual `%PDF-` file output |
| `test_api_adapter.py` | Fake HTTP transport (schema/assertion logic) |
| `test_api_integration.py` | **Real HTTP server + real `k6` binary** — actual sockets, actual load test |
| `test_browser_adapter.py` | **Real headless Chromium via Playwright** — actual DOM, actual screenshots |
| `test_mobile_adapter.py` | Device-independent option-building + retry logic (Appium/Maestro were also validated against a real physical Android device — see [CHANGELOG.md](CHANGELOG.md)) |

Every bug this hardening pass found — a silent data-loss bug in the persistence layer, an approval-gate bypass, a blank project name, a misdetected language, a crash on the most natural test-generation workflow, and two real-device mobile issues — is documented with root cause and fix in **[CHANGELOG.md](CHANGELOG.md)**.

---

## Project layout

| Phase | Module | Purpose |
|:-:|---|---|
| 1 | `project_intelligence` | Scan and detect project stack |
| 2 | `test_design` | Deterministic test-case generation and coverage analysis |
| 3 | `adapters` | Browser / API / mobile automation engines |
| 4 | `execution` | Test run lifecycle and evidence capture |
| 5 | `failure_analysis` | Failure classification and root-cause analysis |
| 6 | `fix_loop` | Diagnose → propose → **approve** → apply → verify |
| 7 | `defect_cicd` | Defect tracking, git operations, CI/CD triggers |
| 8 | `core.reporter` | JSON/HTML reporting |
| 9 | `analyzers.database_analyzer` | Post-test database state verification |

Run `qa-mcp --list-tools` for the full list of registered tools with their implementing function paths.

---

## Dependencies

Python **3.10+**. Core libraries: `mcp`, `pydantic`, `httpx`, `playwright`, `selenium`, `robotframework`, `robotframework-seleniumlibrary`, `Appium-Python-Client`, `pytest`, `sqlalchemy` — full list in [`requirements.txt`](requirements.txt).

Non-Python, install only what you'll use:

| Tool | Needed for |
|---|---|
| Node.js + `npx` | Cypress |
| [k6](https://k6.io/docs/get-started/installation/) | `api.load_test` |
| Appium server + Android/iOS SDK | `mobile.*` with `framework="appium"` |
| [Maestro CLI](https://maestro.mobile.dev/getting-started/installing-maestro) | `mobile.*` with `framework="maestro"` |

### Environment variables

| Variable | Purpose |
|---|---|
| `QA_MCP_STATE_DB` | Persistence file path (default `./qa-mcp-state.json`) — point your whole team at the same path to share state |
| `QA_MCP_ALLOW_AUTO_APPLY` | Must be `1` for `fix_loop.apply_patch` to write to disk — see [Built for a team, not a demo](#built-for-a-team-not-a-demo) |
| `QA_MCP_K6_BIN` | Path to the `k6` binary if it's not on `PATH` |
| `GITHUB_TOKEN` | For `ci.run`/`ci.get_status` with GitHub Actions (needs `actions:write`) |
| `GITLAB_TRIGGER_TOKEN` / `GITLAB_API_TOKEN` | For `ci.run` (trigger) / `ci.get_status` (API) with GitLab CI |

> The persistence layer's cross-process file lock uses `fcntl` (POSIX only). On Windows, locking is silently skipped — writes still work, but aren't safe under concurrent writers from multiple processes.

---

## License

MIT
