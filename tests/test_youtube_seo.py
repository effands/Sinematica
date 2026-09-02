import unittest

from backend.youtube_seo import normalize_seo_titles, theme_hashtags, normalize_hashtags, normalize_youtube_seo_kit, storyboard_to_seo_context
from backend.gallery_metadata import gallery_metadata


class YouTubeSeoFormattingTests(unittest.TestCase):
    def test_storyboard_context_contains_characters_dialogue_and_payoff(self):
        context = storyboard_to_seo_context({
            "film_title": "Lumi dan Benih Terakhir",
            "premise": "Lumi belajar sabar menanam benih.",
            "characters": [{"name": "Lumi", "description": "anak kapibara yang teliti"}],
            "scenes": [{
                "scene_number": 1,
                "title": "Tunas Muncul",
                "action_summary": "Lumi menyiram pot lalu melihat tunas.",
                "dialogue": [{"line": "Ternyata tumbuh perlu waktu!"}],
                "end_state": "Lumi tersenyum di samping tunas hijau.",
            }],
        })
        self.assertIn("Lumi: anak kapibara", context)
        self.assertIn("Ternyata tumbuh perlu waktu!", context)
        self.assertIn("Lumi tersenyum di samping tunas hijau", context)

    def test_legacy_korean_job_recovers_localization_from_scenes(self):
        metadata = gallery_metadata({
            "title": "황금 차원의 충돌",
            "scenes": [{"title": "격돌의 시작", "prompt": "한국 도시에서 영웅들이 만난다."}],
        })
        self.assertEqual(metadata["target_lang"], "Korea")
        self.assertEqual(metadata["target_country"], "South Korea")

    def test_converts_shouting_title_and_removes_title_hashtags(self):
        titles = normalize_seo_titles(
            ["PERTARUNGAN SUPERMAN VS HULK PALING DAHSYAT"],
            "Pertarungan Superman vs Hulk",
        )
        self.assertEqual(
            titles[0],
            "Pertarungan Superman vs Hulk Paling Dahsyat",
        )

    def test_keeps_title_hashtags_within_youtube_character_limit(self):
        titles = normalize_seo_titles(
            ["Pertarungan Superman vs Hulk paling dahsyat #Superman #Hulk"],
            "Superman vs Hulk",
        )
        self.assertIn("#Superman", titles[0])
        self.assertLessEqual(len(titles[0]), 100)

    def test_hashtags_are_deduplicated_and_limited_to_three(self):
        tags = normalize_hashtags(
            {"hashtags": ["#Momo", "Momo", "#CeritaAnak", "#BelajarAgama"]},
            "Momo Belajar Agama",
        )
        self.assertEqual(tags, ["#Momo", "#CeritaAnak", "#BelajarAgama"])

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

    def test_portrait_video_forces_portrait_thumbnail_prompt(self):
        kit = normalize_youtube_seo_kit(
            {"thumbnail_prompt": "Bright YouTube thumbnail, 16:9 format"},
            "Belajar Warna",
            "Dua sahabat mengenal warna",
            aspect_ratio="portrait",
        )
        self.assertIn("9:16", kit["thumbnail_prompt"])
        self.assertNotIn("16:9", kit["thumbnail_prompt"])
        self.assertEqual(kit["thumbnail_aspect_ratio"], "9:16")


if __name__ == "__main__":
    unittest.main()
