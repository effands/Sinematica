import tempfile
import unittest
from pathlib import Path

from backend.media_download import resolve_exact_media_url, stream_download


class _Response:
    headers = {"content-type": "video/mp4"}

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"video-"
        yield b"bytes"


class DirectMediaDownloadTests(unittest.TestCase):
    def test_streams_video_to_destination_without_base64(self):
        calls = []

        def opener(url, stream, timeout, headers):
            calls.append((url, stream, timeout, headers))
            return _Response()

        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "scene.mp4"
            count = stream_download("https://example.test/video", destination, opener=opener)

            self.assertEqual(destination.read_bytes(), b"video-bytes")
            self.assertEqual(count, 11)
            self.assertTrue(calls[0][1])
            self.assertEqual(calls[0][3]["User-Agent"], "Mozilla/5.0")


class ExactFlowMediaUrlTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_exact_signed_url_using_affilia_trpc_route(self):
        media_id = "aa2043fe-24be-4ef7-825a-87bb42098569"

        class Bridge:
            def __init__(self):
                self.calls = []

            async def trpc_request(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return {
                    "data": {"result": {"data": {"json": {
                        "url": f"https://flow-content.google/video/{media_id}?Expires=123"
                    }}}}
                }

        bridge = Bridge()
        result = await resolve_exact_media_url(bridge, media_id, "project-1", "profile-1")

        self.assertEqual(result, f"https://flow-content.google/video/{media_id}?Expires=123")
        self.assertIn("media.getMediaUrlRedirect", bridge.calls[0][0])
        self.assertEqual(bridge.calls[0][1]["instance_id"], "profile-1")

    async def test_rejects_redirect_for_a_different_media_id(self):
        class Bridge:
            async def trpc_request(self, *_args, **_kwargs):
                return {"data": {"url": "https://flow-content.google/video/wrong-id"}}

        result = await resolve_exact_media_url(Bridge(), "expected-id", "project-1")

        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
