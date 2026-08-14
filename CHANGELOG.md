# Changelog

Detailed record of real bugs found and fixed while building out test coverage and validating this project end-to-end (unit tests, full workflow runs, and real hardware/network validation). Kept separate from `README.md` so the README stays focused on how to use the project rather than how it was hardened.

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
