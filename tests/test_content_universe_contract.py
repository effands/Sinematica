import unittest
from pathlib import Path


class ContentUniverseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.js = (root / "frontend" / "app.js").read_text(encoding="utf-8")

    def test_real_navigation_tab_and_generator_exist(self):
        self.assertIn('data-tab="tab-content-universe"', self.html)
        self.assertIn('id="tab-content-universe"', self.html)
        self.assertIn('id="generateContentUniverse"', self.html)
        self.assertIn('buildContentUniverse', self.js)

    def test_all_life_stages_and_six_dimensions_exist(self):
        for audience in ("toddler", "early_child", "older_child", "preteen", "teen", "genz_young", "genz_adult", "millennial", "genx", "senior", "family"):
            self.assertIn(f'value="{audience}"', self.html)
        for field in ("universeAudience", "universeEmotion", "universeGoal", "universeGenre", "universeFormat", "universeComplexity"):
            self.assertIn(f'id="{field}"', self.html)

    def test_storyboard_handoff_includes_safety_voice_and_direction(self):
        self.assertIn("Safety & dignity", self.js)
        self.assertIn("Voice/dialogue", self.js)
        self.assertIn("Camera/audio", self.js)
        self.assertIn("Do not stereotype the age group", self.js)


if __name__ == "__main__":
    unittest.main()
