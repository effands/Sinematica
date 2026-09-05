import unittest
from pathlib import Path

from backend.character_seed_guard import missing_character_seeds


class CharacterSeedGuardTests(unittest.TestCase):
    def test_reports_character_whose_seed_image_was_not_generated(self):
        characters = [
            {"id": 1, "name": "Maya"},
            {"id": 2, "name": "Siska"},
        ]

        result = missing_character_seeds(characters, {1: "maya-media"})

        self.assertEqual(result, ["Siska"])

    def test_accepts_media_indexed_by_string_id_or_character_name(self):
        characters = [
            {"id": 1, "name": "Maya"},
            {"id": 2, "name": "Siska"},
        ]

        result = missing_character_seeds(
            characters,
            {"1": "maya-media", "siska": "siska-media"},
        )

        self.assertEqual(result, [])

    def test_default_character_and_storyboard_templates_do_not_request_visible_metadata_text(self):
        from backend import settings

        cfg = settings.get_settings()
        char_template = cfg["character_seed_template"]
        scene_template = cfg["scene_storyboard_template"]

        forbidden_character_phrases = [
            "Title bar at top",
            "subtle seed tag",
            "Character Seed:",
            "Character Name:",
            "Large \"CHARACTER SHEET\" title",
        ]
        for phrase in forbidden_character_phrases:
            self.assertNotIn(phrase, char_template)

        forbidden_scene_phrases = [
            "Header reading",
            "Title bar reading",
            "showing: \"[Shot Number]",
            "duration tag",
        ]
        for phrase in forbidden_scene_phrases:
            self.assertNotIn(phrase, scene_template)

        self.assertIn("must not appear visually", char_template)
        self.assertIn("no readable writing", scene_template.lower())

    def test_executor_uses_textless_character_sheet_cache_revision(self):
        source = Path(__file__).resolve().parents[1] / "backend" / "jobs_executor.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn('TEXTLESS_CHARACTER_SHEET_REVISION = "textless-v2"', text)
        self.assertIn('char["sheet_revision"] = TEXTLESS_CHARACTER_SHEET_REVISION', text)


if __name__ == "__main__":
    unittest.main()
