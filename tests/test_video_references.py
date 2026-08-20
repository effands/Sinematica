import unittest

from backend.jobs_executor import (
    build_video_reference_ids,
    build_live_action_guard,
    choose_instance_for_project,
    fictionalize_character_names,
    should_drop_character_references,
)


class VideoReferenceSelectionTests(unittest.TestCase):
    def test_adult_mode_explicitly_forbids_cartoon_character_and_storyboard_images(self):
        guard = build_live_action_guard(children_mode=False)
        self.assertIn("LIVE-ACTION PHOTOGRAPHY ONLY", guard)
        self.assertIn("no cartoon", guard.lower())

    def test_children_mode_does_not_receive_live_action_guard(self):
        self.assertEqual(build_live_action_guard(children_mode=True), "")

    def test_all_character_sheets_and_storyboard_fit_up_to_ten(self):
        self.assertEqual(
            build_video_reference_ids(["char-a", "char-b", "char-c"], "storyboard"),
            ["char-a", "char-b", "char-c", "storyboard"],
        )

    def test_continuity_frame_is_first_and_storyboard_is_last_ingredient(self):
        self.assertEqual(
            build_video_reference_ids(
                ["char-a", "char-b"],
                "storyboard",
                continuity_media_id="last-frame",
            ),
            ["last-frame", "char-a", "char-b", "storyboard"],
        )

    def test_ingredient_limit_prioritizes_last_frame_then_characters(self):
        self.assertEqual(
            build_video_reference_ids(
                ["char-a", "char-b", "char-c"],
                "storyboard",
                continuity_media_id="last-frame",
                limit=3,
            ),
            ["last-frame", "char-a", "char-b"],
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

    def test_final_reference_policy_retry_removes_every_image_reference(self):
        self.assertEqual(
            build_video_reference_ids(
                ["char-a"],
                "storyboard",
                policy_attempt=2,
                drop_all_references=True,
            ),
            [],
        )

    def test_prominent_people_rejection_drops_references_only_on_final_retry(self):
        reason = "Generasi ditolak: PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED"
        self.assertFalse(should_drop_character_references(reason, 1, 2))
        self.assertTrue(should_drop_character_references(reason, 2, 2))

    def test_non_image_policy_rejection_keeps_references_on_final_retry(self):
        self.assertFalse(
            should_drop_character_references("PUBLIC_ERROR_UNSAFE_GENERATION", 2, 2)
        )

    def test_reference_free_prompt_replaces_character_names_with_fictional_aliases(self):
        prompt = "Hana looks at Budi. Hana says hello to Budi."
        self.assertEqual(
            fictionalize_character_names(prompt, ["Hana", "Budi"]),
            "Fictional Character A looks at Fictional Character B. "
            "Fictional Character A says hello to Fictional Character B.\n\n"
            "Use entirely original fictional adult characters with non-celebrity faces. "
            "Do not imitate any real person, public figure, actor, protected character, brand, or franchise.",
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
