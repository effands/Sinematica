import unittest

from backend.ugc_conversion import (
    build_conversion_prompt,
    calculate_funnel_metrics,
    conversion_brief_issues,
    normalize_conversion_brief,
)


class UgcConversionTests(unittest.TestCase):
    def complete_brief(self):
        return {
            "enabled": True, "audience": "pekerja kantor", "objective": "purchase",
            "why_now": "promo resmi berakhir malam ini", "awareness_level": "problem_aware",
            "hook_type": "problem", "hook": "Jerawat muncul sebelum meeting?",
            "angle": "percaya diri", "problem": "jerawat merah", "agitate": "jadi minder",
            "solution": "patch menutup area", "proof": "demo pemasangan close-up",
            "cta": "klik keranjang", "variant_count": 3, "test_variable": "hook",
        }

    def test_normalizer_clamps_variants_and_rejects_unknown_enums(self):
        brief = normalize_conversion_brief({"enabled": True, "variant_count": 99, "hook_type": "magic", "objective": "viral"})
        self.assertEqual(brief["variant_count"], 5)
        self.assertEqual(brief["hook_type"], "problem")
        self.assertEqual(brief["objective"], "product_click")

    def test_complete_brief_has_no_issues_and_builds_guardrails(self):
        brief = normalize_conversion_brief(self.complete_brief())
        self.assertEqual(conversion_brief_issues(brief), [])
        prompt = build_conversion_prompt(brief)
        self.assertIn("Hook → Problem → Solution → Proof → CTA", prompt)
        self.assertIn("ubah HANYA `hook`", prompt)
        self.assertIn("urgensi palsu", prompt)

    def test_missing_proof_and_cta_are_blocking_issues(self):
        brief = normalize_conversion_brief({"enabled": True, "audience": "ibu muda", "hook": "Stop", "problem": "sibuk", "solution": "praktis"})
        issues = " ".join(conversion_brief_issues(brief))
        self.assertIn("proof", issues)
        self.assertIn("CTA", issues)

    def test_funnel_metrics_use_correct_denominators(self):
        result = calculate_funnel_metrics({"impressions": 1000, "three_second_views": 600, "completed_views": 300, "clicks": 50, "purchases": 10, "spend": 200, "revenue": 500})
        self.assertEqual(result, {"hook_rate": 60.0, "hold_rate": 50.0, "ctr": 5.0, "cvr": 20.0, "roas": 2.5})

    def test_zero_denominators_return_unknown_not_fake_zero(self):
        result = calculate_funnel_metrics({})
        self.assertTrue(all(value is None for value in result.values()))


if __name__ == "__main__":
    unittest.main()
