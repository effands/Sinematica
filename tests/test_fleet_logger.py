import datetime
import tempfile
import unittest
from pathlib import Path

from backend.fleet_logger import record_fleet_log, get_recent_fleet_logs, clear_fleet_logs


class FleetLoggerTests(unittest.TestCase):
    def setUp(self):
        clear_fleet_logs()

    def test_handles_agent_log_and_persists_to_file(self):
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
            expected_file = Path(temp_dir) / f"flow_fleet_{today_str}.log"
            self.assertTrue(expected_file.exists())

            content = expected_file.read_text(encoding="utf-8")
            self.assertIn("[DOM:EDITOR]", content)
            self.assertIn("Prompt typed successfully", content)
            self.assertIn("profile-1", content)

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
