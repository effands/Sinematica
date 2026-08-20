import unittest

from backend.character_seed_fallback import (
    build_safe_character_seed_prompt,
    is_unsafe_generation_error,
)


class CharacterSeedFallbackTests(unittest.TestCase):
    def test_detects_flow_unsafe_generation_reason(self):
        error = RuntimeError(
            "Google Flow (400): {'reason': 'PUBLIC_ERROR_UNSAFE_GENERATION'}"
        )
        self.assertTrue(is_unsafe_generation_error(error))
        self.assertFalse(is_unsafe_generation_error(RuntimeError("Quota exceeded")))

    def test_builds_neutral_unbranded_prompt_without_original_name(self):
        prompt = build_safe_character_seed_prompt(
            "Hulk",
            "Hulk is a giant green muscular superhero wearing torn purple trousers.",
            685211,
        )

        self.assertNotIn("hulk", prompt.lower())
        self.assertIn("giant green muscular superhero", prompt.lower())
        self.assertIn("685211", prompt)
        self.assertIn("neutral", prompt.lower())
        self.assertIn("unbranded", prompt.lower())

    def test_reference_instruction_is_kept_when_images_are_attached(self):
        prompt = build_safe_character_seed_prompt(
            "Blocked Name", "Tall hero in a blue suit.", 123, has_references=True
        )
        self.assertIn("attached reference images", prompt.lower())

    def test_removes_base_name_when_character_has_parenthesized_locale(self):
        prompt = build_safe_character_seed_prompt(
            "Hulk (Indonesia)",
            "Hulk is 30 years old with green skin and a huge muscular physique.",
            685211,
        )
        self.assertNotIn("hulk", prompt.lower())

    def test_distinct_reinterpretation_avoids_signature_colour_and_costume(self):
        prompt = build_safe_character_seed_prompt(
            "Hulk (Indonesia)",
            "Hulk has bright green skin and torn purple pants.",
            685211,
            distinct_reinterpretation=True,
        )
        lowered = prompt.lower()
        self.assertNotIn("hulk", lowered)
        self.assertNotIn("green", lowered)
        self.assertNotIn("purple", lowered)
        self.assertIn("mineral-skinned fantasy guardian", lowered)


if __name__ == "__main__":
    unittest.main()
