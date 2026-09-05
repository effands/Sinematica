import unittest

from backend.scene_pacing import (
    densify_flow_prompt,
    has_dialogue,
    rewrite_dense_prompt_with_ai,
    should_try_gemini_storyboard_image,
)
from backend.scene_direction import enforce_spoken_language_lock


class DenseScenePromptTests(unittest.TestCase):
    def test_ten_second_emotional_dialogue_scene_gets_three_timed_beats(self):
        result = densify_flow_prompt(
            'A 10-second shot. Raka speaking angrily: "Kembalikan surat itu!"',
            {"action_summary": "Raka confronts Bambang"},
            10,
        )

        self.assertIn("0-3.3 seconds", result)
        self.assertIn("3.3-6.6 seconds", result)
        self.assertIn("6.6-10 seconds", result)
        self.assertIn("do not invent a second line", result)
        self.assertIn("one main action and at most two supporting actions", result)
        self.assertNotIn("No static hold may last longer than 0.5 seconds", result)
        self.assertNotIn("at least two distinct short speaking turns", result)

    def test_non_ten_second_prompt_is_not_changed(self):
        prompt = "A 6-second tracking shot."
        self.assertEqual(densify_flow_prompt(prompt, {}, 6), prompt)

    def test_deepseek_primary_skips_slow_gemini_image_attempt(self):
        self.assertFalse(should_try_gemini_storyboard_image({"default_text_provider": "deepseek"}))
        self.assertTrue(should_try_gemini_storyboard_image({"default_text_provider": "gemini"}))

    def test_detects_single_quoted_spoken_line(self):
        self.assertTrue(has_dialogue({}, "Arif shouts in Indonesian: 'Bank menolak!'"))

    def test_ai_rewrite_must_produce_specific_timed_actions_and_two_dialogue_turns(self):
        calls = []

        class Result:
            provider = "deepseek"
            text = (
                '{"prompt_for_flow":"OPENING STATE: Arif stands screen-left facing Sinta, phone in his right hand. '
                'A 10-second three-shot sequence. 0-3.3 seconds: WIDE ANGLE, Arif slams '
                'the phone and shouts \\"Bank menolak!\\" 3.3-6.6 seconds: OTS SHOT, Sinta pushes a contract '
                'and replies \\"Tandatangani ini.\\" 6.6-10 seconds: CLOSE-UP, Arif signs and exits. '
                'FINAL CONTINUITY FRAME: Sinta remains at the desk watching Arif leave through the door."}'
            )

        def generator(request, json_output=False):
            calls.append((request, json_output))
            return Result()

        rewritten, provider = rewrite_dense_prompt_with_ai(
            "A 10-second shot. Arif shouts in Indonesian: 'Bank menolak!'",
            {"title": "Krisis di Kantor", "action_summary": "Arif receives a contract", "dialogue": [
                {"speaker_id": 1, "line": "Bank menolak!"},
                {"speaker_id": 2, "line": "Tandatangani ini."},
            ]},
            10,
            children_mode=False,
            generator=generator,
        )

        self.assertEqual(provider, "deepseek")
        self.assertIn("0-3.3 seconds", rewritten)
        self.assertIn("3.3-6.6 seconds", rewritten)
        self.assertIn("6.6-10 seconds", rewritten)
        self.assertIn('"Tandatangani ini."', rewritten)
        self.assertIn("ONLY spoken lines", calls[0][0])
        self.assertIn("THREE SHOTS", calls[0][0])
        self.assertIn("SAME location and SAME continuous time window", calls[0][0])
        self.assertIn("OPENING STATE", calls[0][0])
        self.assertIn("FINAL CONTINUITY FRAME", calls[0][0])
        self.assertIn("never looks into camera", calls[0][0])
        self.assertIn("no subtitles, captions", calls[0][0].lower())
        self.assertNotIn("one continuous scene/location", calls[0][0])
        self.assertTrue(calls[0][1])

    def test_japanese_canonical_dialogue_replaces_invented_english(self):
        scene = {"dialogue": [
            {"speaker_id": 1, "line": "なぜ、ここに？"},
            {"speaker_id": 2, "line": "選択を変える覚悟はあるか。"},
        ]}
        prompt = 'Sota asks, "Why are you here?" Ren replies, "Are you ready?"'
        locked = enforce_spoken_language_lock(prompt, scene, "Jepang")
        self.assertNotIn("Why are you here", locked)
        self.assertNotIn("Are you ready", locked)
        self.assertIn('"なぜ、ここに？"', locked)
        self.assertIn('"選択を変える覚悟はあるか。"', locked)
        self.assertIn("natural Jepang only", locked)

    def test_ai_rewrite_with_english_translation_is_rejected_to_local_guard(self):
        class Result:
            provider = "test"
            text = '{"prompt_for_flow":"0-3.3 seconds: WIDE, Sota says \\"Why?\\" 3.3-6.6 seconds: OTS action. 6.6-10 seconds: CLOSE-UP action."}'

        rewritten, provider = rewrite_dense_prompt_with_ai(
            'Sota says "なぜ？"',
            {"dialogue": [{"speaker_id": 1, "line": "なぜ？"}]},
            10,
            target_lang="Jepang",
            generator=lambda *_args, **_kwargs: Result(),
        )
        self.assertEqual(provider, "local-guard")
        self.assertNotIn("Why?", rewritten)
        self.assertIn("なぜ？", rewritten)

    def test_previous_scene_is_supplied_as_location_continuity_context(self):
        calls = []

        def generator(request, json_output=False):
            calls.append(request)
            raise RuntimeError("use local guard")

        rewrite_dense_prompt_with_ai(
            "Sari opens the archive door.",
            {
                "title": "Ruang Arsip",
                "previous_scene_title": "Koridor Kantor",
                "previous_scene_action": "Sari berjalan menuju pintu ruang arsip.",
                "previous_scene_prompt": "Sari stops outside the archive door.",
                "previous_scene_end_state": "Sari's right hand grips the archive-door handle.",
            },
            10,
            generator=generator,
        )

        self.assertIn("Previous 10-second video", calls[0])
        self.assertIn("right hand grips the archive-door handle", calls[0])
        self.assertIn("instead of\nteleporting", calls[0])

    def test_local_fallback_still_locks_opening_props_eyeline_and_final_frame(self):
        result = densify_flow_prompt("Sari examines a ring.", {}, 10)
        self.assertIn("OPENING STATE:", result)
        self.assertIn("prop parts unambiguously", result)
        self.assertIn("never use an ambiguous 'look forward'", result)
        self.assertIn("No subtitles, captions", result)
        self.assertIn("FINAL CONTINUITY FRAME:", result)


if __name__ == "__main__":
    unittest.main()
