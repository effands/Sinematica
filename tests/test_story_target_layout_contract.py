import unittest
from pathlib import Path


class StoryTargetLayoutContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
        cls.css = (root / "frontend" / "style.css").read_text(encoding="utf-8")

    def test_affiliate_and_aspect_are_moved_into_same_row(self):
        self.assertIn("affiliate-aspect-row", self.js)
        self.assertIn("primaryRow.append(affiliateGroup, aspectGroup)", self.js)
        self.assertIn("grid-template-columns:minmax(0,1fr) minmax(0,1fr)", self.css)
        self.assertIn("min-height:44px;padding:0 14px!important", self.css)
        self.assertIn(":has(#chkAffiliateMode:checked)", self.css)


if __name__ == "__main__":
    unittest.main()
