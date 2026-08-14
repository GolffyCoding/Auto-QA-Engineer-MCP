# task-manager

A second sample app for `qa_mcp` — a small internal task tracker with login, two roles (admin/member), and a real task state machine. Where [`checkout-demo`](../checkout-demo/) only exercises `test.generate`'s `fields` and `business_rules` dimensions, this one also exercises `roles` and `states`. Stdlib-only, zero extra dependencies, in-memory data.

Two seeded users:

| Username | Password | Role |
|---|---|---|
| `alice` | `admin123` | admin |
| `bob` | `member123` | member |

Task state machine (as declared): `todo` → (`start`) → `in_progress` → (`complete`) → `done` → (`reopen`) → `todo`.

**Two intentional bugs**, left in on purpose:

1. **State-machine bug** (`app.py`) — the `"complete"` action is accepted from *any* state, not just `in_progress`, so a task can skip straight from `todo` to `done` without the server ever enforcing the declared transitions.
2. **Access-control bug** (`app.py`) — `DELETE /api/tasks/<id>` doesn't check the caller's role or task ownership. Any authenticated user — including a non-admin who doesn't own the task — can delete someone else's task.

## Run it

```bash
python3 sample-apps/task-manager/run_demo.py
```

This scans the app, runs `test.generate` with `fields` + `roles` + `states` together in one call, runs 5 representative real tests, and produces `report.generate_html` **and** `report.generate_pdf`.

## What you should see

3 of 5 tests pass; 2 fail, each correctly diagnosed:

| Test | Result | What it demonstrates |
|---|---|---|
| `dashboard-login-browser` | ✅ Pass | Real browser login flow working end to end |
| `login-rejects-wrong-password` | ✅ Pass | Auth validation working correctly |
| `task-state-machine-valid-path` | ✅ Pass | The declared `todo → in_progress → done` path working correctly |
| `task-skip-state-transition` | ❌ Fail — **High** | Bug 1: `todo → done` skips `in_progress` and isn't rejected |
| `delete-requires-owner-or-admin` | ❌ Fail — **High** | Bug 2: a non-owner, non-admin member can delete another user's task |

Compare `generated-test-cases.json` after a run against `checkout-demo`'s: this one includes `Access Control` and `State Transition` categories that checkout-demo's field-only suite never produces.
