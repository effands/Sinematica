import unittest
from pathlib import Path


class StoryPartsFrontendTests(unittest.TestCase):
    def test_part_controls_and_continuation_payload_are_wired(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (root / "frontend" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="storyPartSizeInput"', html)
        self.assertIn("btnGenerateNextStoryPart", js)
        self.assertIn("previous_part_context", js)
        self.assertIn("compactStoryPartContext", js)
        self.assertIn("mergeStoryPart", js)
        self.assertIn("total_scene_count", js)

    def test_fleet_credit_card_shows_videos_remaining_at_fifteen_credits_each(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
        self.assertIn("FLOW_CREDITS_PER_VIDEO = 15", js)
        self.assertIn("estimateFlowVideosRemaining", js)
        self.assertIn("videoRemainingText", js)
        self.assertIn("15 kredit/video", js)


if __name__ == "__main__":
    unittest.main()
