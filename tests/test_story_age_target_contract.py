import unittest
from pathlib import Path


class StoryAgeTargetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.js = (root / "frontend" / "app.js").read_text(encoding="utf-8")

    def test_age_target_is_available_beside_story_catalog(self):
        self.assertIn('id="storyAgeTarget"', self.html)
        for value in ("toddler", "early_child", "older_child", "preteen", "teen", "genz_young", "genz_adult", "millennial", "genx", "senior", "family"):
            self.assertGreaterEqual(self.html.count(f'value="{value}"'), 2)

    def test_age_target_syncs_brief_and_child_safety_mode(self):
        self.assertIn("applyStoryAgeTarget", self.js)
        self.assertIn("briefAudienceInput", self.js)
        self.assertIn("childSafe", self.js)
        self.assertIn("dataset.ageGroup", self.js)

    def test_age_drives_universe_conflict_and_emotion(self):
        for field in ("storyUniverseSelect", "storyConflictSelect", "storyEmotionSelect"):
            self.assertIn(f'id="{field}"', self.html)
        self.assertIn("STORY_CONFLICTS", self.js)
        self.assertIn("refreshStoryUniverses", self.js)
        self.assertIn("universeDirection", self.js)
        self.assertIn("sandwich generation", self.js)

    def test_ai_can_replace_fallback_options_contextually(self):
        self.assertIn('id="generateAudienceUniverseAi"', self.html)
        self.assertIn("/api/storyboard/audience_universe", self.js)
        self.assertIn("aiStoryUniverseMap", self.js)
        self.assertIn("Opsi lokal tetap dapat dipakai", self.js)


if __name__ == "__main__":
    unittest.main()
