import unittest

from backend.jobs_executor import build_video_reference_ids, choose_instance_for_project


class VideoReferenceSelectionTests(unittest.TestCase):
    def test_all_character_sheets_and_storyboard_fit_up_to_ten(self):
        self.assertEqual(
            build_video_reference_ids(["char-a", "char-b", "char-c"], "storyboard"),
            ["char-a", "char-b", "char-c", "storyboard"],
        )

    def test_ten_character_sheets_take_priority_over_storyboard(self):
        characters = [f"char-{index}" for index in range(10)]
        self.assertEqual(build_video_reference_ids(characters, "storyboard"), characters)

    def test_storyboard_only_fills_an_unused_slot(self):
        self.assertEqual(
            build_video_reference_ids(["char-a", "char-b"], "storyboard"),
            ["char-a", "char-b", "storyboard"],
        )

    def test_policy_retry_keeps_characters_and_removes_storyboard(self):
        self.assertEqual(
            build_video_reference_ids(["char-a", "char-b"], "storyboard", policy_attempt=2),
            ["char-a", "char-b"],
        )

    def test_storyboard_is_last_resort_without_character_sheet(self):
        self.assertEqual(
            build_video_reference_ids([], "storyboard", policy_attempt=1),
            ["storyboard"],
        )

    def test_profile_owning_flow_project_is_selected(self):
        instances = [
            {"instance_id": "empty-active", "connected": True, "project_id": None},
            {"instance_id": "project-owner", "connected": True, "project_id": "project-123"},
        ]
        self.assertEqual(
            choose_instance_for_project(instances, "project-123"),
            "project-owner",
        )


if __name__ == "__main__":
    unittest.main()
