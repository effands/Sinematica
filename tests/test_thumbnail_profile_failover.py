import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.routers.storyboard import GenerateThumbnailRequest, generate_thumbnail_endpoint


class _Bridge:
    def instance_snapshot(self):
        return [
            {"instance_id": "profile-a", "name": "A", "connected": True, "ready": True, "project_id": "project-a"},
            {"instance_id": "profile-b", "name": "B", "connected": True, "ready": True, "project_id": "project-b"},
        ]


class ThumbnailProfileFailoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_recaptcha_failure_uses_next_profile(self):
        generate = AsyncMock(side_effect=[
            ValueError("Google Flow (403): reCAPTCHA evaluation failed; PUBLIC_ERROR_UNUSUAL_ACTIVITY"),
            {"image_url": "https://example.test/image.png", "media_id": "media-b"},
        ])
        with patch("backend.bridge_manager.get_bridge", return_value=_Bridge()), \
             patch("omniflash.generators.generate_character_image", generate), \
             patch("backend.routers.storyboard.settings.get_settings", return_value={}):
            result = await generate_thumbnail_endpoint(GenerateThumbnailRequest(prompt="cover"))

        self.assertEqual(result["profile_used"], "B")
        self.assertEqual([call.kwargs["instance_id"] for call in generate.await_args_list], ["profile-a", "profile-b"])

    async def test_all_captcha_failures_return_actionable_message(self):
        generate = AsyncMock(side_effect=ValueError("403 reCAPTCHA evaluation failed"))
        with patch("backend.bridge_manager.get_bridge", return_value=_Bridge()), \
             patch("omniflash.generators.generate_character_image", generate), \
             patch("backend.routers.storyboard.settings.get_settings", return_value={}):
            with self.assertRaises(HTTPException) as caught:
                await generate_thumbnail_endpoint(GenerateThumbnailRequest(prompt="cover"))

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("semua profil Chrome", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
