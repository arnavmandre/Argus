import socket
import unittest
from unittest import mock

from api import stream_probe


class StreamProbeTests(unittest.TestCase):
    def test_probe_reports_unavailable_when_port_closed(self):
        with mock.patch(
            "api.stream_probe.socket.create_connection",
            side_effect=OSError("closed"),
        ):
            result = stream_probe.probe_stream_endpoint(
                host="127.0.0.1", signal_port=49100
            )
        self.assertFalse(result["available"])
        self.assertIn("not accepting", result["reason"].lower())

    def test_probe_reports_available_when_tcp_connects(self):
        with mock.patch("api.stream_probe.socket.create_connection") as conn:
            conn.return_value.__enter__ = mock.Mock(return_value=mock.Mock())
            conn.return_value.__exit__ = mock.Mock(return_value=False)
            result = stream_probe.probe_stream_endpoint(
                host="127.0.0.1", signal_port=49100
            )
        self.assertTrue(result["available"])
        self.assertEqual(result["signal_port"], 49100)
        self.assertIsNone(result["media_port"])

    def test_force_env_skips_probe(self):
        with mock.patch.dict("os.environ", {"URBANTWIN_STREAM_FORCE": "1"}):
            with mock.patch(
                "api.stream_probe.socket.create_connection"
            ) as conn:
                result = stream_probe.probe_stream_endpoint()
        conn.assert_not_called()
        self.assertTrue(result["available"])

    def test_available_stream_config_shape(self):
        probe = {
            "available": True,
            "host": "127.0.0.1",
            "signal_port": 49100,
            "media_port": None,
            "reason": None,
        }
        cfg = stream_probe.available_stream_config(
            "2026-09-20T00:00:00+00:00", probe, source="live"
        )
        self.assertEqual(cfg["status"], "available")
        self.assertEqual(cfg["signaling_host"], "127.0.0.1")
        self.assertEqual(cfg["signaling_port"], 49100)
        self.assertIsNone(cfg["media_port"])
        self.assertEqual(cfg["signaling_url"], "http://127.0.0.1:49100")
        self.assertIsInstance(cfg["session_token"], str)
        self.assertTrue(len(cfg["session_token"]) >= 16)


if __name__ == "__main__":
    unittest.main()
