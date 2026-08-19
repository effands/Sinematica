import unittest

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


if __name__ == "__main__":
    unittest.main()
