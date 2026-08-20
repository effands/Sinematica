import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.gemini_storyboard import generate_storyboard


class CustomScriptStoryboardTests(unittest.TestCase):
    def test_affiliate_mode_requires_product_to_stay_inside_the_story_arc(self):
        provider_storyboard = {
            "film_title": "Drama Produk",
            "characters": [],
            "scenes": [{"scene_number": 1, "affiliate_scene": True, "prompt_for_flow": "Product scene"}],
        }
        config = {
            "enabled": True,
            "name": "Serum Cerah",
            "benefits": "melembapkan kulit",
            "cta": "cek keranjang",
            "style": "soft_selling",
            "scene_position": 1,
            "reference_paths": ["product-a.png"],
        }
        with patch("backend.gemini_storyboard.generate_text") as generate_text:
            generate_text.return_value = SimpleNamespace(
                text=json.dumps(provider_storyboard), provider="test", model="test"
            )
            result = generate_storyboard(
                premise="Seorang wanita bersiap menghadiri reuni.",
                scene_count=1,
                fixed_scene_duration=10,
                affiliate_config=config,
            )

        submitted_prompt = str(generate_text.call_args.args[0][0])
        self.assertIn("Serum Cerah", submitted_prompt)
        self.assertIn("tidak boleh terasa seperti iklan yang ditempel", submitted_prompt)
        self.assertEqual(result["affiliate_product"], config)

    def test_script_mode_preserves_source_script_and_marks_storyboard(self):
        source_script = "EPISODE 1\nSINTA: Aku tidak bersalah.\nBAGUS: Keluar dari rumah ini!"
        provider_storyboard = {
            "film_title": "Sinta",
            "characters": [],
            "scenes": [{"scene_number": 1, "prompt_for_flow": "A 10-second live-action scene."}],
        }

        with patch("backend.gemini_storyboard.generate_text") as generate_text:
            generate_text.return_value = SimpleNamespace(
                text=json.dumps(provider_storyboard),
                provider="test-provider",
                model="test-model",
            )
            result = generate_storyboard(
                premise=source_script,
                scene_count=1,
                fixed_scene_duration=10,
                script_mode=True,
            )

        submitted_prompt = str(generate_text.call_args.args[0][0])
        self.assertIn(source_script, submitted_prompt)
        self.assertIn("DILARANG mengubah alur, dialog, urutan kejadian", submitted_prompt)
        self.assertTrue(result["script_mode"])
        self.assertEqual(result["source_script"], source_script)


if __name__ == "__main__":
    unittest.main()
