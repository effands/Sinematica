import asyncio
import base64
import json
import unittest

from engine.omniflash.bridge import ExtensionBridge, is_routable_bridge_message


class _OpenWebSocket:
    closed = False

    def __init__(self, bridge):
        self.bridge = bridge
        self.sent = []

    async def send(self, payload):
        message = json.loads(payload)
        self.sent.append(message)
        self.bridge.handle_message(
            json.dumps({
                "type": "download_response",
                "id": message["id"],
                "status": 200,
                "content_type": "video/mp4",
                "data_base64": base64.b64encode(b"mp4-bytes").decode("ascii"),
            }),
            self,
            "profile-1",
        )


class _ChunkedWebSocket(_OpenWebSocket):
    async def send(self, payload):
        message = json.loads(payload)
        self.sent.append(message)
        req_id = message["id"]
        chunks = [b"large-", b"video-bytes"]
        self.bridge.handle_message(json.dumps({
            "type": "download_start", "id": req_id, "status": 200,
            "content_type": "video/mp4", "total_chunks": len(chunks)
        }), self, "profile-1")
        for index, chunk in enumerate(chunks):
            self.bridge.handle_message(json.dumps({
                "type": "download_chunk", "id": req_id, "index": index,
                "data_base64": base64.b64encode(chunk).decode("ascii")
            }), self, "profile-1")
        self.bridge.handle_message(json.dumps({
            "type": "download_complete", "id": req_id, "status": 200
        }), self, "profile-1")


class _SilentWebSocket(_OpenWebSocket):
    async def send(self, payload):
        self.sent.append(json.loads(payload))


class _RetryBridge(ExtensionBridge):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def download_url(self, url, instance_id=None, timeout=180):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary download failure")
        return {"data": b"recovered", "content_type": "video/mp4"}


class DownloadThroughChromeTests(unittest.IsolatedAsyncioTestCase):
    def test_websocket_router_forwards_all_download_and_trpc_responses(self):
        for message_type in (
            "api_response", "trpc_response", "download_response",
            "download_start", "download_chunk", "download_complete",
        ):
            self.assertTrue(is_routable_bridge_message(message_type), message_type)
        self.assertFalse(is_routable_bridge_message("flow_ui_request"))

    async def test_download_retry_reuses_rendered_url_without_rendering_again(self):
        bridge = _RetryBridge()

        result = await bridge.download_url_with_retry("https://example.invalid/video.mp4", attempts=2, delay=0)

        self.assertEqual(result["data"], b"recovered")
        self.assertEqual(bridge.calls, 2)

    async def test_download_timeout_has_clear_non_empty_error(self):
        bridge = ExtensionBridge()
        ws = _SilentWebSocket(bridge)
        bridge.register_instance("profile-1", ws, "Chrome Profile")

        with self.assertRaisesRegex(RuntimeError, "Unduhan media Flow.*timeout"):
            await bridge.download_url("https://example.invalid/video.mp4", "profile-1", timeout=0.01)

    async def test_download_url_reassembles_chunked_websocket_transfer(self):
        bridge = ExtensionBridge()
        ws = _ChunkedWebSocket(bridge)
        bridge.register_instance("profile-1", ws, "Chrome Profile")

        result = await bridge.download_url("https://example.invalid/video.mp4", "profile-1", timeout=0.2)

        self.assertEqual(result["data"], b"large-video-bytes")
        self.assertEqual(result["content_type"], "video/mp4")

    async def test_download_url_returns_bytes_from_authenticated_chrome_profile(self):
        bridge = ExtensionBridge()
        ws = _OpenWebSocket(bridge)
        bridge.register_instance("profile-1", ws, "Chrome Profile")

        result = await bridge.download_url(
            "https://example.invalid/rendered-video.mp4",
            instance_id="profile-1",
        )

        self.assertEqual(result["data"], b"mp4-bytes")
        self.assertEqual(result["content_type"], "video/mp4")
        self.assertEqual(ws.sent[0]["type"], "download_request")
        self.assertEqual(ws.sent[0]["url"], "https://example.invalid/rendered-video.mp4")


if __name__ == "__main__":
    unittest.main()
