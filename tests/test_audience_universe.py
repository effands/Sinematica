import unittest
from unittest.mock import patch

from backend.audience_universe import normalize_audience_universe
from backend.routers.storyboard import AudienceUniverseRequest, generate_audience_universe_endpoint


class AudienceUniverseTests(unittest.TestCase):
    def test_normalizes_unique_universes_conflicts_and_emotions(self):
        payload = {
            "universes": [
                {"name": f"Universe {index}", "conflicts": [f"Konflik {index}-{item}" for item in range(4)]}
                for index in range(6)
            ],
            "emotions": ["malu menjadi berani", "cemas menjadi lega", "ragu menjadi yakin", "marah menjadi paham", "sepi menjadi terhubung"],
        }
        result = normalize_audience_universe(payload)
        self.assertEqual(len(result["universes"]), 6)
        self.assertEqual(len(result["universes"][0]["conflicts"]), 4)
        self.assertEqual(len(result["emotions"]), 5)

    def test_rejects_thin_ai_output(self):
        with self.assertRaises(ValueError):
            normalize_audience_universe({"universes": [{"name": "Sama", "conflicts": ["a"]}], "emotions": ["sedih"]})

    def test_storyboard_route_returns_frontend_contract(self):
        generated = {
            "universes": [{"name": "Kampung", "conflicts": ["Konflik A", "Konflik B", "Konflik C"]}],
            "emotions": ["ragu menjadi yakin"],
            "provider": "mock",
        }
        with patch("backend.routers.storyboard.generate_audience_universe", return_value=generated) as call:
            response = generate_audience_universe_endpoint(
                AudienceUniverseRequest(audience="Senior 60+", country="Indonesia")
            )

        self.assertTrue(response["success"])
        self.assertEqual(response["package"], generated)
        self.assertEqual(call.call_args.args[0]["audience"], "Senior 60+")


if __name__ == "__main__":
    unittest.main()
