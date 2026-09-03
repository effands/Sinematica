import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import shutil

from backend.jobs_executor import resume_job, get_job_status, _active_jobs


class TestJobResume(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        _active_jobs.clear()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        _active_jobs.clear()

    def test_resume_non_existent_job_returns_false(self):
        self.assertFalse(resume_job("non_existent_job_id"))

    def test_resume_valid_job_starts_processing(self):
        job_id = "test_job_123"
        _active_jobs[job_id] = {
            "job_id": job_id,
            "title": "Test Movie",
            "status": "failed",
            "storyboard": {
                "film_title": "Test Movie",
                "characters": [],
                "scenes": [{"scene_number": 1, "title": "Scene 1", "action_summary": "Test action"}]
            }
        }

        with patch("backend.jobs_executor.asyncio.create_task") as mock_task:
            success = resume_job(job_id)
            self.assertTrue(success)
            self.assertEqual(_active_jobs[job_id]["status"], "processing")
            self.assertFalse(_active_jobs[job_id]["cancelled"])
            mock_task.assert_called_once()
            mock_task.call_args.args[0].close()

    def test_resume_accepts_a_flexible_scene_limit(self):
        job_id = "test_job_quota"
        _active_jobs[job_id] = {
            "job_id": job_id,
            "status": "waiting_for_quota",
            "storyboard": {"scenes": [{"scene_number": 1}]},
        }

        with patch("backend.jobs_executor.asyncio.create_task") as mock_task:
            self.assertTrue(resume_job(job_id, render_scene_limit=3))
            self.assertEqual(_active_jobs[job_id]["render_scene_limit"], 3)
            coroutine = mock_task.call_args.args[0]
            coroutine.close()

    def test_resume_can_clear_an_old_scene_limit(self):
        job_id = "test_job_clear_quota"
        _active_jobs[job_id] = {
            "job_id": job_id,
            "status": "waiting_for_quota",
            "render_scene_limit": 2,
            "storyboard": {"scenes": [{"scene_number": 1}]},
        }

        with patch("backend.jobs_executor.asyncio.create_task") as mock_task:
            self.assertTrue(resume_job(job_id, render_scene_limit=None))
            self.assertIsNone(_active_jobs[job_id]["render_scene_limit"])
            mock_task.call_args.args[0].close()


if __name__ == "__main__":
    unittest.main()
