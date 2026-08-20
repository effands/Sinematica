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

    def test_actor_modal_uses_studio_layout_and_custom_dropzone(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
        self.assertIn('class="actor-studio-modal"', html)
        self.assertIn('class="actor-upload-dropzone"', html)
        self.assertIn('class="actor-modal-grid"', html)
        self.assertIn('class="actor-modal-footer"', html)
        self.assertIn('class="actor-modal-cancel"', html)
        self.assertIn(".actor-studio-modal", css)
        self.assertIn("@media (max-width: 720px)", css)


if __name__ == "__main__":
    unittest.main()
