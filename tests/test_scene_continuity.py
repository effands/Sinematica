import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.film_stitcher import extract_continuity_frame
from backend.scene_continuity import build_continuity_prompt, continuity_start_image


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


if __name__ == "__main__":
    unittest.main()
