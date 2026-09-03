import unittest

from backend.audience_universe import normalize_audience_universe


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


if __name__ == "__main__":
    unittest.main()
