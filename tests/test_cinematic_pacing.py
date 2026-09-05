"""Unit tests for dynamic cinematic pacing, tension waves, and multi-cultural genre archetypes."""

import unittest
from backend.cinematic_pacing import (
    detect_cinematic_archetype,
    calculate_pacing_tier,
    build_dynamic_narrative_rules,
    build_story_part_rules,
    story_phase_for_range,
    CINEMATIC_ARCHETYPES,
)


class CinematicPacingTests(unittest.TestCase):
    def test_detect_preschool_archetype(self):
        arch = detect_cinematic_archetype(is_children=True)
        self.assertEqual(arch["id"], "preschool")
        self.assertIn("100% DILARANG amarah", arch["scene_1_principle"])

        arch2 = detect_cinematic_archetype(premise="Petualangan anak kelinci mencari buah di kebun")
        self.assertEqual(arch2["id"], "preschool")

    def test_detect_elderly_nostalgia_archetype(self):
        arch = detect_cinematic_archetype(premise="Kakek tua membuka album foto usang di rumah kayu")
        self.assertEqual(arch["id"], "elderly_nostalgia")
        self.assertIn("reflektif", arch["scene_1_principle"])
        self.assertIn("teh", arch["scene_1_principle"])

    def test_detect_horror_archetype(self):
        arch = detect_cinematic_archetype(genre="Horror Supernatural", premise="Rumah tua berhantu di tengah hutan")
        self.assertEqual(arch["id"], "horror")
        self.assertIn("DILARANG langsung jumpscare", arch["scene_1_principle"])
        self.assertIn("creeping dread", arch["scene_1_principle"])

    def test_detect_mythology_archetype(self):
        arch = detect_cinematic_archetype(genre="Mitologi", premise="Kutukan dewa laut dan pusaka wayang kuno")
        self.assertEqual(arch["id"], "mythology")
        self.assertIn("pertanda sakral", arch["scene_1_principle"])

    def test_detect_telenovela_archetype(self):
        arch = detect_cinematic_archetype(genre="Telenovela", premise="Perebutan warisan di hacienda mewah")
        self.assertEqual(arch["id"], "telenovela")
        self.assertIn("elegansi", arch["scene_1_principle"])
        self.assertIn("Flamenco", arch["audio_atmosphere"])

    def test_detect_crime_noir_archetype(self):
        arch = detect_cinematic_archetype(genre="Noir Gangster", premise="Detektif menyelidiki berkas rahasia mafia")
        self.assertEqual(arch["id"], "crime_noir")
        self.assertIn("paling pelan", arch["scene_1_principle"])
        self.assertIn("Chiaroscuro", arch["camera_style"])

    def test_detect_scifi_archetype(self):
        arch = detect_cinematic_archetype(genre="Sci-Fi Cyberpunk", premise="Hologram AI di kota masa depan")
        self.assertEqual(arch["id"], "scifi")
        self.assertIn("hologram neon", arch["scene_1_principle"])

    def test_detect_turkish_dizi_archetype(self):
        arch = detect_cinematic_archetype(target_country="Turkey", premise="Keluarga mafia Istanbul di tepi Bosphorus")
        self.assertEqual(arch["id"], "turkish_dizi")
        self.assertIn("Bakışlar", arch["scene_1_principle"])
        self.assertIn("Bağlama", arch["audio_atmosphere"])

    def test_detect_arab_musalsalat_archetype(self):
        arch = detect_cinematic_archetype(target_country="Saudi Arabia", premise="Musalsalat perseteruan dua klan terpandang")
        self.assertEqual(arch["id"], "arab_musalsalat")
        self.assertIn("Sharaf", arch["scene_1_principle"])
        self.assertIn("Gahwa", arch["scene_1_principle"])

    def test_detect_bollywood_archetype(self):
        arch = detect_cinematic_archetype(target_country="India", premise="Pertarungan epik demi sumpah Dharma")
        self.assertEqual(arch["id"], "bollywood")
        self.assertIn("Dharma", arch["scene_1_principle"])
        self.assertIn("Dholak", arch["audio_atmosphere"])

    def test_detect_anime_manga_archetype(self):
        arch = detect_cinematic_archetype(genre="Anime Shonen", premise="Pendekar pedang dengan tekad api")
        self.assertEqual(arch["id"], "anime_manga")
        self.assertIn("Jo-Ha-Kyū", arch["name"])
        self.assertIn("Ma", arch["scene_1_principle"])

    def test_detect_manhwa_archetype(self):
        arch = detect_cinematic_archetype(genre="Manhwa Webtoon", premise="Hunter rank E mengalami awakening misterius")
        self.assertEqual(arch["id"], "manhwa")
        self.assertIn("Aura Dominasi", arch["name"])

    def test_detect_manhua_cultivation_archetype(self):
        arch = detect_cinematic_archetype(genre="Manhua Xianxia", premise="Kultivasi pedang terbang sekte langit")
        self.assertEqual(arch["id"], "manhua")
        self.assertIn("Dao", arch["scene_1_principle"])

    def test_detect_cdrama_palace_vs_duanju(self):
        arch_palace = detect_cinematic_archetype(premise="Intrik selir di istana kaisar dinasti Tang")
        self.assertEqual(arch_palace["id"], "cdrama_palace_xianxia")

        arch_duanju = detect_cinematic_archetype(premise="Pewaris menyamar dihina mertua jahat", is_microdrama=True)
        self.assertEqual(arch_duanju["id"], "cdrama_duanju")

    def test_pacing_tier_calculation(self):
        tier1 = calculate_pacing_tier(3)
        self.assertEqual(tier1["tier"], 1)
        self.assertIn("Fast-Hook", tier1["name"])

        tier2 = calculate_pacing_tier(6)
        self.assertEqual(tier2["tier"], 2)
        self.assertIn("Kishōtenketsu", tier2["name"])
        self.assertIn("DILARANG langsung marah-marah", tier2["description"])

        tier3 = calculate_pacing_tier(12)
        self.assertEqual(tier3["tier"], 3)
        self.assertIn("Full Cinematic", tier3["name"])
        self.assertIn("Tension Waves", tier3["description"])

    def test_build_dynamic_narrative_rules_anti_screaming_rule(self):
        prompt_rules = build_dynamic_narrative_rules(
            scene_count=8,
            genre="Drama Realistis",
            premise="Dua saudara bertemu kembali setelah 10 tahun terpisah",
            target_country="Indonesia",
        )
        self.assertIn("ANTI MARAH-MARAH TANPA ALASAN", prompt_rules)
        self.assertIn("DILARANG KERAS membuka Scene 1 dengan teriakan", prompt_rules)
        self.assertIn("ARKETIPE DRAMA TERDETEKSI", prompt_rules)

    def test_long_story_first_part_is_setup_not_climax(self):
        phase = story_phase_for_range(0, 15, 90)
        self.assertEqual(phase["id"], "setup")
        self.assertFalse(phase["climax_allowed"])
        rules = build_story_part_rules(0, 15, 90, part_number=1)
        self.assertIn("Scene Global 1-15", rules)
        self.assertIn("DILARANG menyelesaikan konflik utama", rules)
        self.assertIn("dilarang membuka dengan makian", rules)

    def test_continuation_part_carries_checkpoint_and_global_range(self):
        rules = build_story_part_rules(
            15, 15, 50, part_number=2,
            previous_context={"last_scenes": [{"scene_number": 15, "end_state": "Surat masih tertutup"}]},
        )
        self.assertIn("Scene Global 16-30", rules)
        self.assertIn("Surat masih tertutup", rules)


if __name__ == "__main__":
    unittest.main()
