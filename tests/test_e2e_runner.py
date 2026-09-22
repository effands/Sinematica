import pytest
from pathlib import Path
from scripts.test_e2e_generation import (
    format_log_line,
    find_latest_scene_master_job,
    parse_cli_arguments,
    check_fleet_ready,
)


def test_format_log_line_formats_clean_output():
    entry = {
        "timestamp": "10:15:30",
        "level": "info",
        "profile": "System",
        "message": "[6%] Mengirim request character seed image 'Aruna Wening'...",
    }
    line = format_log_line(entry)
    assert "10:15:30" in line
    assert "Mengirim request character seed" in line


def test_find_latest_scene_master_job(tmp_path):
    history_file = tmp_path / "jobs_history.json"
    history_file.write_text(
        '[{"job_id": "job_1", "title": "Test 1", "created_at": 100},'
        ' {"job_id": "job_2", "title": "Test 2", "created_at": 200, "storyboard": {"scenes": [1]}}]',
        encoding="utf-8",
    )
    job = find_latest_scene_master_job(history_file)
    assert job is not None
    assert job["job_id"] == "job_2"
    assert job["title"] == "Test 2"


def test_find_latest_scene_master_job_empty(tmp_path):
    history_file = tmp_path / "non_existent.json"
    job = find_latest_scene_master_job(history_file)
    assert job is None


def test_parse_cli_arguments():
    args = parse_cli_arguments(["--limit", "1", "--scene", "2", "--port", "8888"])
    assert args.limit == 1
    assert args.scene == 2
    assert args.port == 8888


def test_check_fleet_ready_helper():
    mock_fleet_data = {
        "profiles": [
            {
                "instance_id": "profile-test1",
                "connected": True,
                "logged_in": True,
                "ready": True,
                "flow_project_url": "https://flow.google.com/u/0/project/123",
            }
        ]
    }
    is_ready, msg, profiles = check_fleet_ready("http://127.0.0.1:8888", mock_data=mock_fleet_data)
    assert is_ready is True
    assert "profile-test1" in msg
    assert len(profiles) == 1
