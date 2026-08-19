import tempfile
import unittest
from pathlib import Path

from backend.gallery_cleanup import cleanup_job_files, job_source_files


class GalleryCleanupTests(unittest.TestCase):
    def test_job_source_files_records_theme_and_music_without_duplicates(self):
        theme = "storage/uploads/ref_one.jpg"

        result = job_source_files(
            theme,
            {
                "_theme_image_path": theme,
                "music_track_path": "storage/uploads/music_one.mp3",
            },
        )

        self.assertEqual(
            result,
            [theme, "storage/uploads/music_one.mp3"],
        )

    def test_deleting_gallery_job_removes_job_folder_and_its_orphan_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jobs_dir = root / "jobs"
            uploads_dir = root / "uploads"
            job_dir = jobs_dir / "job_one"
            upload = uploads_dir / "music_one.mp3"
            job_dir.mkdir(parents=True)
            uploads_dir.mkdir(parents=True)
            (job_dir / "scene_01.mp4").write_bytes(b"video")
            upload.write_bytes(b"music")

            result = cleanup_job_files(
                "job_one",
                {"source_files": [str(upload)]},
                [],
                jobs_dir=jobs_dir,
                uploads_dir=uploads_dir,
            )

            self.assertFalse(job_dir.exists())
            self.assertFalse(upload.exists())
            self.assertEqual(result.deleted_uploads, [str(upload.resolve())])

    def test_upload_referenced_by_another_gallery_job_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jobs_dir = root / "jobs"
            uploads_dir = root / "uploads"
            shared = uploads_dir / "shared.mp3"
            (jobs_dir / "job_one").mkdir(parents=True)
            uploads_dir.mkdir(parents=True)
            shared.write_bytes(b"music")

            result = cleanup_job_files(
                "job_one",
                {"source_files": [str(shared)]},
                [{"job_id": "job_two", "source_files": [str(shared)]}],
                jobs_dir=jobs_dir,
                uploads_dir=uploads_dir,
            )

            self.assertTrue(shared.exists())
            self.assertEqual(result.deleted_uploads, [])

    def test_source_outside_uploads_directory_is_never_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jobs_dir = root / "jobs"
            uploads_dir = root / "uploads"
            outside = root / "actors" / "actor.jpg"
            (jobs_dir / "job_one").mkdir(parents=True)
            uploads_dir.mkdir(parents=True)
            outside.parent.mkdir(parents=True)
            outside.write_bytes(b"actor")

            cleanup_job_files(
                "job_one",
                {"source_files": [str(outside)]},
                [],
                jobs_dir=jobs_dir,
                uploads_dir=uploads_dir,
            )

            self.assertTrue(outside.exists())

    def test_job_id_cannot_escape_jobs_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jobs_dir = root / "jobs"
            uploads_dir = root / "uploads"
            outside = root / "do-not-delete"
            jobs_dir.mkdir()
            uploads_dir.mkdir()
            outside.mkdir()
            (outside / "keep.txt").write_text("keep", encoding="utf-8")

            result = cleanup_job_files(
                "../do-not-delete",
                {},
                [],
                jobs_dir=jobs_dir,
                uploads_dir=uploads_dir,
            )

            self.assertTrue(outside.exists())
            self.assertFalse(result.job_directory_deleted)


if __name__ == "__main__":
    unittest.main()
