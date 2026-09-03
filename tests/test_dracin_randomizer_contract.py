import unittest
from pathlib import Path


class DracinRandomizerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.js = (root / "frontend" / "app.js").read_text(encoding="utf-8")

    def test_random_theme_controls_exist_without_removing_original_presets(self):
        self.assertIn('id="randomizeDracinThemes"', self.html)
        self.assertIn('id="dracinRandomOptions"', self.html)
        self.assertIn("CEO Menyamar Jadi Karyawan Biasa", self.html)

    def test_generator_combines_multiple_story_dimensions_and_tracks_repeats(self):
        self.assertIn("generateDracinThemeOptions", self.js)
        self.assertIn("usedDracinCombinations", self.js)
        for dimension in ("leads", "triggers", "secrets", "stakes", "tones"):
            self.assertIn(f"const {dimension}", self.js)
        self.assertIn("generateDracinThemeOptions(8)", self.js)
        self.assertIn("const shuffle = items", self.js)
        self.assertIn("shuffled.tones[index]", self.js)


if __name__ == "__main__":
    unittest.main()
