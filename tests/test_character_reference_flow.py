import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.character_reference_flow import (
    resolve_character_reference_paths,
    upload_character_references,
)


STORYBOARD = {"character_references": {
    "goku-id": {"name": "Son Goku", "paths": ["front.png", "side.png", "costume.webp"]},
    "vegeta-id": {"name": "Vegeta", "paths": ["vegeta.png"]},
}}


class CharacterReferenceFlowTests(unittest.IsolatedAsyncioTestCase):
    def test_executor_requires_flow_to_apply_owned_references(self):
        source = (Path(__file__).resolve().parents[1] / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
        self.assertIn("reference_media_ids=reference_media_ids or None", source)
        self.assertIn('not img_res.get("reference_applied")', source)
        self.assertIn("ATTACHED CHARACTER REFERENCES ARE THE SINGLE SOURCE OF TRUTH", source)

    def test_character_gets_only_its_actor_paths(self):
        self.assertEqual(
            resolve_character_reference_paths({"source_actor_id": "goku-id"}, STORYBOARD, require_exists=False),
            ["front.png", "side.png", "costume.webp"],
        )
        self.assertEqual(
            resolve_character_reference_paths({"name": "Vegeta"}, STORYBOARD, require_exists=False),
            ["vegeta.png"],
        )

    def test_partial_name_never_fuzzy_matches(self):
        self.assertEqual(resolve_character_reference_paths({"name": "Goku"}, STORYBOARD, require_exists=False), [])

    async def test_upload_preserves_order_and_returns_media_ids(self):
        calls = []
        async def uploader(bridge, path, project_id=None, instance_id=None):
            calls.append((Path(path).name, project_id, instance_id))
            return f"media-{Path(path).stem}"

        with TemporaryDirectory() as temp_dir:
            paths = [Path(temp_dir) / "front.png", Path(temp_dir) / "side.png"]
            for path in paths:
                path.write_bytes(b"x")
            result = await upload_character_references(
                object(), [str(p) for p in paths], "project", "profile", upload_fn=uploader
            )

        self.assertEqual(result, ["media-front", "media-side"])
        self.assertEqual([call[0] for call in calls], ["front.png", "side.png"])


if __name__ == "__main__":
    unittest.main()
