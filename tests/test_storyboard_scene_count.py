import ast
import unittest
from pathlib import Path


class StoryboardSceneCountTests(unittest.TestCase):
    def test_ugc_mode_does_not_randomize_requested_scene_count(self):
        source_path = Path(__file__).resolve().parents[1] / "backend" / "gemini_storyboard.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        random_choice_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "random"
            and node.func.attr == "choice"
        ]

        self.assertEqual(random_choice_calls, [])
        self.assertIn("WAJIB TEPAT {scene_count} Scene", source)
        self.assertIn("actual_scene_count != scene_count", source)


if __name__ == "__main__":
    unittest.main()
