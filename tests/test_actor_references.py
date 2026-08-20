import io
import unittest
from types import SimpleNamespace

from backend.actor_references import (
    actor_reference_paths,
    normalize_actor,
    resolve_character_actor,
    validate_image_uploads,
)


def upload(name="front.png", content_type="image/png", size=32):
    return SimpleNamespace(filename=name, content_type=content_type, file=io.BytesIO(b"x" * size))


class ActorReferenceTests(unittest.TestCase):
    def test_legacy_actor_becomes_one_primary_image(self):
        actor = normalize_actor({"id": "a1", "name": "Son Goku", "image_path": "one.png", "image_url": "/one.png"})
        self.assertEqual(actor["images"], [{"path": "one.png", "url": "/one.png", "primary": True}])

    def test_resolution_prefers_id_then_exact_name_without_fuzzy_match(self):
        actors = [{"id": "a1", "name": "Son Goku"}, {"id": "a2", "name": "Gohan"}]
        self.assertEqual(resolve_character_actor({"source_actor_id": "a1", "name": "Wrong"}, actors)["id"], "a1")
        self.assertEqual(resolve_character_actor({"name": " son   goku "}, actors)["id"], "a1")
        self.assertIsNone(resolve_character_actor({"name": "Goku"}, actors))

    def test_paths_are_unique_and_preserve_order(self):
        actor = {"images": [{"path": "front.png"}, {"path": "side.png"}], "image_path": "front.png"}
        self.assertEqual(actor_reference_paths(actor), ["front.png", "side.png"])

    def test_validates_count_type_and_size_and_rewinds_stream(self):
        valid = [upload(name=f"{i}.png") for i in range(4)]
        validate_image_uploads(valid, max_bytes=64)
        self.assertTrue(all(item.file.tell() == 0 for item in valid))
        with self.assertRaisesRegex(ValueError, "maksimal 4"):
            validate_image_uploads(valid + [upload("fifth.png")])
        with self.assertRaisesRegex(ValueError, "JPEG, PNG, atau WebP"):
            validate_image_uploads([upload("bad.gif", "image/gif")])
        with self.assertRaisesRegex(ValueError, "10 MB"):
            validate_image_uploads([upload(size=65)], max_bytes=64)


if __name__ == "__main__":
    unittest.main()
