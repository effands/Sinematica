import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ActorReferenceUiTests(unittest.TestCase):
    def test_actor_form_supports_multi_image_preview_and_payload(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="actorImages"', html)
        self.assertIn("multiple", html)
        self.assertIn('id="actorImagePreview"', html)
        self.assertIn('id="actorImageCount"', html)
        self.assertIn("formData.append('image_files'", js)
        self.assertIn("MAX_ACTOR_REFERENCE_IMAGES = 4", js)

    def test_actor_cards_render_image_array_with_legacy_fallback(self):
        js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
        self.assertIn("actor.images", js)
        self.assertIn("actor.image_url", js)
        self.assertIn("Referensi", js)


if __name__ == "__main__":
    unittest.main()
