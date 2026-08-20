import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.gemini_storyboard import generate_storyboard


class CustomScriptStoryboardTests(unittest.TestCase):
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
