import ast
import unittest
from pathlib import Path


SOURCE_PATH = Path(__file__).parents[1] / "backend" / "gemini_storyboard.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
LOCALE_NODES = [
    node for node in TREE.body
    if (isinstance(node, (ast.Assign, ast.FunctionDef)) and (
        (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COUNTRY_LANGUAGE_MAP" for t in node.targets))
        or (isinstance(node, ast.FunctionDef) and node.name in {"resolve_target_language", "build_local_realism_rules", "build_children_localization_rules"})
    ))
]
NAMESPACE = {}
exec(compile(ast.Module(body=LOCALE_NODES, type_ignores=[]), str(SOURCE_PATH), "exec"), NAMESPACE)
resolve_target_language = NAMESPACE["resolve_target_language"]
build_local_realism_rules = NAMESPACE["build_local_realism_rules"]
build_children_localization_rules = NAMESPACE["build_children_localization_rules"]


class StoryboardLocaleTests(unittest.TestCase):
    def test_japan_infers_japanese_when_language_is_omitted(self):
        self.assertEqual(resolve_target_language("Japan", ""), "Jepang")

    def test_explicit_language_is_preserved(self):
        self.assertEqual(resolve_target_language("Japan", "Inggris"), "Inggris")

    def test_japan_rules_cover_character_environment_names_and_dialogue(self):
        rules = build_local_realism_rules("Japan")
        for expected in ("Skin Tone", "Wardrobe", "Lingkungan", "Nama Karakter", "Bahasa Suara/Dialog"):
            self.assertIn(expected, rules)
        self.assertIn("East Asian Japanese woman", rules)

    def test_children_rules_localize_learning_examples_and_language(self):
        rules = build_children_localization_rules("Japan", "Jepang")
        for expected in ("tujuan belajar", "huruf", "rima", "arah lalu lintas", "Jepang"):
            self.assertIn(expected, rules)
        self.assertIn("Japan", rules)


if __name__ == "__main__":
    unittest.main()
