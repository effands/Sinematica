import unittest

from backend.storyboard_actor_references import attach_character_references, select_actor_references


ACTORS = [{
    "id": "goku-id", "name": "Son Goku", "seed": 123, "description": "Orange gi",
    "images": [{"path": "front.png"}, {"path": "side.png"}, {"path": "costume.webp"}],
}, {
    "id": "vegeta-id", "name": "Vegeta", "seed": 456, "description": "Blue armor",
    "images": [{"path": "vegeta.png"}],
}]


class StoryboardActorReferenceTests(unittest.TestCase):
    def test_selected_actor_keeps_name_id_and_all_owned_paths(self):
        info, selected = select_actor_references("goku-id", "Hero story", ACTORS)
        self.assertIn("source_actor_id=goku-id", info)
        self.assertIn("Son Goku", info)
        self.assertEqual(selected[0]["paths"], ["front.png", "side.png", "costume.webp"])

    def test_attachment_maps_by_id_then_exact_name_without_leaking(self):
        _, selected = select_actor_references("goku-id,vegeta-id", "", ACTORS)
        storyboard = attach_character_references({"characters": [
            {"name": "Son Goku"},
            {"name": "Wrong", "source_actor_id": "vegeta-id"},
            {"name": "Goku"},
        ]}, selected)

        self.assertEqual(storyboard["characters"][0]["source_actor_id"], "goku-id")
        self.assertEqual(storyboard["characters"][1]["source_actor_id"], "vegeta-id")
        self.assertNotIn("source_actor_id", storyboard["characters"][2])
        self.assertEqual(storyboard["character_references"]["goku-id"]["paths"],
                         ["front.png", "side.png", "costume.webp"])


if __name__ == "__main__":
    unittest.main()
