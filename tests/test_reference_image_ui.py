import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReferenceImageUiTests(unittest.TestCase):
    def test_preview_renderer_targets_the_existing_reference_preview_container(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="imagePreviewList"', html)
        self.assertIn("getElementById('imagePreviewList')", js)
        self.assertNotIn("getElementById('refImageList')", js)
        self.assertIn("MAX_STORYBOARD_REFERENCE_IMAGES = 7", js)
        self.assertIn("reference-preview-remove", js)
        self.assertIn("selectedRefFiles.splice(index, 1)", js)


if __name__ == "__main__":
    unittest.main()
