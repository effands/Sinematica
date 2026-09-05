import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.routers.storyboard import DownloadThumbnailRequest, download_thumbnail_endpoint


class ThumbnailDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_image_as_attachment(self):
        bridge = type("Bridge", (), {})()
        bridge.download_url = AsyncMock(return_value={"data": b"png-data", "content_type": "image/png"})
        request = DownloadThumbnailRequest(
            image_url="https://flow-content.google/example.png",
            instance_id="profile-a",
        )
        with patch("backend.bridge_manager.get_bridge", return_value=bridge):
            response = await download_thumbnail_endpoint(request)

        self.assertEqual(response.body, b"png-data")
        self.assertEqual(response.headers["content-disposition"], 'attachment; filename="youtube_thumbnail.png"')
        bridge.download_url.assert_awaited_once_with(
            request.image_url, instance_id="profile-a", timeout=120,
        )

    async def test_rejects_untrusted_download_url(self):
        with self.assertRaises(HTTPException) as caught:
            await download_thumbnail_endpoint(
                DownloadThumbnailRequest(image_url="https://example.com/not-flow.png")
            )
        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
