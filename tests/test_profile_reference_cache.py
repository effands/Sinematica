import tempfile
import unittest
from pathlib import Path

from backend.profile_reference_cache import (
    ensure_character_media_for_profile,
    ensure_files_for_profile,
)


class ProfileReferenceCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_character_sheet_gets_distinct_id_per_profile_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "hero.png"
            sheet.write_bytes(b"image")
            calls = []

            async def upload(_bridge, path, project_id=None, instance_id=None):
                calls.append((path, project_id, instance_id))
                return f"media-{instance_id}-{len(calls)}"

            characters = [{"id": 1, "name": "Hero"}]
            paths = {1: str(sheet)}
            cache = {}
            first, _ = await ensure_character_media_for_profile(
                object(), characters, paths, "project-a", "profile-a", cache, upload_fn=upload
            )
            first_again, uploaded = await ensure_character_media_for_profile(
                object(), characters, paths, "project-a", "profile-a", cache, upload_fn=upload
            )
            second, _ = await ensure_character_media_for_profile(
                object(), characters, paths, "project-b", "profile-b", cache, upload_fn=upload
            )

            self.assertEqual(first[1], first_again[1])
            self.assertEqual(uploaded, [])
            self.assertNotEqual(first[1], second[1])
            self.assertEqual(len(calls), 2)

    async def test_arbitrary_reference_file_is_uploaded_once_per_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "storyboard.png"
            sheet.write_bytes(b"image")
            calls = []

            async def upload(_bridge, path, project_id=None, instance_id=None):
                calls.append((project_id, instance_id))
                return f"media-{instance_id}"

            cache = {}
            ids1, count1 = await ensure_files_for_profile(
                object(), [str(sheet)], "p", "a", cache, upload_fn=upload
            )
            ids2, count2 = await ensure_files_for_profile(
                object(), [str(sheet)], "p", "a", cache, upload_fn=upload
            )
            self.assertEqual(ids1, ids2)
            self.assertEqual((count1, count2), (1, 0))


if __name__ == "__main__":
    unittest.main()
