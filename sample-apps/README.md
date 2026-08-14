# Sample apps

Two zero-extra-dependency sample apps for seeing the full `qa_mcp` pipeline run against something real, each with intentional bugs so the resulting report has real findings to look at.

| App | Demonstrates | `test.generate` dimensions used |
|---|---|---|
| [`checkout-demo/`](checkout-demo/) | A checkout form + API — a single-page storefront flow | `fields`, `business_rules` |
| [`task-manager/`](task-manager/) | A login-gated internal tool with roles and a task state machine | `fields`, `roles`, `states` |

Run either with:

```bash
python3 sample-apps/checkout-demo/run_demo.py
python3 sample-apps/task-manager/run_demo.py
```

Each one scans itself, generates a full deterministic test suite, runs a handful of real tests (real headless-Chromium browser test, real HTTP API calls, real SQLite check where relevant) against a small app with 2-3 intentional bugs, and produces HTML **and PDF** reports with an executive risk summary and a root cause on every failure. See each app's own README for exactly what it demonstrates and what the two runs should show.
