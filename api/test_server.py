"""HTTP contract tests for the stdlib UrbanTwin API server."""
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from api.run_manager import RunManager
from api.server import create_app


ROOT = Path(__file__).resolve().parents[1]

_PROBE_UNAVAILABLE = {
    "available": False,
    "host": "127.0.0.1",
    "signal_port": 49100,
    "media_port": 47998,
    "reason": "Kit signaling port is not accepting connections.",
}


def _valid_body(**overrides):
    body = {
        "temperature": 31,
        "humidity": 55,
        "rainfall": 12,
        "population": 42000,
        "apply_recommended_interventions": True,
        "animation_frames": 1,
        "animation_duration_seconds": 1,
    }
    body.update(overrides)
    return body


def _minimal_report(config) -> None:
    report_path = (
        Path(config.root) / "data" / "runs" / config.run_id / "simulation_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    scenario = {
        "temperature": config.temperature,
        "humidity": config.humidity,
        "rainfall": config.rainfall,
        "population": config.population,
    }
    report = {
        "scenario": scenario,
        "before": {
            "metrics": {},
            "citizens": [
                {
                    "id": "c1",
                    "archetype": "student",
                    "behavior": "SEEK_SHADE",
                    "home": "A",
                    "destination": "B",
                },
                {
                    "id": "c2",
                    "archetype": "worker",
                    "behavior": "SEEK_SHADE",
                    "home": "A",
                    "destination": "B",
                },
            ],
            "problem_zones": [],
            "problem_buildings": [],
            "problem_routes": [],
            "zones": [],
            "buildings": [],
            "routes": [],
            "interventions": {},
        },
        "after": {
            "metrics": {},
            "citizens": [],
            "problem_zones": [],
            "problem_buildings": [],
            "problem_routes": [],
            "zones": [],
            "buildings": [],
            "routes": [],
            "interventions": {},
        },
        "advisor": {
            "summary": "",
            "problem_zones": [],
            "problem_buildings": [],
            "problem_routes": [],
            "recommendations": [],
            "affected_buildings": {},
            "explanation": [],
            "supported_interventions": {},
        },
        "intervention": {},
        "delta": {},
        "control": {"scenario": {}, "metrics": {}, "recommendations": []},
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")


def _wait_until(predicate, timeout=2.0, interval=0.02) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class ServerContractTests(unittest.TestCase):
    def setUp(self):
        self._probe_patcher = mock.patch(
            "api.shapes.probe_stream_endpoint",
            return_value=_PROBE_UNAVAILABLE,
        )
        self._probe_patcher.start()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.run_root = Path(self._tmpdir.name)

        def fast_pipeline(config):
            _minimal_report(config)
            return {"status": "complete", "run_id": config.run_id}

        self.manager = RunManager(self.run_root, pipeline_fn=fast_pipeline)
        self.server, bound = create_app(ROOT, manager=self.manager)
        self.assertIs(bound, self.manager)
        host, port = self.server.server_address[:2]
        self.host = host
        self.port = port
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmpdir.cleanup()
        self._probe_patcher.stop()

    def _request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
        try:
            payload = None
            hdrs = {"Accept": "application/json"}
            if headers:
                hdrs.update(headers)
            if body is not None:
                payload = json.dumps(body).encode("utf-8")
                hdrs["Content-Type"] = "application/json"
            conn.request(method, path, body=payload, headers=hdrs)
            response = conn.getresponse()
            raw = response.read()
            content_type = response.getheader("Content-Type")
            cache = response.getheader("Cache-Control")
            data = json.loads(raw.decode("utf-8")) if raw else None
            return response.status, data, content_type, cache
        finally:
            conn.close()

    def test_health_is_live_mode(self):
        status, data, content_type, cache = self._request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")
        self.assertEqual(cache, "no-store")
        self.assertEqual(data["mode"], "live")
        self.assertEqual(data["source"], "live")
        self.assertTrue(data["capabilities"]["http_api"])
        self.assertTrue(data["capabilities"]["live_simulation"])
        self.assertFalse(data["capabilities"]["omniverse_streaming"])

    def test_scenarios_constraints(self):
        status, data, _, _ = self._request("GET", "/api/scenarios")
        self.assertEqual(status, 200)
        self.assertEqual(data["source"], "live")
        self.assertEqual(data["constraints"]["temperature"], [-10, 45])
        self.assertEqual(data["constraints"]["population"], [25000, 100000])
        self.assertTrue(any(p["id"] == "baseline" for p in data["presets"]))

    def test_stream_config_and_model_card(self):
        status, stream, _, _ = self._request("GET", "/api/stream/config")
        self.assertEqual(status, 200)
        self.assertEqual(stream["source"], "live")
        self.assertEqual(stream["status"], "offline")

        status, card, _, _ = self._request("GET", "/api/model-card")
        self.assertEqual(status, 200)
        self.assertEqual(card["source"], "live")
        self.assertIn("models", card)
        self.assertIn("limitations", card)
        self.assertNotIn("dataset_sha256", card)

    def test_post_queues_quickly_and_poll_completes(self):
        started = time.perf_counter()
        status, created, _, _ = self._request("POST", "/api/runs", _valid_body())
        elapsed = time.perf_counter() - started
        self.assertEqual(status, 202)
        self.assertEqual(created["status"], "queued")
        self.assertIn("run_id", created)
        self.assertLess(elapsed, 1.0, "POST must return without waiting for the pipeline")

        run_id = created["run_id"]

        def poll_complete():
            st, summary, _, _ = self._request("GET", f"/api/runs/{run_id}")
            return st == 200 and summary["status"] == "complete"

        self.assertTrue(_wait_until(poll_complete), "run should reach complete")
        status, summary, _, _ = self._request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(summary["source"], "live")
        self.assertEqual(summary["scenario"]["temperature"], 31)

        status, listing, _, _ = self._request("GET", "/api/runs")
        self.assertEqual(status, 200)
        self.assertEqual(listing["source"], "live")
        self.assertIsNone(listing["active_run_id"])

    def test_validation_failure_is_422(self):
        status, data, _, _ = self._request(
            "POST",
            "/api/runs",
            _valid_body(temperature=99),
        )
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "validation_failed")

    def test_bad_json_is_400(self):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
        try:
            conn.request(
                "POST",
                "/api/runs",
                body=b"{not-json",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            response = conn.getresponse()
            raw = response.read()
            data = json.loads(raw.decode("utf-8"))
            self.assertEqual(response.status, 400)
            self.assertIn("error", data)
        finally:
            conn.close()

    def test_conflict_when_worker_busy(self):
        entered = threading.Event()
        release = threading.Event()

        def slow_pipeline(config):
            entered.set()
            release.wait(timeout=5)
            _minimal_report(config)
            return {"status": "complete", "run_id": config.run_id}

        self.manager._pipeline_fn = slow_pipeline
        status, first, _, _ = self._request("POST", "/api/runs", _valid_body())
        self.assertEqual(status, 202)
        self.assertTrue(entered.wait(timeout=2))

        status, conflict, _, _ = self._request(
            "POST",
            "/api/runs",
            _valid_body(temperature=26, humidity=40, rainfall=5, population=30000),
        )
        self.assertEqual(status, 409)
        self.assertEqual(conflict["error"]["code"], "conflict")

        listing_status, listing, _, _ = self._request("GET", "/api/runs")
        self.assertEqual(listing_status, 200)
        self.assertEqual(listing["active_run_id"], first["run_id"])

        release.set()
        self.assertTrue(
            _wait_until(lambda: self.manager.list_active() is None),
            "busy slot should clear after worker exits",
        )

    def test_unknown_run_is_404(self):
        status, data, _, _ = self._request("GET", "/api/runs/run_missing_000000")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "not_found")

        status, data, _, _ = self._request("DELETE", "/api/runs/run_missing_000000")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "not_found")

        status, data, _, _ = self._request(
            "GET",
            "/api/runs/run_missing_000000/citizens?state=before&limit=10&offset=0",
        )
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "not_found")

    def test_cancel_returns_updated_summary(self):
        self.manager._pause_workers = True
        status, created, _, _ = self._request("POST", "/api/runs", _valid_body())
        self.assertEqual(status, 202)
        run_id = created["run_id"]
        time.sleep(0.05)

        status, summary, _, _ = self._request("DELETE", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(summary["run_id"], run_id)
        self.assertEqual(summary["status"], "cancelled")
        self.assertEqual(summary["source"], "live")

        self.manager._pause_workers = False
        self.assertTrue(_wait_until(lambda: self.manager.list_active() is None))

    def test_view_allow_list_and_undelivered(self):
        status, created, _, _ = self._request("POST", "/api/runs", _valid_body())
        self.assertEqual(status, 202)
        run_id = created["run_id"]
        self.assertTrue(
            _wait_until(
                lambda: self.manager.get_run(run_id)["status"]
                in {"complete", "failed", "cancelled"}
            )
        )

        status, result, _, _ = self._request(
            "POST",
            f"/api/runs/{run_id}/view",
            {"state": "before", "camera": "Overview", "overlay": "behavior"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["accepted"])
        self.assertFalse(result["delivered"])
        self.assertEqual(result.get("delivery"), "webrtc_client")
        self.assertIn("reason", result)
        self.assertEqual(
            result["command"],
            {"state": "before", "camera": "Overview", "overlay": "behavior"},
        )

        status, rejected, _, _ = self._request(
            "POST",
            f"/api/runs/{run_id}/view",
            {"state": "before", "camera": "NotACamera", "overlay": "behavior"},
        )
        self.assertEqual(status, 422)
        self.assertEqual(rejected["error"]["code"], "validation_failed")

        status, viewport, _, _ = self._request(
            "POST",
            "/api/runs/viewport/view",
            {"state": "before", "camera": "Overview", "overlay": "behavior"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(viewport["accepted"])
        self.assertFalse(viewport["delivered"])
        self.assertEqual(viewport.get("delivery"), "webrtc_client")

        status, missing, _, _ = self._request(
            "POST",
            "/api/runs/run_does_not_exist/view",
            {"state": "before", "camera": "Overview", "overlay": "behavior"},
        )
        self.assertEqual(status, 404)

    def test_citizens_pagination(self):
        status, created, _, _ = self._request("POST", "/api/runs", _valid_body())
        self.assertEqual(status, 202)
        run_id = created["run_id"]
        self.assertTrue(
            _wait_until(lambda: self.manager.get_run(run_id)["status"] == "complete")
        )

        status, page, _, _ = self._request(
            "GET",
            f"/api/runs/{run_id}/citizens?state=before&limit=1&offset=0",
        )
        self.assertEqual(status, 200)
        self.assertEqual(page["source"], "live")
        self.assertEqual(page["limit"], 1)
        self.assertEqual(page["offset"], 0)
        self.assertEqual(page["total_in_run"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["id"], "c1")

        status, page2, _, _ = self._request(
            "GET",
            f"/api/runs/{run_id}/citizens?state=before&limit=1&offset=1",
        )
        self.assertEqual(status, 200)
        self.assertEqual(page2["items"][0]["id"], "c2")

    def test_explain_deterministic_for_complete_run(self):
        status, created, _, _ = self._request("POST", "/api/runs", _valid_body())
        self.assertEqual(status, 202)
        run_id = created["run_id"]
        self.assertTrue(
            _wait_until(lambda: self.manager.get_run(run_id)["status"] == "complete")
        )

        status, explain, _, _ = self._request("POST", f"/api/runs/{run_id}/explain")
        self.assertEqual(status, 200)
        self.assertEqual(explain["run_id"], run_id)
        self.assertIn(explain["source"], ("deterministic", "llm"))
        self.assertTrue(explain["text"])
        self.assertIsInstance(explain["claims"], list)

    def test_explain_unknown_run_is_404(self):
        status, data, _, _ = self._request(
            "POST",
            "/api/runs/run_missing_000000/explain",
        )
        self.assertEqual(status, 404)
        self.assertEqual(data["error"]["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
