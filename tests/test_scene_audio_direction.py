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
        self.assertIn("AUDIO REALISM BLUEPRINT (FIVE LAYERS)", result)
        self.assertIn("AMBIENCE", result)
        self.assertIn("FOLEY/SFX", result)
        self.assertIn("MIX/MASTER", result)

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

    def test_dialogue_gets_natural_human_conversation_direction(self):
        result = apply_scene_audio_direction(
            "Maya answers her mother.",
            {
                "title": "Percakapan Dapur",
                "dialogue": [
                    {"speaker_id": 1, "line": "Bu, aku pulang agak malam."},
                    {"speaker_id": 2, "line": "Kabarin dulu, ya."},
                ],
            },
            {"genre_style": "Drama keluarga"},
        )

        self.assertIn("real conversation captured on location", result)
        self.assertIn("native, everyday speaking voice", result)
        self.assertIn("subtle breaths", result)
        self.assertIn("without adding, removing, or changing", result)
        self.assertIn("robotic rhythm", result)
        self.assertIn("non-mechanical lip-sync", result)

    def test_silent_scene_does_not_add_dialogue_performance(self):
        result = apply_scene_audio_direction(
            "Maya silently opens the letter.",
            {"title": "Surat"},
            {"genre_style": "Drama keluarga"},
        )

        self.assertNotIn("DIALOGUE PERFORMANCE", result)

    def test_raw_amateur_uses_live_phone_ambience_without_cinematic_score(self):
        result = apply_scene_audio_direction(
            "A student searches her bag.",
            {"dialogue": [{"speaker_id": 1, "line": "Aduh, ketinggalan lagi."}]},
            {"ugc_variant": "raw_amateur"},
        )

        self.assertIn("RAW AMATEUR SMARTPHONE", result)
        self.assertIn("casual background conversation", result)
        self.assertIn("phone-microphone perspective", result)
        self.assertNotIn("cinematic underscore continuous", result)

    def test_visible_actions_receive_synchronized_foley_cues(self):
        result = apply_scene_audio_direction(
            "Maya opens the car door and gets inside.",
            {"action_summary": "Maya membuka pintu mobil lalu masuk"},
            {},
        )
        self.assertIn("handle click", result)
        self.assertIn("exact visible contact frame", result)

    def test_explicit_audio_blueprint_survives_into_render_prompt(self):
        result = apply_scene_audio_direction(
            "A tense kitchen conversation.",
            {"audio_blueprint": {
                "voice_performance": "restrained anger, slower on the final word",
                "ambience": "old refrigerator hum and distant neighborhood traffic",
                "foley_sfx": "cup touches table exactly as her fingers release it",
                "music": "none",
                "mix": "dialogue foreground with natural kitchen reflections",
            }},
            {},
        )
        self.assertIn("old refrigerator hum", result)
        self.assertIn("cup touches table", result)
        self.assertIn("restrained anger", result)

    def test_explicit_music_replaces_inferred_scene_music_to_avoid_conflict(self):
        result = apply_scene_audio_direction(
            "A battle survivor reveals the hidden ring.",
            {
                "title": "War Reveal",
                "audio_blueprint": {"music": "one continuous low bass drone"},
            },
            {},
        )
        self.assertIn("Follow the authored scene music exactly: one continuous low bass drone", result)
        self.assertNotIn("orchestral palette", result)
        self.assertNotIn("restrained war percussion", result)

    def test_storyboard_music_track_wins_over_unrelated_settings_value(self):
        result = resolve_master_music_track(
            {"music_track_path": "uploads/song.mp3"},
            {"music_track_path": "settings/old.mp3"},
        )

        self.assertEqual(result, "uploads/song.mp3")

    def test_character_voice_lock_preserves_voice_timbre_across_scenes(self):
        storyboard = {
            "characters": [
                {
                    "id": 1,
                    "name": "Boma",
                    "vocal_signature": "Warm baritone, 28yo male, steady calm cadence",
                }
            ]
        }
        scene = {
            "dialogue": [{"speaker_id": 1, "line": "Kita harus segera berangkat sekarang."}],
        }
        result = apply_scene_audio_direction("Boma berbicara di depan rumah.", scene, storyboard)
        self.assertIn("VOICE IDENTITY LOCK (Boma)", result)
        self.assertIn("Warm baritone, 28yo male, steady calm cadence", result)
        self.assertIn("allowing pitch", result)
        self.assertIn("Never freeze intonation", result)
        self.assertNotIn("Maintain this exact vocal pitch", result)

    def test_wardrobe_and_forward_do_not_trigger_war_score(self):
        result = apply_scene_audio_direction('', {'prompt_for_flow': 'Same wardrobe, step forward.'}, {})
        self.assertNotIn('war percussion', result)

    def test_explicit_no_music_does_not_request_continuous_underscore(self):
        result = apply_scene_audio_direction('', {'audio_blueprint': {'music': 'none'}}, {})
        self.assertNotIn('underscore continuous', result)
        self.assertNotIn('orchestral palette', result)


if __name__ == "__main__":
    unittest.main()
