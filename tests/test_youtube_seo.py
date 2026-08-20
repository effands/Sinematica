import unittest

from backend.youtube_seo import normalize_seo_titles, theme_hashtags


class YouTubeSeoFormattingTests(unittest.TestCase):
    def test_converts_shouting_title_and_appends_theme_hashtags(self):
        titles = normalize_seo_titles(
            ["PERTARUNGAN SUPERMAN VS HULK PALING DAHSYAT"],
            "Pertarungan Superman vs Hulk",
        )
        self.assertEqual(
            titles[0],
            "Pertarungan Superman vs Hulk Paling Dahsyat #Superman #Hulk",
        )

    def test_preserves_existing_hashtags_without_duplicating_them(self):
        titles = normalize_seo_titles(
            ["Pertarungan Superman vs Hulk paling dahsyat #Superman #Hulk"],
            "Superman vs Hulk",
        )
        self.assertEqual(titles[0].count("#Superman"), 1)
        self.assertTrue(titles[0].endswith("#Superman #Hulk"))

    def test_theme_hashtags_ignore_generic_connector_words(self):
        self.assertEqual(
            theme_hashtags("Pertarungan Epik: Superman vs Hulk"),
            ["#Superman", "#Hulk"],
        )


if __name__ == "__main__":
    unittest.main()
