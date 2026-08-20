import unittest

from backend.gallery_metadata import gallery_metadata


class GalleryMetadataTests(unittest.TestCase):
    def test_exposes_runtime_size_processing_time_and_initial_prompt(self):
        job = {
            "total_duration": 40,
            "output_size_bytes": 10_878_210,
            "output_size_display": "10.38 MB",
            "processing_seconds": 595.045,
            "processing_duration": "9m 55s",
            "initial_prompt": "Goku melawan Boboiboy di medan berbatu.",
        }

        self.assertEqual(gallery_metadata(job), {
            "total_duration": 40,
            "output_size_bytes": 10_878_210,
            "output_size_display": "10.38 MB",
            "processing_seconds": 595.045,
            "processing_duration": "9m 55s",
            "initial_prompt": "Goku melawan Boboiboy di medan berbatu.",
        })

    def test_uses_story_idea_alias_for_older_job_shape(self):
        self.assertEqual(gallery_metadata({"premise": "Ide lama"})["initial_prompt"], "Ide lama")


if __name__ == "__main__":
    unittest.main()
