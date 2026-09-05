import ast
import unittest
from pathlib import Path


class StoryboardSceneCountTests(unittest.TestCase):
    def test_ugc_mode_does_not_randomize_requested_scene_count(self):
        source_path = Path(__file__).resolve().parents[1] / "backend" / "gemini_storyboard.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        random_choice_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "random"
            and node.func.attr == "choice"
        ]

        self.assertIn("WAJIB TEPAT {scene_count} Scene", source)
        self.assertIn("actual_scene_count != target_scene_count", source)

    def test_extend_storyboard_scenes_reaches_target_count(self):
        from backend.gemini_storyboard import _extend_storyboard_scenes
        import json
        from backend.text_generation import ProviderResult

        initial_storyboard = {
            "film_title": "Legenda Pendekar Bayangan",
            "characters": [{"name": "Arga", "seed": 100001, "visual_description": "Pendekar pedang"}],
            "scenes": [
                {
                    "scene_number": i,
                    "title": f"Adegan {i}",
                    "action_summary": f"Aksi {i}",
                    "prompt_for_flow": f"Prompt {i}",
                    "duration": 10,
                }
                for i in range(1, 31)
            ]
        }

        # Mock generator returning remaining 20 scenes (31 to 50)
        def mock_generator(prompt, json_output=True):
            continuation_scenes = [
                {
                    "scene_number": i,
                    "title": f"Adegan {i}",
                    "action_summary": f"Aksi {i}",
                    "prompt_for_flow": f"Prompt {i}",
                    "duration": 10,
                }
                for i in range(31, 51)
            ]
            return ProviderResult(
                text=json.dumps({"scenes": continuation_scenes}),
                provider="mock_gemini",
                model="gemini-2.5-flash",
            )

        completed = _extend_storyboard_scenes(
            storyboard=initial_storyboard,
            target_count=50,
            premise="Perjalanan balas dendam pendekar",
            target_lang="Indonesia",
            seed=100001,
            generator=mock_generator,
        )

        self.assertEqual(len(completed["scenes"]), 50)
        self.assertEqual(completed["scenes"][0]["scene_number"], 1)
        self.assertEqual(completed["scenes"][-1]["scene_number"], 50)
        self.assertEqual(completed["scenes"][-1]["time_range"], "8:10–8:20")
        required_editor_fields = {
            "scene_purpose", "activity", "expression", "visual_composition",
            "transition_bridge", "shot_type", "camera_movement", "narration_id",
            "text_overlay", "shot_flow",
        }
        for scene in completed["scenes"]:
            self.assertTrue(required_editor_fields.issubset(scene))
            self.assertTrue(all(scene[field] for field in required_editor_fields))

    def test_continuation_prompt_requires_complete_editor_schema(self):
        from backend.gemini_storyboard import _extend_storyboard_scenes

        captured = []

        class Result:
            text = '{"scenes":[{"title":"Dua","action_summary":"Berjalan","prompt_for_flow":"Prompt","duration":10}]}'

        def generator(prompt, json_output=True):
            captured.append(prompt)
            return Result()

        _extend_storyboard_scenes(
            {"film_title": "Tes", "scenes": [{"title": "Satu", "action_summary": "Diam", "prompt_for_flow": "Prompt", "duration": 10}]},
            2,
            "Tes",
            generator=generator,
        )
        for field in ("scene_purpose", "expression", "visual_composition", "transition_bridge", "narration_id", "text_overlay"):
            self.assertIn(field, captured[0])

    def test_generate_storyboard_returns_only_requested_longform_part(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        def mock_generate_text(prompt, json_output=True):
            scenes = [
                {
                    "scene_number": i,
                    "title": f"Adegan {i}",
                    "action_summary": f"Aksi {i}",
                    "prompt_for_flow": f"Prompt {i}",
                    "duration": 10,
                }
                for i in range(1, 16)
            ]
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Film Epik",
                    "characters": [{"name": "Budi", "seed": 100002, "visual_description": "Aktor"}],
                    "scenes": scenes,
                }),
                provider="mock_gemini",
                model="gemini-2.5-flash",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text):
            result = generate_storyboard(
                premise="Kisah perjalanan epik petualang di rimba misterius",
                scene_count=15,
                story_total_scene_count=51,
                story_scene_offset=15,
                story_part_number=2,
                previous_part_context={"last_scenes": [{"scene_number": 15, "end_state": "Di gerbang hutan"}]},
            )
            self.assertEqual(len(result["scenes"]), 15)
            self.assertEqual(result["scenes"][0]["scene_number"], 16)
            self.assertEqual(result["scenes"][-1]["scene_number"], 30)
            self.assertEqual(result["story_parts"]["total_scene_count"], 51)
            self.assertTrue(result["story_parts"]["has_next_part"])

    def test_complete_drama_without_conflict_climax_or_ending_is_rejected_before_render(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        scenes = [
            {
                "scene_number": i,
                "title": f"Hari Tenang {i}",
                "scene_purpose": "Suasana harian",
                "activity": "Tokoh berjalan pelan dan melihat ruangan",
                "action_summary": "Tokoh mengamati suasana tanpa perubahan cerita",
                "transition_bridge": "Tatapan berpindah ke ruangan berikutnya",
                "prompt_for_flow": "A 10-second medium shot of a person quietly walking in a room.",
                "duration": 10,
            }
            for i in range(1, 21)
        ]

        def mock_generate_text(prompt, json_output=True):
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Drama Datar",
                    "characters": [{"name": "Rian", "seed": 100001, "description": "Pria dewasa"}],
                    "scenes": scenes,
                }),
                provider="mock",
                model="mock",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text), \
             patch("backend.gemini_storyboard._call_web2api", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "kualitas cerita belum cukup menarik|alur terlalu datar"):
                generate_storyboard(
                    premise="Drama keluarga 20 scene",
                    scene_count=20,
                    fixed_scene_duration=10,
                )

    def test_weak_storyboard_is_repaired_before_render_when_repair_passes(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        weak_scenes = [
            {
                "scene_number": i,
                "title": f"Hari Tenang {i}",
                "scene_purpose": "Suasana harian",
                "activity": "Tokoh berjalan pelan dan melihat ruangan",
                "action_summary": "Tokoh mengamati suasana tanpa perubahan cerita",
                "transition_bridge": "Tatapan berpindah ke ruangan berikutnya",
                "prompt_for_flow": "A 10-second medium shot of a person quietly walking in a room.",
                "duration": 10,
            }
            for i in range(1, 13)
        ]
        repaired_scenes = []
        for i in range(1, 13):
            if i <= 3:
                beat = "Hook rahasia keluarga: Rian menemukan bukti warisan dan tujuan Clara mulai terancam."
            elif i <= 7:
                beat = "Konflik meningkat; tuduhan, tekanan, dan keputusan sulit memaksa Rian melawan."
            elif i <= 10:
                beat = "Klimaks konfrontasi: rahasia terbongkar dan pilihan terakhir menentukan nasib keluarga."
            else:
                beat = "Resolusi ending: akibat keputusan diterima, kebenaran terjawab, dan keluarga mendapat keadilan."
            repaired_scenes.append({
                "scene_number": i,
                "title": f"Repair {i}",
                "scene_purpose": beat,
                "activity": beat,
                "action_summary": beat,
                "transition_bridge": beat,
                "prompt_for_flow": f"A 10-second dramatic shot. {beat}",
                "duration": 10,
            })

        calls = []

        def mock_generate_text(prompt, json_output=True):
            calls.append(prompt)
            scenes = repaired_scenes if "script doctor" in prompt else weak_scenes
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Drama Diperbaiki",
                    "characters": [{"name": "Rian", "seed": 100001, "description": "Pria dewasa"}],
                    "scenes": scenes,
                }),
                provider="mock",
                model="mock",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text):
            result = generate_storyboard(
                premise="Drama keluarga yang perlu diperkuat",
                scene_count=12,
                fixed_scene_duration=10,
            )
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(result["story_engagement_audit"]["status"], "passed")
        self.assertEqual(result["dramatic_arc_audit"]["status"], "passed")

    def test_complete_drama_with_clear_arc_passes_dramatic_audit(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        scenes = []
        for i in range(1, 21):
            if i <= 4:
                beat = "Keluarga membangun rutinitas, tetapi rahasia warisan mulai terasa."
            elif i <= 8:
                beat = "Konflik dimulai saat bukti pengkhianatan dan tuduhan muncul."
            elif i <= 14:
                beat = "Tekanan semakin meningkat, pilihan sulit dan konsekuensi memburuk."
            elif i <= 18:
                beat = "Klimaks konfrontasi: rahasia terbongkar dan keputusan terakhir menentukan nasib keluarga."
            else:
                beat = "Resolusi ending sedih bahagia: akibat keputusan diterima dan keadilan tercapai."
            scenes.append({
                "scene_number": i,
                "title": f"Beat Drama {i}",
                "scene_purpose": beat,
                "activity": beat,
                "action_summary": beat,
                "transition_bridge": beat,
                "prompt_for_flow": f"A 10-second dramatic shot. {beat}",
                "duration": 10,
            })

        def mock_generate_text(prompt, json_output=True):
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Drama Berkurva",
                    "characters": [{"name": "Rian", "seed": 100001, "description": "Pria dewasa"}],
                    "scenes": scenes,
                }),
                provider="mock",
                model="mock",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text):
            result = generate_storyboard(
                premise="Drama keluarga 20 scene dengan konflik",
                scene_count=20,
                fixed_scene_duration=10,
            )
        self.assertEqual(result["dramatic_arc_audit"]["status"], "passed")
        self.assertEqual(result["story_engagement_audit"]["status"], "passed")
        self.assertEqual(len(result["scenes"]), 20)

    def test_repetitive_passive_story_is_rejected_by_engagement_audit(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        scenes = []
        for i in range(1, 13):
            scenes.append({
                "scene_number": i,
                "title": f"Ruangan {i}",
                "scene_purpose": "Mood",
                "activity": "Tokoh berjalan pelan dan melihat ruangan",
                "action_summary": "Tokoh mengamati suasana tanpa perubahan cerita",
                "transition_bridge": "Ia menatap kejauhan",
                "prompt_for_flow": "A 10-second shot of a person quietly walking and looking around.",
                "duration": 10,
            })

        def mock_generate_text(prompt, json_output=True):
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Observasi Kosong",
                    "characters": [{"name": "Rian", "seed": 100001, "description": "Pria dewasa"}],
                    "scenes": scenes,
                }),
                provider="mock",
                model="mock",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text), \
             patch("backend.gemini_storyboard._call_web2api", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "kualitas cerita belum cukup menarik"):
                generate_storyboard(
                    premise="Film suasana rumah",
                    scene_count=12,
                    fixed_scene_duration=10,
                )

    def test_children_story_still_needs_curiosity_attempt_and_payoff(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        scenes = [
            {
                "scene_number": i,
                "title": f"Belajar {i}",
                "scene_purpose": "Anak penasaran lalu belajar bersama",
                "activity": "Karakter mencoba menyusun kartu warna bersama teman",
                "action_summary": "Karakter mencoba, belajar, lalu berhasil menolong teman menyusun kartu warna",
                "transition_bridge": "Mereka melihat kartu berikutnya dengan penasaran",
                "prompt_for_flow": "A gentle 10-second cartoon scene where friends try, learn, help, and celebrate.",
                "duration": 10,
            }
            for i in range(1, 7)
        ]
        scenes[-1]["scene_purpose"] = "Payoff pelajaran dan perayaan kecil"
        scenes[-1]["action_summary"] = "Akhir cerita: mereka berhasil, belajar bergantian, dan merayakan bersama."

        def mock_generate_text(prompt, json_output=True):
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Kartu Warna",
                    "characters": [{"name": "Lumi", "seed": 100001, "description": "Tokoh kartun"}],
                    "scenes": scenes,
                }),
                provider="mock",
                model="mock",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text):
            result = generate_storyboard(
                premise="Belajar warna untuk anak",
                scene_count=6,
                fixed_scene_duration=10,
                children_mode=True,
            )
        self.assertEqual(result["story_engagement_audit"]["status"], "passed")

    def test_accidental_tiny_tail_is_collapsed_to_complete_story(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        scenes = []
        for i in range(1, 16):
            if i <= 4:
                beat = "Hook rahasia: Maya menemukan bukti ancaman dan utang tersembunyi."
            elif i <= 9:
                beat = "Konflik meningkat; tuduhan, tekanan, keputusan, dan konsekuensi memburuk."
            elif i <= 13:
                beat = "Klimaks konfrontasi: pengakuan terbongkar dan pilihan terakhir menentukan keluarga."
            else:
                beat = "Resolusi ending: akibat diterima, kebenaran terjawab, dan pasangan menemukan keadilan."
            scenes.append({
                "scene_number": i,
                "title": f"Beat {i}",
                "scene_purpose": beat,
                "activity": beat,
                "action_summary": beat,
                "transition_bridge": beat,
                "prompt_for_flow": beat,
                "duration": 10,
            })

        def mock_generate_text(prompt, json_output=True):
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Dua Sisi Kemewahan",
                    "characters": [{"name": "Maya", "seed": 100001, "description": "Istri"}],
                    "creative_brief": {"result": "Storyboard video portrait, 16 scene, sekitar 160 detik"},
                    "scenes": scenes,
                }),
                provider="mock",
                model="mock",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text):
            result = generate_storyboard(
                premise="Drama keluarga tentang utang rahasia",
                scene_count=15,
                story_total_scene_count=16,
                fixed_scene_duration=10,
            )
        self.assertEqual(len(result["scenes"]), 15)
        self.assertEqual(result["story_parts"]["total_scene_count"], 15)
        self.assertFalse(result["story_parts"]["has_next_part"])
        self.assertEqual(result["dramatic_arc_audit"]["status"], "passed")

    def test_incomplete_longform_part_rejects_fake_final_ending(self):
        from unittest.mock import patch
        from backend.gemini_storyboard import generate_storyboard
        import json
        from backend.text_generation import ProviderResult

        scenes = []
        for i in range(1, 21):
            beat = "Tekanan meningkat; rahasia dan bukti memaksa keluarga mengambil keputusan."
            if i == 20:
                beat = "Resolusi ending: semua konflik selesai, mereka berdamai, dan keluarga bahagia."
            scenes.append({
                "scene_number": i,
                "title": f"Part Beat {i}",
                "scene_purpose": beat,
                "activity": beat,
                "action_summary": beat,
                "transition_bridge": beat,
                "prompt_for_flow": beat,
                "duration": 10,
            })

        def mock_generate_text(prompt, json_output=True):
            return ProviderResult(
                text=json.dumps({
                    "film_title": "Drama Panjang",
                    "characters": [{"name": "Rian", "seed": 100001, "description": "Suami"}],
                    "scenes": scenes,
                }),
                provider="mock",
                model="mock",
            )

        with patch("backend.gemini_storyboard.generate_text", side_effect=mock_generate_text), \
             patch("backend.gemini_storyboard._call_web2api", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "part ini masih punya lanjutan|scene terakhir terasa seperti ending"):
                generate_storyboard(
                    premise="Drama keluarga panjang 40 scene",
                    scene_count=20,
                    story_total_scene_count=40,
                    fixed_scene_duration=10,
                )


if __name__ == "__main__":
    unittest.main()
