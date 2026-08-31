import tempfile
import unittest
from pathlib import Path

from backend.media_download import (
    resolve_exact_media_url,
    resolve_exact_media_url_with_retry,
    stream_download,
    stream_exact_media_with_retry,
)


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
        self.assertIn(f"name={media_id}", bridge.calls[0][0])
        self.assertNotIn("projects%2F", bridge.calls[0][0])
        self.assertEqual(bridge.calls[0][1]["instance_id"], "profile-1")

    async def test_resource_name_is_reduced_to_uuid_for_redirect_route(self):
        media_id = "aa2043fe-24be-4ef7-825a-87bb42098569"

        class Bridge:
            def __init__(self):
                self.url = ""

            async def trpc_request(self, url, **_kwargs):
                self.url = url
                return {
                    "status": 200,
                    "responseUrl": f"https://flow-content.google/video/{media_id}",
                }

        bridge = Bridge()
        result = await resolve_exact_media_url(
            bridge, f"projects/project-1/media/{media_id}", "project-1"
        )

        self.assertEqual(result, f"https://flow-content.google/video/{media_id}")
        self.assertTrue(bridge.url.endswith(f"?name={media_id}"))

    async def test_rejects_redirect_for_a_different_media_id(self):
        class Bridge:
            async def trpc_request(self, *_args, **_kwargs):
                return {"data": {"url": "https://flow-content.google/video/wrong-id"}}

        result = await resolve_exact_media_url(Bridge(), "expected-id", "project-1")

        self.assertEqual(result, "")

    async def test_never_mistakes_labs_resolver_endpoint_for_final_video_url(self):
        media_id = "expected-id"

        class Bridge:
            async def trpc_request(self, *_args, **_kwargs):
                return {
                    "status": 200,
                    "responseUrl": (
                        "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect"
                        f"?name=projects%2Fp%2Fmedia%2F{media_id}"
                    ),
                    "data": {},
                }

        result = await resolve_exact_media_url(Bridge(), media_id, "project-1")

        self.assertEqual(result, "")

    async def test_accepts_trusted_response_url_even_when_cdn_path_omits_media_id(self):
        class Bridge:
            async def trpc_request(self, *_args, **_kwargs):
                return {
                    "status": 200,
                    "data": {"url": "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect"},
                    "responseUrl": "https://flow-content.google/v/opaque-signed-token?Expires=123",
                }

        result = await resolve_exact_media_url(Bridge(), "expected-media-id", "project-1")

        self.assertEqual(result, "https://flow-content.google/v/opaque-signed-token?Expires=123")

    async def test_accepts_opaque_redirect_status_when_final_url_is_trusted(self):
        class Bridge:
            async def trpc_request(self, *_args, **_kwargs):
                return {
                    "status": 0,
                    "responseUrl": "https://flow-content.google/v/opaque-token?Expires=123",
                }

        result = await resolve_exact_media_url(Bridge(), "media-id", "project-1")

        self.assertEqual(result, "https://flow-content.google/v/opaque-token?Expires=123")

    async def test_surfaces_resolver_http_error_instead_of_publish_message(self):
        class Bridge:
            async def trpc_request(self, *_args, **_kwargs):
                return {"status": 401, "error": "AUTH_REQUIRED"}

        with self.assertRaisesRegex(RuntimeError, "HTTP 401.*AUTH_REQUIRED"):
            await resolve_exact_media_url(Bridge(), "media-id", "project-1")

    async def test_retries_until_flow_publishes_the_signed_url(self):
        class Bridge:
            def __init__(self):
                self.calls = 0

            async def trpc_request(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls < 3:
                    return {"status": 404, "error": "Requested entity was not found."}
                return {
                    "status": 200,
                    "responseUrl": "https://flow-content.google/v/final-signed-token?Expires=123",
                }

        bridge = Bridge()
        result = await resolve_exact_media_url_with_retry(
            bridge, "expected-media-id", "project-1", "profile-2", attempts=3, delay=0
        )

        self.assertEqual(result, "https://flow-content.google/v/final-signed-token?Expires=123")
        self.assertEqual(bridge.calls, 3)

    async def test_re_resolves_signed_url_after_transient_cdn_404(self):
        resolved_urls = []
        downloaded_urls = []

        async def resolver(_bridge, _media_id, _project_id, _instance_id):
            url = f"https://flow-content.google/v/signed-{len(resolved_urls) + 1}"
            resolved_urls.append(url)
            return url

        def downloader(url, destination):
            downloaded_urls.append(url)
            if len(downloaded_urls) == 1:
                raise RuntimeError("404 Internal Error")
            Path(destination).write_bytes(b"fresh-video")

        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "scene.mp4"
            result = await stream_exact_media_with_retry(
                object(), "media-1", "project-1", "profile-1", destination,
                attempts=2, delay=0, resolver=resolver, downloader=downloader,
            )

            self.assertEqual(result, "https://flow-content.google/v/signed-2")
            self.assertEqual(resolved_urls, downloaded_urls)
            self.assertEqual(destination.read_bytes(), b"fresh-video")


if __name__ == "__main__":
    unittest.main()
