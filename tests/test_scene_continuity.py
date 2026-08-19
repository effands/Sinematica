import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.film_stitcher import extract_continuity_frame
from backend.scene_continuity import build_continuity_prompt, continuity_start_image
from engine.omniflash.generators.i2v import generate_video_i2v


class SceneContinuityTests(unittest.TestCase):
    def test_extracts_frame_two_tenths_before_video_end(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            Path(command[-1]).write_bytes(b"jpeg")
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "scene_01.mp4"
            frame = root / "continuity_01.jpg"
            video.write_bytes(b"video")

            result = extract_continuity_frame(
                video,
                frame,
                ffmpeg_bin="ffmpeg-test",
                runner=runner,
            )

            self.assertEqual(result, str(frame))
            self.assertEqual(calls[0][0][1:4], ["-y", "-sseof", "-0.2"])
            self.assertEqual(frame.read_bytes(), b"jpeg")

    def test_failed_extraction_does_not_leave_broken_frame(self):
        def runner(command, **kwargs):
            Path(command[-1]).write_bytes(b"partial")
            return subprocess.CompletedProcess(command, 1, "", "bad video")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "scene.mp4"
            frame = root / "continuity.jpg"
            video.write_bytes(b"video")

            result = extract_continuity_frame(
                video,
                frame,
                ffmpeg_bin="ffmpeg-test",
                runner=runner,
            )

            self.assertIsNone(result)
            self.assertFalse(frame.exists())

    def test_only_immediately_previous_completed_scene_can_seed_next_scene(self):
        self.assertEqual(continuity_start_image("frame-media", 1, 2), "frame-media")
        self.assertIsNone(continuity_start_image("frame-media", 1, 3))
        self.assertIsNone(continuity_start_image(None, 1, 2))

    def test_continuity_prompt_declares_reference_as_literal_opening_frame(self):
        result = build_continuity_prompt("She opens the door.", "frame-media")

        self.assertIn("literal opening frame", result)
        self.assertIn("Continue the same", result)
        self.assertTrue(result.startswith("She opens the door."))


class ContinuityI2VContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_i2v_request_sends_previous_frame_as_start_image(self):
        class Bridge:
            def __init__(self):
                self.body = None

            async def api_request(self, endpoint, body, instance_id=None):
                self.body = body
                return {"status": 200, "data": {"media": [{"name": "video-media"}]}}

        bridge = Bridge()
        result = await generate_video_i2v(
            bridge,
            prompt="Continue walking.",
            aspect="landscape",
            project_id="project-1",
            start_image_id="previous-final-frame",
            duration=10,
            instance_id="profile-1",
        )

        self.assertEqual(result, ["video-media"])
        self.assertEqual(
            bridge.body["requests"][0]["startImage"],
            {"mediaId": "previous-final-frame"},
        )


if __name__ == "__main__":
    unittest.main()
