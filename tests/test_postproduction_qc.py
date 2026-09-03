import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.postproduction_qc import (
    assess_scene_consistency,
    build_postproduction_report,
    parse_signalstats,
    summarize_signalstats,
)


class PostproductionQcTests(unittest.TestCase):
    SAMPLE = """lavfi.signalstats.YAVG=100\nlavfi.signalstats.UAVG=128\nlavfi.signalstats.VAVG=130\nlavfi.signalstats.YDIF=2\nlavfi.signalstats.YAVG=104\n"""

    def test_signalstats_parser_and_summary(self):
        summary = summarize_signalstats(parse_signalstats(self.SAMPLE))
        self.assertEqual(summary["exposure_y"], 102.0)
        self.assertEqual(summary["chroma_u"], 128.0)

    def test_consistency_flags_exposure_white_balance_and_flicker(self):
        findings = assess_scene_consistency([
            {"exposure_y": 100, "chroma_u": 128, "chroma_v": 128, "luma_variation": 2},
            {"exposure_y": 130, "chroma_u": 145, "chroma_v": 128, "luma_variation": 22},
            {"exposure_y": 101, "chroma_u": 128, "chroma_v": 128, "luma_variation": 3},
        ])
        issues = {item["issue"] for item in findings}
        self.assertIn("exposure_mismatch", issues)
        self.assertIn("white_balance_mismatch", issues)
        self.assertIn("possible_flicker_or_exposure_pumping", issues)

    def test_report_is_non_destructive_and_keeps_manual_artifact_checklist(self):
        with tempfile.TemporaryDirectory() as folder:
            clip = Path(folder) / "scene.mp4"
            clip.write_bytes(b"test")
            runner = lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=self.SAMPLE, stderr="")
            report = build_postproduction_report([str(clip)], ffmpeg_bin="ffmpeg-test", runner=runner)
        self.assertEqual(report["status"], "automatic_checks_passed")
        self.assertIn("hands/fingers", " ".join(report["manual_review"]))
        self.assertIn("never auto-repaired", report["limitations"])


if __name__ == "__main__":
    unittest.main()
