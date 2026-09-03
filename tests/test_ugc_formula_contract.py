import unittest
from pathlib import Path


class UgcFormulaContractTests(unittest.TestCase):
    def test_raw_amateur_and_viral_formula_are_preserved_in_storyboard_prompt(self):
        source = (Path(__file__).parents[1] / "backend" / "gemini_storyboard.py").read_text(encoding="utf-8")
        self.assertIn('"raw_amateur"', source)
        self.assertIn('"conversion_hypotheses"', source)
        self.assertIn('"conversion_beat"', source)
        conversion_source = (Path(__file__).parents[1] / "backend" / "ugc_conversion.py").read_text(encoding="utf-8")
        self.assertIn("UGC AFFILIATE CONVERSION SYSTEM", conversion_source)
        self.assertIn("WHO + DOING WHAT + WHERE", source)
        self.assertIn("first 3 seconds", source)
        self.assertIn("autofocus hunting", source)
        self.assertIn("Never imitate a trailer", source)

    def test_render_stage_reasserts_raw_amateur_finish(self):
        source = (Path(__file__).parents[1] / "backend" / "jobs_executor.py").read_text(encoding="utf-8")
        self.assertIn('ugc_variant") or "").lower() == "raw_amateur"', source)
        self.assertIn("RAW AMATEUR SMARTPHONE LOCK", source)
        self.assertIn("NO cinematic dolly/crane/drone", source)

    def test_conversion_lab_fields_and_funnel_calculator_are_wired(self):
        root = Path(__file__).parents[1]
        html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
        for field_id in ("ugcAudience", "ugcAwareness", "ugcHookType", "ugcProof", "ugcConversionCta", "ugcMetricResults"):
            self.assertIn(f'id="{field_id}"', html)
        self.assertIn("getUgcConversionBrief", js)
        self.assertIn("ugc_conversion_brief", js)
        self.assertIn("calculateUgcFunnelMetrics", js)


if __name__ == "__main__":
    unittest.main()
