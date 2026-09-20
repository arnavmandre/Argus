# Phase 16 — Constrained LLM (plan)

## Tasks

1. `api/explain.py` — payload builder + deterministic template + optional LLM POST.
2. Wire `POST /api/runs/{id}/explain` in `api/server.py`; `RunManager.get_report`.
3. `api/test_explain.py` + server contract test for explain/404.
4. Frontend: `ExplainResponse`, `api.explain`, Next proxy route, `RunExplainPanel` on live complete runs.
5. `docs/PHASE16_CONSTRAINED_LLM.md` + CLAUDE.md honesty line.

## Acceptance

```powershell
cd .worktrees/phase13-streaming-kit
python -m unittest api.test_explain api.test_server -v
cd frontend; npx tsc --noEmit
```

- Explain without `URBANTWIN_LLM_URL` returns `source: deterministic`.
- Payload JSON contains no citizen home/destination/id fields.
