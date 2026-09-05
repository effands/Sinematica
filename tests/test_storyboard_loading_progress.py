import unittest
from pathlib import Path


class StoryboardLoadingProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
        cls.html = (root / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_progress_is_derived_from_completed_scene_count(self):
        self.assertIn("function setCuteAiSceneProgress(completedScenes, totalScenes", self.js)
        self.assertIn("Math.round((completed / total) * 100)", self.js)
        self.assertIn("setCuteAiSceneProgress(completedBeforeRequest, totalStoryScenes, true)", self.js)
        self.assertIn("setCuteAiSceneProgress(currentStoryboard.scenes?.length || 0, totalStoryScenes, false)", self.js)

    def test_loading_modal_shows_exact_scene_progress_text(self):
        self.assertIn('id="aiCuteLoadingProgressText"', self.html)
        self.assertIn("scene selesai · ${percent}%", self.js)


if __name__ == "__main__":
    unittest.main()
