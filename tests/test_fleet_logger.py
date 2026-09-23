import datetime
import json
import tempfile
import unittest
from pathlib import Path

from backend.fleet_logger import record_fleet_log, get_recent_fleet_logs, clear_fleet_logs
from backend.jobs_executor import classify_diagnostic, log_event, get_job_logs


class FleetLoggerTests(unittest.TestCase):
    def setUp(self):
        clear_fleet_logs()

    def test_handles_agent_log_and_persists_to_file_and_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_entry = {
                "timestamp": "2026-09-22T12:00:00.000Z",
                "level": "INFO",
                "tag": "DOM:EDITOR",
                "message": "Prompt typed successfully",
                "instance_id": "profile-1",
                "project_id": "proj-abc",
                "meta": {"charCount": 42},
            }
            record_fleet_log(log_entry, log_dir=Path(temp_dir))

            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            expected_log = Path(temp_dir) / f"flow_fleet_{today_str}.log"
            expected_jsonl = Path(temp_dir) / f"flow_fleet_{today_str}.jsonl"
            self.assertTrue(expected_log.exists())
            self.assertTrue(expected_jsonl.exists())

            content = expected_log.read_text(encoding="utf-8")
            self.assertIn("[DOM:EDITOR]", content)
            self.assertIn("Prompt typed successfully", content)
            self.assertIn("profile-1", content)

            jsonl_lines = expected_jsonl.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(jsonl_lines), 1)
            parsed = json.loads(jsonl_lines[0])
            self.assertEqual(parsed["tag"], "DOM:EDITOR")
            self.assertEqual(parsed["meta"]["charCount"], 42)

    def test_in_memory_ring_buffer_stores_recent_logs(self):
        for i in range(1, 15):
            record_fleet_log({
                "timestamp": f"2026-09-22T12:00:{i:02d}.000Z",
                "level": "INFO",
                "tag": "API:PROXY",
                "message": f"Request {i}",
                "instance_id": "profile-1",
            })

        recent = get_recent_fleet_logs(limit=5)
        self.assertEqual(len(recent), 5)
        self.assertEqual(recent[-1]["message"], "Request 14")
        self.assertEqual(recent[0]["message"], "Request 10")

    def test_classify_diagnostic_error_patterns(self):
        diag_tile = classify_diagnostic("Elemen flow-error-tile terdeteksi: Maaf, video gagal dibuat", "error")
        self.assertIsNotNone(diag_tile)
        self.assertEqual(diag_tile["classification"], "GOOGLE_FLOW_MEDIA_GENERATION_FAILED")
        self.assertIn("retry", diag_tile["action_taken"].lower())

        diag_auth = classify_diagnostic("Backend menerima HTTP 401 unauthenticated dari API Flow", "error")
        self.assertIsNotNone(diag_auth)
        self.assertEqual(diag_auth["classification"], "GOOGLE_FLOW_AUTH_SESSION_EXPIRED")

        diag_quota = classify_diagnostic("Profil Flow kehabisan kuota / limit credit (HTTP 429)", "warning")
        self.assertIsNotNone(diag_quota)
        self.assertEqual(diag_quota["classification"], "GOOGLE_FLOW_RESOURCE_EXHAUSTED_OR_RATE_LIMITED")

        diag_policy = classify_diagnostic("Prompt ditolak Google Flow karena kebijakan safety filter", "error")
        self.assertIsNotNone(diag_policy)
        self.assertEqual(diag_policy["classification"], "GOOGLE_FLOW_POLICY_SAFETY_TRIGGERED")

        diag_bridge = classify_diagnostic("Ekstensi Chrome Sinematica terputus / content_script_unreachable", "error")
        self.assertIsNotNone(diag_bridge)
        self.assertEqual(diag_bridge["classification"], "CHROME_EXTENSION_BRIDGE_DISCONNECTED")

    def test_log_event_auto_persists_diagnostic_structure(self):
        job_id = "test_diag_job_001"
        log_event(
            job_id,
            "⚠️ Generasi gambar gagal di Google Flow (flow-error-tile)",
            level="warning",
            profile="Profile Alpha",
        )
        logs = get_job_logs(job_id)
        self.assertTrue(len(logs) > 0)
        last_entry = logs[-1]
        self.assertEqual(last_entry["profile"], "Profile Alpha")
        self.assertIn("diagnostic", last_entry)
        self.assertEqual(last_entry["diagnostic"]["classification"], "GOOGLE_FLOW_MEDIA_GENERATION_FAILED")

