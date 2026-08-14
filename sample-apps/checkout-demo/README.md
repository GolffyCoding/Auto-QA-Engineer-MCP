# checkout-demo

A minimal sample app for seeing the whole `qa_mcp` pipeline run against something real: scan → generate → execute → diagnose → report. Zero extra dependencies — the "app" is Python's stdlib `http.server` plus a static HTML form, and the "database" is a throwaway SQLite file.

It has **two intentional bugs**, left in on purpose so the demo report has real failures with real root causes to look at, instead of a wall of green:

1. **Business logic bug** (`app.py`) — `POST /api/checkout` doesn't cap a coupon discount at the order amount, so a large enough coupon produces a negative total.
2. **API bug** (`app.py`) — `GET /api/orders/<id>` for an order that doesn't exist returns `200` with an empty body instead of `404`.

Plus one **intentionally broken row** seeded into `checkout.db` (`orders.user_id = 999`, which has no matching `users.id`) so `db.check_fk_integrity` has something real to find.

## Run it

```bash
python3 sample-apps/checkout-demo/run_demo.py
```

This will:

1. Seed `checkout.db` with the broken foreign key
2. Start the sample app on `http://127.0.0.1:8420`
3. Run `project.scan` against this folder
4. Run `test.generate` for the `checkout` feature (fields + a business rule) — the full generated suite is saved to `generated-test-cases.json` so you can see everything `qa_mcp` would generate, not just the handful of tests actually run below
5. Run 5 representative real tests against the app (`tests/`) — a browser test (real headless Chromium via Playwright), two API tests, and a database integrity check — via `test.create_run`/`test.run`
6. Generate a full report via `report.generate_html`

## What you should see

2 of 5 tests pass; 3 fail, each correctly diagnosed:

| Test | Result | What it demonstrates |
|---|---|---|
| `checkout-form-happy-path` | ✅ Pass | Real browser interaction working end to end |
| `checkout-api-valid-order` | ✅ Pass | Real API request/response working end to end |
| `checkout-api-coupon-exceeds-amount` | ❌ Fail — **High**, `logic` | The business-logic bug: total goes negative |
| `orders-api-404-for-missing-order` | ❌ Fail — **High**, `logic` | The API bug: wrong status code for a missing resource |
| `db-orders-fk-integrity` | ❌ Fail — **Critical**, `database` | The seeded orphaned foreign key, found via `db.check_fk_integrity` |

The generated HTML report (path printed at the end, under `./reports/` at the repo root) has an executive summary with a `risk_level` of `Critical` (driven by the database failure) and a root cause + suggested fix attached to every failed test — not just a bare error string. See the main [README.md](../../README.md#reporting-built-to-hand-to-a-stakeholder-not-just-a-ci-dashboard) for what that looks like.

For a version with roles and a state machine (a login-gated internal tool, not just a public form), see [`../task-manager/`](../task-manager/).
