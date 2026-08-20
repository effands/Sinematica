import unittest

from backend.execution_metrics import finish_job_timing, format_elapsed


class ExecutionMetricsTests(unittest.TestCase):
    def test_finish_records_end_time_and_elapsed_seconds(self):
        job = {"created_at": 100.25}
        finish_job_timing(job, now=225.75)

        self.assertEqual(job["started_at"], 100.25)
        self.assertEqual(job["completed_at"], 225.75)
        self.assertEqual(job["processing_seconds"], 125.5)
        self.assertEqual(job["processing_duration"], "2m 5s")

    def test_elapsed_format_supports_hours(self):
        self.assertEqual(format_elapsed(3723.4), "1h 2m 3s")


if __name__ == "__main__":
    unittest.main()
