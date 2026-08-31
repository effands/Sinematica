import unittest

from engine.omniflash.generators.i2v import generate_video_r2v


class _CaptchaThenSuccessBridge:
    def __init__(self):
        self.calls = []

    async def api_request(self, endpoint, body, instance_id=None):
        self.calls.append((endpoint, body, instance_id))
        if len(self.calls) == 1:
            return {
                "status": 403,
                "data": {"error": {"message": "reCAPTCHA evaluation failed"}},
            }
        return {"status": 200, "data": {"media": [{"name": "render-with-refs"}]}}


class R2VReferenceRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_recaptcha_failure_retries_r2v_with_same_references(self):
        bridge = _CaptchaThenSuccessBridge()

        media = await generate_video_r2v(
            bridge,
            "prompt",
            "portrait",
            "project-1",
            ["character-a", "storyboard-a"],
            instance_id="profile-1",
            attempts=2,
            retry_delay=0,
        )

        self.assertEqual(media, ["render-with-refs"])
        self.assertEqual(len(bridge.calls), 2)
        for _endpoint, body, _instance in bridge.calls:
            self.assertEqual(
                body["requests"][0]["referenceImages"],
                [{"mediaId": "character-a"}, {"mediaId": "storyboard-a"}],
            )

    async def test_r2v_rejects_empty_reference_list(self):
        with self.assertRaisesRegex(ValueError, "minimal satu image reference"):
            await generate_video_r2v(
                _CaptchaThenSuccessBridge(), "prompt", "portrait", "project-1", [],
                attempts=1, retry_delay=0,
            )


if __name__ == "__main__":
    unittest.main()
