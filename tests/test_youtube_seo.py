import unittest

from backend.youtube_seo import normalize_seo_titles, theme_hashtags, normalize_youtube_seo_kit


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

    def test_normalize_youtube_seo_kit_extracts_aliases_and_list_tags(self):
        raw = {
            "titles": ["코코의 특별한 목소리 #애니메이션"],
            "description": "코코의 모험 이야기",
            "thumbnailPrompt": "A cute 3D character singing with magical glow, 16:9 aspect ratio",
            "keywords": ["코코", "어린이 애니메이션", "3D 애니", "마법의 노래", "키즈 동화"]
        }
        kit = normalize_youtube_seo_kit(raw, "코코의 특별한 목소리", "코코의 모험")
        self.assertEqual(kit["thumbnail_prompt"], "A cute 3D character singing with magical glow, 16:9 aspect ratio")
        self.assertIn("코코", kit["tags_csv"])
        self.assertIn("어린이 애니메이션", kit["tags_csv"])
        self.assertEqual(len(kit["titles"]), 1)

    def test_normalize_youtube_seo_kit_generates_fallbacks_when_empty(self):
        raw = {
            "titles": [],
            "description": "",
            "thumbnail_prompt": "-",
            "tags": ""
        }
        kit = normalize_youtube_seo_kit(raw, "Warisan Rahasia", "Kisah rahasia keluarga kaya")
        self.assertTrue(len(kit["titles"]) >= 1)
        self.assertTrue(len(kit["thumbnail_prompt"]) > 10)
        self.assertNotEqual(kit["thumbnail_prompt"], "-")
        self.assertIn("Warisan Rahasia", kit["tags_csv"])
        self.assertTrue(len(kit["description"]) > 20)


if __name__ == "__main__":
    unittest.main()

