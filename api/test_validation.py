import unittest

from api.validation import validate_run_request, validate_view_command


class ValidationTests(unittest.TestCase):
    def test_accepts_extreme_heat_rain_preset(self):
        body = {
            "temperature": 40,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
            "apply_recommended_interventions": True,
            "animation_frames": 3,
            "animation_duration_seconds": 6,
        }
        request, error = validate_run_request(body)
        self.assertIsNone(error)
        self.assertEqual(request["population"], 100000)
        self.assertEqual(request["animation_frames"], 3)

    def test_rejects_out_of_range_temperature(self):
        body = {
            "temperature": 99,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
            "apply_recommended_interventions": True,
        }
        request, error = validate_run_request(body)
        self.assertIsNone(request)
        self.assertEqual(error["error"]["code"], "validation_failed")

    def test_view_command_allow_list(self):
        ok, err = validate_view_command(
            {"state": "before", "camera": "ProblemZone", "overlay": "behavior"}
        )
        self.assertIsNone(err)
        bad, err2 = validate_view_command(
            {"state": "before", "camera": "/World/Hack", "overlay": "behavior"}
        )
        self.assertIsNone(bad)
        self.assertEqual(err2["error"]["code"], "validation_failed")


if __name__ == "__main__":
    unittest.main()
