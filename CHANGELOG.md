# Changelog

Detailed record of real bugs found and fixed while building out test coverage and validating this project end-to-end (unit tests, full workflow runs, and real hardware/network validation). Kept separate from `README.md` so the README stays focused on how to use the project rather than how it was hardened.

## QA reference concepts + real Stress/Stability/Spike load testing

Asked to bring StrongQA's QA knowledge base (Key Concepts + Testing Types) into the project. Fetched the actual page content (not summarized from memory) for six Key Concepts (Software Testing, Testing/QA/QC, Testing vs Debugging, Verification vs Validation, Testing Documentation, Myths about QA) and five Testing Types (Functional, Performance, Load, Stress, Stability), and added two things:

1. **`qa_mcp/knowledge/concepts.py`** - grounded static reference data (not a document dump) exposed as `knowledge.get_concept`/`.list_concepts`/`.get_testing_type`/`.list_testing_types`, so an agent can look up an accurate definition instead of guessing/hallucinating QA theory. Registered in both the CLI dispatch table and the real server's `TOOLS` dict (the sync-check test added earlier caught nothing missing this time - it did its job).

2. **`api.load_test` gained a real `test_type` parameter** (`"load"` / `"stress"` / `"stability"`/`"soak"` / `"spike"`), each a genuine k6 execution pattern via `options.stages` (staged VU ramps), not just a label - `"load"` (default) is byte-identical to the old behavior for backward compatibility, `"stress"` ramps to 3x the requested VUs, `"spike"` bursts to 5x briefly, `"stability"` holds a flat load for a long duration (default 10 minutes if none given).

**Found and fixed a real bug while testing the new `"stress"` mode against a live k6 run**: the first draft's stress stages summed to 3 minutes, but the subprocess wait timeout was still 120 seconds inherited from the old flat-load code path - every stress test would guaranteed a `TimeoutError`. Caught by actually running it end to end against a real local server rather than just asserting on the generated script text; shortened the default stress/spike stage durations so a default run comfortably fits inside the existing timeout.

7 new tests (`test_knowledge_concepts.py`, 5 new in `test_api_integration.py` exercising all four `test_type` values against real k6). 157 tests total - the full suite now takes ~2 minutes instead of ~30 seconds, since the new stress/spike/stability tests each run a real, if short, k6 load pattern rather than a single request.

## Reports weren't a real Test Summary Report

Feedback (with a reference example, a StrongQA test report template) that the generated report still wasn't something a QA team could actually use as-is: no document control section, no scope statement, no test environment record, no formal defect ID scheme, no release recommendation, no sign-off block - a nicer-looking CI dashboard, not the document shape a real QA team files or sends.

Restructured `ReportGenerator.generate()`/`generate_html()` into an actual Test Summary Report: document control (project/system under test, version, prepared by, status, test environment), an introduction/scope statement, a full test summary (now including a `skipped` count that was silently missing before), a formal defect table with `DEF-NNN` IDs, every executed test listed (not just failures), a deterministic go/no-go **recommendation** derived from the worst severity present, and a **sign-off** block with a blank Name/Date row per reviewer specified. All of it is optional metadata (`project_name`, `version`, `prepared_by`, `test_environment`, `reviewers`) with sensible defaults, so existing callers that don't pass any of it still work.

Caught a real rendering bug while visually reviewing the redesigned PDF output (converted to PNG and inspected page by page): the new document-control table's header cells inherited `color: white` from the generic `th` rule while sitting on a light-grey (`#eee`) background - unreadable in the rendered PDF/HTML. Fixed by setting an explicit `color` on `.doc-control th`. Undetectable from HTML string assertions alone; only visual inspection of the actual rendered output caught it.

3 new/updated tests in `tests/test_reporter.py`. 144 tests total.

## Company customization: a whole subsystem existed but was dead code

Prompted by feedback that there was no `.env.example`, no way to customize the LLM's instructions/role, and no way to teach the tool company-specific conventions. Turned up that `qa_mcp/knowledge/base.py` already had a `KnowledgeBase` class built for exactly this - project rules, failure patterns, team decisions - but it was **never registered as an MCP tool anywhere** (not in `mcp_server.py`'s CLI table, not in `server.py`'s real tool table) and nothing else in the codebase referenced it except a stray comment. A company could not have used it no matter how they tried; there was no way in.

Fixed:

- `KnowledgeBase` now uses the shared `PersistentStore` (atomic writes, safe for concurrent writers) instead of its original unlocked, non-atomic `json.dump`/`json.load` - it had the exact same data-loss exposure as the bug already fixed elsewhere in `PersistentStore` itself, just never noticed because nothing called it.
- Registered 6 new tools (`knowledge.add_rule`, `.get_rules`, `.add_failure_pattern`, `.get_similar_failures`, `.add_decision`, `.get_decisions`) in both the CLI table and the real server's `TOOLS` dict.
- `create_server()` in `qa_mcp/server.py` now builds its `instructions` (what the LLM is told at connection time) dynamically: base instructions, then any saved `knowledge.add_rule` entries, then the contents of `QA_MCP_INSTRUCTIONS_FILE` if set. A rule added once is visible in every future session without the agent re-fetching it.
- Added `.env.example` at the repo root documenting every environment variable this project reads, including the new `QA_MCP_INSTRUCTIONS_FILE`.

15 new tests (`tests/test_knowledge_base.py`, plus 3 in `tests/test_mcp_server.py` covering the instructions-building logic). 141 tests total.

## The real MCP server (`qa_mcp.server`) had zero test coverage and tools missing from it

Prompted by a question about how to actually connect an LLM to this project: `qa_mcp.server` is the module a real MCP client (Claude Desktop, Claude Code, or anything else) connects to - `qa_mcp.mcp_server` (the `qa-mcp --call` CLI) is a separate, debug-only dispatch table that dynamically imports tools by string path and was the only one with any test coverage. Before this pass, `qa_mcp.server` had never been imported in this environment - the `mcp` package (an existing `requirements.txt`/`setup.py` dependency) had never actually been installed here, and no test touched the module at all.

Once installed and actually exercised end to end (a real subprocess speaking real MCP over stdio - `initialize` → `list_tools` → `call_tool`), the API used (`MCPServer`, `add_tool`, `run(transport="stdio")`) checked out against the real SDK. But three tools present in the CLI's tool table were missing from the real server's `TOOLS` dict, meaning they showed up in `qa-mcp --list-tools` and worked via `qa-mcp --call`, but an LLM connected through `qa-mcp-serve` couldn't see or call them at all:

- `report.generate_pdf` (the newly-added PDF export tool - simply forgotten when it was wired into the CLI table but not this one)
- `test.generate_api` and `test.generate_e2e` (aliases of `test.generate`)

Fixed by importing and registering all three. Added `tests/test_mcp_server.py`, including a test that diffs the CLI tool table against the real server's tool table so this class of bug can't reoccur silently, and a real end-to-end stdio session test.

## Project scanner: "app.py" as a Flask indicator

**Found live, from the exact bug-class fix above:** running the newly-added stdio integration test against this repo made `project.scan` report `framework: "Flask"` - wrong, this project doesn't use Flask. Root cause: `"app.py"` was listed as a Flask indicator in `FRAMEWORK_INDICATORS`, and this repo's own `sample-apps/checkout-demo/app.py` / `sample-apps/task-manager/app.py` (plain `http.server`, nothing to do with Flask) matched it. `app.py`/`app.js` are far too generic a filename to mean anything on their own - removed both as indicators; the config-file-based check (actual `Flask`/`flask`/`express` text in `requirements.txt`/`package.json`) still works correctly and is the reliable signal.

## PDF reports + sample apps

Added `report.generate_pdf`, which renders the same HTML report through headless Chromium's print-to-PDF (Playwright, already a dependency — no new library needed) instead of a screenshot, so it gets real page breaks and print-safe styling via `@page`/`@media print` CSS. Added a document metadata line (report ID, run ID, generated-at timestamp) to both the HTML and PDF output, which was previously missing — a report with no identifying metadata isn't something you can file or reference later.

Added a second sample app, `sample-apps/task-manager/`, alongside the existing `checkout-demo/`. `checkout-demo` only exercises `test.generate`'s `fields` and `business_rules` dimensions; `task-manager` adds a login-gated internal tool with two roles and a real task state machine, exercising `roles` and `states` as well, with its own two intentional bugs (a state machine that accepts an invalid transition, and a delete endpoint with no ownership/role check).

**Found while wiring up the sample apps: `test.run`/`TestExecutor.run_test` had no way to pass environment variables to the test subprocess at all.** Both demo scripts built an `env` dict for the target app's URL but had nowhere to actually pass it — the subprocess call only ever inherited the parent process's environment verbatim. This is a real gap for any company usage where the same test needs to run against different environments (staging vs. prod) or needs a credential injected at run time. Added an `env: Optional[Dict[str, str]]` parameter to `TestExecutor.run_test`/`retry` and the `test.run`/`test.rerun` MCP tools, merged into (not replacing) the parent environment. 2 new tests in `tests/test_executor.py`.

## Reporting

**Reports were a bare pass/fail table — not something you'd hand to a stakeholder.** `report.generate`/`report.generate_html` only ever produced a summary count and a raw error string per failed test (`"Test failed"`), even though `failure_analysis` already had a 15-category classification engine with root-cause and suggested-fix logic — the two were never connected. Fixed: `ReportGenerator` now runs every failed test through the same classification logic (`_classify`/`_find_root_cause`/`_suggest_fix`) automatically, no separate `failure.inspect` call needed, and attaches a category, severity (`Critical`/`High`/`Medium`/`Low`, derived from the category), real root cause, and suggested fix to each one. Also added a deterministic executive summary (risk level, one-line headline, severity/category breakdown, top 5 risks) built entirely from fixed templates over real data — no LLM-authored text. The diagnosis step reuses only the analyzer's pure classification methods (not `.inspect()`), so generating a report stays a read-only operation with no persistence side effects. 10 new tests in `tests/test_reporter.py`.

## Persistence

**Silent data loss on the second `save()` call.** `PersistentStore.save()` reassigned `self._data` to a brand-new dict on every call, but `namespace()` hands callers a live reference to the *old* dict and every module (`TestExecutor`, `DefectTracker`, `FixEngine`, `FailureAnalyzer`) calls `namespace()` exactly once in `__init__` and mutates that reference for the rest of the process's life. After the first `save()`, that reference silently detached from `self._data` — every mutation after that point never reached disk. Reproduced with `TestExecutor` running two tests into the same run: the second result vanished from disk. Fixed by merging into the existing dict object in place instead of reassigning. Regression test: `tests/test_persistence.py::test_repeated_save_on_same_instance_keeps_writing_new_mutations`.

## Fix loop / approval gate

**LLM agents could self-approve and self-apply patches.** `fix_loop_apply_patch(patch_id, read_only=False)` took `read_only` straight from the caller, so an agent could call `fix_loop.approve` followed by `fix_loop.apply_patch(read_only=False)` in the same session with no human involved (`approved_by` was just a string the agent could set itself). Fixed: `read_only=False` is now always rejected unless a human operator has set `QA_MCP_ALLOW_AUTO_APPLY=1` in the environment ahead of time — something an agent cannot do from within its own tool calls.

## Project scanner (`project_intelligence/scanner.py`)

Found by running `project.scan` against this repo's own directory:

- **Blank project name.** `Path(".").name` is `""`, so scanning "the current project" (the single most common invocation) always produced `name: ""`. Fixed by resolving to an absolute path first.
- **Python project misclassified as `language: "Unknown"`.** The scanner never excluded `.git`/`node_modules`/`__pycache__`/`.venv` from its `rglob("*")` walk. Extension-less `.git` blob files outnumbered actual `.py` files, so "most common extension" resolved to nothing. Fixed with `ProjectScanner.EXCLUDED_DIRS` and a `_walk()` helper used everywhere `rglob()` was called directly (also fixes framework/auth/testing-tool/route/endpoint/component/form detection, which had the same exposure).

## Test design (`test_design/generator.py`)

**`test.prioritize` crashed on the single most natural workflow.** Feeding `test.generate`'s own JSON output straight into `test.prioritize` — the obvious next step — crashed with `AttributeError` because the old implementation called `c.priority` directly, which only works on `TestCase` objects, not the dicts every MCP/CLI caller actually deals in. Fixed to accept both and always return JSON-serializable dicts.

## Mobile adapters (`adapters/mobile.py`)

Validated against a real physical Android device (OPPO/Realme CPH1819, Android 10) connected over `adb`, and a real Appium server + Maestro CLI — not mocks.

- **`AppiumAdapter.app_activity` was hardcoded to `.MainActivity`.** Most real apps — including system apps; Settings launches via `.Settings` — don't use that name, so `launch()` failed against almost anything in the real world. Added an `app_activity` constructor param (defaults unchanged if omitted).
- **No way to pass extra Appium capabilities.** This device's OEM (ColorOS) requires `appium:ignoreHiddenApiPolicyError` and `appium:noReset` just to create a session — without them, session creation fails on a `SecurityException` from the OEM's settings/clear-data guards. Added a `capabilities` constructor param.
- With both fixes, `launch`/`assert_element`/`tap`/`swipe`/`close` were all confirmed working end to end on the real device.
- **Maestro CLI is intermittently flaky over USB.** Running the identical `maestro test` invocation back to back produced `"...is not connected"` on 1 of 3 runs even though `adb devices` showed the device connected throughout — reproduced with the standalone CLI directly, unrelated to this project. `MaestroAdapter` is more exposed to this than `AppiumAdapter` because it spawns a new `maestro test` process per action rather than holding one session. Added a short retry (max 2 attempts) scoped specifically to that disconnect message; other failures are not retried.

## Test coverage added while validating all of the above

105 → 108 tests were added across this hardening pass, exercising real infrastructure wherever the sandbox allowed it instead of mocking: a real headless Chromium via Playwright, a real local HTTP server + real `k6` binary, a real SQLite database, a real throwaway git repo, and the real physical Android device described above. See `README.md#running-the-test-suite` for the current breakdown.
