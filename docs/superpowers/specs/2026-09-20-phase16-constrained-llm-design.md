# Phase 16 — Constrained LLM explanations (design)

## Problem

Operators want readable narrative over UrbanTwin run results without letting a
model invent metrics, places, Kit commands, or intervention effectiveness.

## Principles

1. **Bounded payload** — `build_explanation_payload(report)` copies only scenario,
   before/after metric dicts, advisor summary and recommendation ids/labels,
   problem zones/buildings/routes already in the report, advisor explanation
   lines, and optional report-level warnings/limitations. Citizen arrays never
   leave the simulator; counts only.
2. **Deterministic default** — With no `URBANTWIN_LLM_URL`, `explain_run` returns
   a template that concatenates payload fields. No network; acceptance passes
   without API keys.
3. **Optional LLM** — When `URBANTWIN_LLM_URL` is set, POST the JSON payload with
   a system prompt forbidding new facts. Parse text; on any failure, fall back to
   the template and set `unavailable_reason`.
4. **Advisor authority** — Threshold advisor recommendations and re-simulation
   remain the only source of “what to do” and “what worked”.
5. **Graceful UI** — `POST /api/runs/{id}/explain` is optional. Frontend hides
   failures; mock mode does not pretend to explain without the Python API.

## API

- `POST /api/runs/{run_id}/explain` → `{ run_id, source: "deterministic"|"llm", text, claims[], unavailable_reason? }`
- 404 unknown run; 409 when no simulator report yet.

## Security

- LLM URL and keys stay server-side (`URBANTWIN_LLM_URL` only). Never
  `NEXT_PUBLIC_*` for secrets.
