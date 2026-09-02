import re
import unittest

from backend.gemini_storyboard import build_auto_art_direction, build_children_variation_packet, format_auto_art_direction


class ChildrenStoryVariationTests(unittest.TestCase):
    def test_auto_art_direction_varies_color_objects_and_motif(self):
        directions = [build_auto_art_direction() for _ in range(6)]
        self.assertEqual(6, len({item["token"] for item in directions}))
        self.assertGreaterEqual(len({item["palette"] for item in directions}), 2)
        rendered = format_auto_art_direction(directions[0])
        self.assertIn("story-driving hero object", rendered)
        self.assertIn("recurring visual motif", rendered)

    def test_packets_change_between_generations(self):
        packets = [build_children_variation_packet() for _ in range(8)]
        tokens = [re.search(r"KIDS-\d{8}", packet).group(0) for packet in packets]
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertEqual(len(packets), len(set(packets)))

    def test_packet_forces_fresh_names_and_story_elements(self):
        packet = build_children_variation_packet()
        self.assertIn("ATURAN ANTI-KONTEN-BERULANG", packet)
        self.assertIn("Buat nama karakter baru", packet)
        self.assertIn("Variasikan sedikitnya lima unsur", packet)
        self.assertIn("Properti cerita:", packet)


if __name__ == "__main__":
    unittest.main()
