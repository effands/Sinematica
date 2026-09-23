import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import json

from run_e2e_pipeline import (
    E2EPipelineRunner,
    GENRE_CATALOG_PRESETS,
    check_and_wait_for_extension_fleet,
    check_server_health,
    ensure_backend_server,
)


def test_genre_catalog_presets_structure():
    assert len(GENRE_CATALOG_PRESETS) >= 5
    for preset in GENRE_CATALOG_PRESETS:
        assert "category" in preset
        assert "genre" in preset
        assert "theme" in preset
        assert preset.get("country") == "Indonesia"
        assert preset.get("language") == "Indonesia"


def test_check_server_health():
    with patch("run_e2e_pipeline.http_get") as mock_get:
        mock_get.return_value = (200, {"state": "ready", "extension_connected": True})
        assert check_server_health("http://127.0.0.1:8888") is True

        mock_get.return_value = (0, None)
        assert check_server_health("http://127.0.0.1:8888") is False


def test_ensure_backend_server_already_running():
    with patch("run_e2e_pipeline.check_server_health", return_value=True):
        proc = ensure_backend_server("http://127.0.0.1:8888", port=8888)
        assert proc is None


def test_ensure_backend_server_starts_process():
    with patch("run_e2e_pipeline.check_server_health") as mock_health, \
         patch("subprocess.Popen") as mock_popen:
        mock_health.side_effect = [False, True]
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        proc = ensure_backend_server("http://127.0.0.1:8888", port=8888, timeout=2.0)
        assert proc is mock_proc
        assert mock_popen.called


def test_e2e_pipeline_step_1_and_2():
    async def _run():
        runner = E2EPipelineRunner(
            scene_count=2,
            duration=10,
            aspect_ratio="portrait",
            target_country="Indonesia",
            target_lang="Indonesia",
            selected_preset=GENRE_CATALOG_PRESETS[0],
        )

        with patch("run_e2e_pipeline.auto_suggest_details") as mock_suggest:
            mock_suggest.return_value = {
                "suggested_title": "Rahasia Sang Direktur Magang",
                "suggested_premise": "Direktur Utama menyamar sebagai karyawan magang untuk menyelidiki kecurangan.",
                "suggested_characters": "Reza Rahardian, Anya Geraldine",
            }

            concept = await runner.step_1_trend_and_concept()
            assert concept["title"] == "Rahasia Sang Direktur Magang"
            assert "Direktur" in concept["premise"]

        with patch("run_e2e_pipeline.generate_storyboard") as mock_sb:
            mock_sb.return_value = {
                "film_title": "Rahasia Sang Direktur Magang",
                "premise": "Direktur Utama menyamar sebagai karyawan magang.",
                "aspect_ratio": "portrait",
                "characters": [
                    {"name": "Reza", "seed": 123456, "wardrobe": "Kemeja polos"},
                    {"name": "Anya", "seed": 654321, "wardrobe": "Blazer kerja"},
                ],
                "scenes": [
                    {
                        "scene_number": 1,
                        "title": "Adegan 1: Penyamaran Dimulai",
                        "duration": 10,
                        "action_summary": "Reza memasuki lobi kantor dengan pakaian magang.",
                        "prompt_for_flow": "A cinematic shot of a young man walking into an office lobby.",
                    },
                    {
                        "scene_number": 2,
                        "title": "Adegan 2: Pertemuan Tak Terduga",
                        "duration": 10,
                        "action_summary": "Anya menegur Reza di ruang arsip.",
                        "prompt_for_flow": "A cinematic close up of a woman talking to a coworker in an archive room.",
                    },
                ],
            }

            sb = await runner.step_2_generate_storyboard(concept)
            assert sb["film_title"] == "Rahasia Sang Direktur Magang"
            assert len(sb["scenes"]) == 2
            assert sb["scenes"][0]["duration"] == 10
            assert sb["scenes"][1]["duration"] == 10
            assert sb["target_country"] == "Indonesia"
            assert sb["target_lang"] == "Indonesia"

    asyncio.run(_run())


def test_e2e_pipeline_step_3_and_4_payload_and_streaming():
    async def _run():
        runner = E2EPipelineRunner(scene_count=2, duration=10, aspect_ratio="portrait")
        runner.storyboard = {
            "film_title": "Test Film",
            "characters": [{"name": "Hero"}],
            "scenes": [{"scene_number": 1}, {"scene_number": 2}],
        }

        mock_profiles = [
            {"instance_id": "prof-1", "connected": True, "ready": True, "logged_in": True, "project_id": "proj-uuid-1"}
        ]

        captured_payloads = []

        def mock_post(url, payload=None, timeout=10.0):
            if "/api/jobs/create" in url:
                captured_payloads.append(payload)
                return 200, {"success": True, "job_id": "job_test_123"}
            return 404, None

        def mock_get(url, timeout=5.0):
            if "/api/fleet" in url:
                return 200, {"profiles": mock_profiles}
            if "/api/jobs/job_test_123" in url:
                return 200, {
                    "job": {
                        "job_id": "job_test_123",
                        "status": "completed",
                        "title": "Test Film",
                    },
                    "logs": [
                        {"time": "12:00:00", "message": "[6%] Request character seed...", "level": "info"},
                        {"time": "12:00:05", "message": "Proses job selesai secara keseluruhan!", "level": "success"},
                    ]
                }
            return 404, None

        with patch("run_e2e_pipeline.http_post", side_effect=mock_post), \
             patch("run_e2e_pipeline.http_get", side_effect=mock_get):
            status = await runner.step_3_and_4_register_and_execute_job()
            assert status.get("status") == "completed"
            assert runner.job_id == "job_test_123"
            assert len(captured_payloads) == 1

            payload = captured_payloads[0]
            assert "storyboard" in payload
            assert payload["aspect_ratio"] == "portrait"
            assert payload["duration"] == 10
            assert payload["force_uniform_duration"] is True
            assert payload["render_scene_limit"] == 2
            assert payload["flow_project_id"] == "proj-uuid-1"

    asyncio.run(_run())


def test_e2e_pipeline_verification_reporting(tmp_path):
    async def _run():
        runner = E2EPipelineRunner(scene_count=2, duration=10)
        runner.job_id = "job_mock_e2e"

        job_dir = tmp_path / "storage" / "jobs" / "job_mock_e2e"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "storyboard_01.png").write_bytes(b"fake_image_1")
        (job_dir / "storyboard_02.png").write_bytes(b"fake_image_2")
        (job_dir / "scene_01.mp4").write_bytes(b"fake_video_1")
        (job_dir / "scene_02.mp4").write_bytes(b"fake_video_2")
        (job_dir / "cinematic_film.mp4").write_bytes(b"fake_final_video")

        with patch("run_e2e_pipeline.settings.JOBS_DIR", tmp_path / "storage" / "jobs"):
            mock_status = {
                "status": "completed",
                "current_scene": 2,
                "total_scenes": 2,
                "cinematic_film_path": str(job_dir / "cinematic_film.mp4"),
            }
            await runner.step_5_verify_and_report(mock_status)

    asyncio.run(_run())


def test_check_and_wait_for_extension_fleet_already_ready():
    async def _run():
        mock_data = {
            "profiles": [
                {"instance_id": "prof-1", "connected": True, "ready": True, "logged_in": True, "name": "Profile 1"}
            ]
        }

        with patch("run_e2e_pipeline.http_get", return_value=(200, mock_data)):
            profiles = await check_and_wait_for_extension_fleet("http://127.0.0.1:8888", interactive=True)
            assert len(profiles) == 1
            assert profiles[0]["instance_id"] == "prof-1"

    asyncio.run(_run())


def test_check_and_wait_for_extension_fleet_retry_on_enter():
    async def _run():
        empty_data = {"profiles": []}
        ready_data = {
            "profiles": [
                {"instance_id": "prof-2", "connected": True, "ready": True, "logged_in": True}
            ]
        }

        with patch("run_e2e_pipeline.http_get") as mock_get, \
             patch("asyncio.to_thread", new=AsyncMock(return_value="")), \
             patch("asyncio.sleep", new=AsyncMock()):
            mock_get.side_effect = [
                (200, empty_data),
                (200, ready_data),
            ]
            profiles = await check_and_wait_for_extension_fleet("http://127.0.0.1:8888", interactive=True)

            assert len(profiles) == 1
            assert profiles[0]["instance_id"] == "prof-2"

    asyncio.run(_run())


def test_check_and_wait_for_extension_fleet_cancel_q():
    async def _run():
        empty_data = {"profiles": []}

        with patch("run_e2e_pipeline.http_get", return_value=(200, empty_data)), \
             patch("asyncio.to_thread", new=AsyncMock(return_value="q")), \
             pytest.raises(SystemExit):
            await check_and_wait_for_extension_fleet("http://127.0.0.1:8888", interactive=True)

    asyncio.run(_run())


def test_check_and_wait_for_extension_fleet_non_interactive():
    async def _run():
        empty_data = {"profiles": []}

        with patch("run_e2e_pipeline.http_get", return_value=(200, empty_data)):
            profiles = await check_and_wait_for_extension_fleet("http://127.0.0.1:8888", interactive=False)
            assert profiles == []

    asyncio.run(_run())
