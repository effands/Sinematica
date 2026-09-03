import unittest
from pathlib import Path


class YoutubeBlueprintContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.js = (root / "frontend" / "app.js").read_text(encoding="utf-8")

    def test_blueprint_is_a_real_navigation_tab(self):
        self.assertIn('data-tab="tab-youtube-blueprint"', self.html)
        self.assertIn('id="tab-youtube-blueprint"', self.html)
        self.assertIn("'tab-youtube-blueprint'", self.js)

    def test_strategy_retention_rights_and_analytics_fields_exist(self):
        for field in (
            "ytFormat", "ytMarket", "ytMicroNiche", "ytAudience", "ytDemand", "ytGap",
            "ytAngle", "ytHook", "ytOpenLoop", "ytPayoff", "ytSources", "ytCtr",
            "ytHookRetention", "ytAvd", "ytEndRetention", "ytRetentionShape",
        ):
            self.assertIn(f'id="{field}"', self.html)

    def test_blueprint_has_safety_and_single_variable_experiment_contract(self):
        self.assertIn("Never fabricate citations", self.js)
        self.assertIn("Change one variable per test", self.js)
        self.assertIn("No deceptive clickbait", self.js)
        self.assertIn("diagnoseYoutubeMetrics", self.js)

    def test_seven_modules_and_five_quality_gates_are_operational(self):
        for field in (
            "ytEditorialThesis", "ytFleetGovernance", "ytAiDisclosure", "ytLocalizationQa",
            "ytAudioQa", "ytContinuityLedger", "ytRiskRegister",
        ):
            self.assertIn(f'id="{field}"', self.html)
        for gate in ("Evidence", "Originality", "Rights", "Promise", "Technical"):
            self.assertIn(f'id="ytGate{gate}"', self.html)
        self.assertIn("QUALITY GATES:", self.js)
        self.assertIn("Use semantic pacing", self.js)

    def test_analytics_segments_audience_traffic_and_economics(self):
        for field in ("ytTrafficSource", "ytNewViewers", "ytReturningViewers", "ytRevenue", "ytHours"):
            self.assertIn(f'id="{field}"', self.html)
        self.assertIn("Revenue per production hour", self.js)


if __name__ == "__main__":
    unittest.main()
