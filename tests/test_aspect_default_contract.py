import unittest
from pathlib import Path


class AspectDefaultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
        cls.js = (root / "frontend" / "app.js").read_text(encoding="utf-8")

    def test_header_and_default_checkbox_are_removed(self):
        self.assertNotIn('id="aspectDefaultCheckbox"', self.html)
        self.assertNotIn("aspect-default-option", self.html)
        self.assertIn('aria-label="Aspect ratio video"', self.html)

    def test_portrait_is_the_fixed_initial_default(self):
        self.assertIn('<option value="portrait" selected>', self.html)
        self.assertIn("select.value = 'portrait'", self.js)
        self.assertIn("localStorage.removeItem('sinematica_default_aspect_ratio')", self.js)


if __name__ == "__main__":
    unittest.main()
