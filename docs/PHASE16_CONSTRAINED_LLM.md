# Phase 16 — Constrained LLM explanations

Optional narrative layer over **already computed** simulator output. It does not
run the simulation, change the advisor, or drive Kit.

## Backend

Module: `api/explain.py`

| Function | Role |
|---|---|
| `build_explanation_payload(report)` | Allow-listed slice of `simulation_report.json` |
| `explain_run(payload)` | Deterministic template; optional LLM when configured |

Environment:

- `URBANTWIN_LLM_URL` — optional HTTP endpoint. Request body:
  `{"messages":[{"role":"system","content":"…"},{"role":"user","content":"<payload JSON>"}]}`
  Response: OpenAI-style `choices[0].message.content` or top-level `"text"`.

HTTP:

```http
POST /api/runs/{run_id}/explain
```

Returns:

```json
{
  "run_id": "run_…",
  "source": "deterministic",
  "text": "…",
  "claims": ["scenario:…", "recommendation:increase_shade"],
  "unavailable_reason": "optional when LLM failed"
}
```

Errors: `404` unknown run; `409` run exists but no report yet.

## Frontend

- Live mode only (`URBANTWIN_API_BASE` set): **Explain results** on completed runs.
- Mock fixtures: explain route returns `404`; button hidden.
- Failures are silent; the deterministic advisor panel stays visible.

## Honesty

- Metrics and effectiveness come from `Simulation/main.py`, not from the explainer.
- Default path is a deterministic template — not an LLM — and makes no medical,
  meteorological, or engineering claims beyond the report disclaimers.

## Next

**Phase 17 (done on `phase13-streaming-kit`)** — single launcher, smoke test, and
judge runbook: `docs/DEMO_RUNBOOK.md`, `tools/demo_launch.ps1`,
`tools/demo_smoke.py`.
