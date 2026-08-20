import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GalleryClipLayoutTests(unittest.TestCase):
    def test_clip_grid_uses_bounded_two_row_scroll_area(self):
        app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")

        self.assertIn('class="gallery-clips-grid"', app)
        self.assertIn(".gallery-clips-grid", css)
        self.assertIn("max-height:", css)
        self.assertIn("overflow-y: auto", css)


if __name__ == "__main__":
    unittest.main()
