import unittest

from backend.scene_audio_direction import (
    apply_scene_audio_direction,
    resolve_master_music_track,
)


class SceneAudioDirectionTests(unittest.TestCase):
    def test_chinese_battle_scene_gets_subtle_continuous_thematic_score(self):
        result = apply_scene_audio_direction(
            "Armies clash at the palace gate.",
            {"title": "Perang Istana", "action_summary": "Pasukan menyerbu gerbang"},
            {"genre_style": "Drama China kerajaan"},
        )

        self.assertIn("low-volume", result)
        self.assertIn("continuous throughout the entire clip", result)
        self.assertIn("Chinese cinematic orchestra", result)
        self.assertIn("restrained war percussion", result)
        self.assertIn("dialogue remains clearly audible", result)

    def test_music_video_forbids_singing_and_lip_sync(self):
        result = apply_scene_audio_direction(
            "A woman walks through rain.",
            {"title": "Rain"},
            {"genre_style": "Cinematic Music Video"},
            music_video=True,
        )

        self.assertIn("never sings", result)
        self.assertIn("no lip-sync", result)
        self.assertIn("mouth movements must not follow lyrics", result)

    def test_storyboard_music_track_wins_over_unrelated_settings_value(self):
        result = resolve_master_music_track(
            {"music_track_path": "uploads/song.mp3"},
            {"music_track_path": "settings/old.mp3"},
        )

        self.assertEqual(result, "uploads/song.mp3")


if __name__ == "__main__":
    unittest.main()
