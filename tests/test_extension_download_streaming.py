import unittest
from pathlib import Path


class ExtensionDownloadStreamingTests(unittest.TestCase):
    def test_download_does_not_serialize_mp4_through_execute_script(self):
        source = (Path(__file__).parents[1] / "engine" / "chrome-extension" / "background.js").read_text(
            encoding="utf-8"
        )
        start = source.index("async function handleDownloadRequest")
        end = source.index("async function notifyRegistration", start)
        handler = source[start:end]

        self.assertNotIn("chrome.scripting.executeScript", handler)
        self.assertNotIn("response.arrayBuffer()", handler)
        self.assertIn("response.body.getReader()", handler)
        self.assertIn("sendDownloadChunk", handler)


if __name__ == "__main__":
    unittest.main()
