# Argus AI RAG urban advisor

The RAG advisor is an optional, grounded ranking layer over the existing Argus
simulator. It does not calculate metrics or predict an after-state. It receives a
bounded completed-run report, retrieves local intervention records, asks
`openai/gpt-oss-120b` to rank only actions the simulator can execute, validates
the response, and returns structured recommendations.

The deterministic threshold advisor remains the reliable execution authority and
fallback. A missing API key, missing optional dependency, stale index, malformed
model response, invented action, or unknown target cannot stop the demo.

## Setup

```powershell
python -m pip install -r api\requirements-rag.txt
python -m api.rag.build_index
$env:GROQ_API_KEY = "your-key"
python -m api --host 127.0.0.1 --port 8000
```

Copy `.env.example` to `.env` and replace the placeholder, or set the key in
PowerShell. The API automatically loads the root `.env` without overriding a
value already present in the shell. The index is written to the ignored
`data/.rag_index/` directory. Rebuild it whenever
`data/urban_interventions.json` changes. Without the built semantic index, the
advisor uses a dependency-free lexical retriever and reports that backend
truthfully.

## Endpoint

After a run completes:

```http
POST /api/runs/{run_id}/advise
```

The backend obtains the report from its own run manager. The browser does not
send simulator output back to the API.

The response identifies `advisor_mode`, `fallback_used`, retrieval backend,
knowledge hash, model, retrieved knowledge, and ranked recommendations. Records
whose `source_status` is `NEEDS_SOURCE` must be shown as unverified contextual
leads, never as evidence-backed planning guidance.

## Apply and test boundary

Only these current simulator IDs are executable:

- `increase_shade`
- `improve_drainage`
- `alternative_pedestrian_routes`
- `no_major_intervention`

The validator requires every model-selected action to match the action on a
record that was actually retrieved. It also checks any supplied route, building,
or zone target against the bounded report. The existing simulator owns action
strengths and all before/after computation.

The frontend lets the operator select one or more returned actions. “Apply
selected and re-simulate” starts a new run with the optional
`selected_recommendation_ids` request field. The API accepts only the simulator's
allow-list, the pipeline forwards those IDs to `Simulation/main.py`, and the
simulator passes them through its existing `recommended_interventions(...)`
function. The after-state is therefore a real simulator run using only the
selected actions.

## Tests

```powershell
python -m unittest api.test_rag -v
python -m unittest discover -s api -p "test_*.py"
python -m unittest integration.test_export_interfaces integration.test_run_pipeline
```
