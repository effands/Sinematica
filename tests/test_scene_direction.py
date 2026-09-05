import unittest

from backend.scene_direction import (
    apply_no_branding_direction,
    build_speaker_lock,
    choose_shot_count,
    ensure_unique_character_signatures,
    timeline_markers,
)


class SceneDirectionTests(unittest.TestCase):
    def test_no_branding_guard_is_explicit_and_idempotent(self):
        once = apply_no_branding_direction("Cinematic palace scene.")
        twice = apply_no_branding_direction(once)

        self.assertIn("NO BROADCAST BRANDING", once)
        self.assertIn("TV station logo", once)
        self.assertIn("watermark", once)
        self.assertEqual(twice, once)

    def test_shot_count_follows_scene_energy(self):
        self.assertEqual(choose_shot_count({"action_summary": "Pasukan menyerbu dalam perang besar"}), 5)
        self.assertEqual(choose_shot_count({"action_summary": "Maya menangis lalu berbisik jujur", "dialogue": [{}]}), 3)
        self.assertEqual(choose_shot_count({"action_summary": "Maya membuka surat dan berjalan ke meja"}), 4)

    def test_timeline_contains_exact_number_of_shots(self):
        self.assertEqual(timeline_markers(3), ["0-3.3 seconds", "3.3-6.6 seconds", "6.6-10 seconds"])
        self.assertEqual(len(timeline_markers(4)), 4)
        self.assertEqual(timeline_markers(5), ["0-2 seconds", "2-4 seconds", "4-6 seconds", "6-8 seconds", "8-10 seconds"])

    def test_wardrobe_and_forward_are_not_combat_and_door_contact_wins(self):
        self.assertEqual(choose_shot_count({}, 'Same wardrobe. She looks forward and says "Pulang."'), 3)
        self.assertEqual(choose_shot_count({}, 'Preserve wardrobe while folding a letter.'), 4)
        self.assertEqual(choose_shot_count({}, 'After the battle she closes the car door.'), 3)

    def test_character_signatures_are_present_and_unique(self):
        characters = [
            {"id": 1, "name": "Maya", "description": "Wanita muda berambut hitam."},
            {"id": 2, "name": "Siska", "description": "Wanita muda berambut hitam."},
        ]
        result = ensure_unique_character_signatures(characters)

        self.assertTrue(all(c.get("visual_signature") for c in result))
        self.assertEqual(len({c["visual_signature"] for c in result}), 2)
        self.assertIn(result[0]["visual_signature"], result[0]["description"])
        self.assertIn(result[1]["visual_signature"], result[1]["description"])

    def test_speaker_lock_names_signature_position_and_exact_line(self):
        characters = [
            {"id": 1, "name": "Maya", "visual_signature": "crimson jacket and jade pendant"},
            {"id": 2, "name": "Siska", "visual_signature": "cobalt dress and silver hairpin"},
        ]
        scene = {
            "characters_in_scene": [1, 2],
            "dialogue": [{"speaker_id": 1, "line": "Aku tidak akan menyerah.", "screen_position": "left"}],
        }

        lock = build_speaker_lock(scene, characters)
        self.assertIn("Maya", lock)
        self.assertIn("crimson jacket and jade pendant", lock)
        self.assertIn("left", lock)
        self.assertIn('"Aku tidak akan menyerah."', lock)
        self.assertIn("non-speakers keep their mouths closed", lock)


if __name__ == "__main__":
    unittest.main()
