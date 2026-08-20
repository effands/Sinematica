import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.execution_metrics import finish_job_timing, format_elapsed, record_output_file_size


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

    def test_output_size_is_recorded_in_bytes_and_mb(self):
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "film.mp4"
            output.write_bytes(b"x" * 1_572_864)
            job = {}

            record_output_file_size(job, output)

        self.assertEqual(job["output_size_bytes"], 1_572_864)
        self.assertEqual(job["output_size_mb"], 1.5)
        self.assertEqual(job["output_size_display"], "1.50 MB")


if __name__ == "__main__":
    unittest.main()
