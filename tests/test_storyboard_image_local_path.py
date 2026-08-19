import tempfile
import unittest
from pathlib import Path
import sys
import types

sys.modules.setdefault("requests", types.SimpleNamespace(get=lambda *args, **kwargs: None, post=lambda *args, **kwargs: None))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))

from backend.storyboard_image import fetch_image_bytes


class StoryboardImageLocalPathTests(unittest.TestCase):
    def test_reads_cached_character_sheet_from_local_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sheet.png"
            path.write_bytes(b"png-bytes")

            result = fetch_image_bytes(str(path))

        self.assertEqual(result, {"mime_type": "image/png", "data": b"png-bytes"})


if __name__ == "__main__":
    unittest.main()
