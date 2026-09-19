"""Live-mode API response envelopes built from simulator reports."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integration.export_api_mocks import (  # noqa: E402
    LIVE_RUN_WARNINGS,
    health_fixture,
    model_card_fixture,
    run_summary,
    scenarios_fixture,
    stream_config_fixture,
)


def live_run_summary(
    report,
    created_utc,
    run_id,
    *,
    status="complete",
    warnings=None,
    error=None,
) -> dict:
    """Shape a simulator report as a live RunSummary envelope."""
    return run_summary(
        report,
        created_utc,
        run_id,
        source="live",
        status=status,
        warnings=LIVE_RUN_WARNINGS if warnings is None else warnings,
        error=error,
    )


def live_citizen_page(report, run_id, state, limit, offset) -> dict:
    """Paginated citizen page for a live run (serves the full simulated set)."""
    if state not in ("before", "after"):
        raise ValueError(f"state must be 'before' or 'after', got {state!r}")
    citizens = report[state]["citizens"]
    total_in_run = len(citizens)
    start = max(0, int(offset))
    size = max(0, int(limit))
    items = citizens[start : start + size]
    return {
        "run_id": run_id,
        "state": state,
        "source": "live",
        "limit": size,
        "offset": start,
        "total": total_in_run,
        "total_in_run": total_in_run,
        "items": items,
        "notes": [
            f"Live run serves {total_in_run} simulated citizens paginated.",
            "Citizens are survey-calibrated synthetic people, not real individuals.",
        ],
    }


def live_health(checked_utc) -> dict:
    return health_fixture(checked_utc, source="live")


def live_scenarios() -> dict:
    return scenarios_fixture(source="live")


def live_stream_config(checked_utc) -> dict:
    return stream_config_fixture(checked_utc, source="live")


def live_model_card(card, exported_utc) -> dict:
    return model_card_fixture(card, exported_utc, source="live")
