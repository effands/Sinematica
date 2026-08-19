import unittest

from backend.provider_config import normalize_settings_update


class ProviderSettingsTests(unittest.TestCase):
    def test_provider_keys_are_trimmed_and_deduplicated(self):
        request = {
            "openai_api_keys": "oa-1\noa-2\noa-1",
            "deepseek_api_keys": [" ds-1 ", "", "ds-1"],
            "xai_api_keys": "xai-1\nxai-1",
            "default_text_provider": "deepseek",
        }

        result = normalize_settings_update(request)

        self.assertEqual(result["openai_api_keys"], ["oa-1", "oa-2"])
        self.assertEqual(result["openai_api_key"], "oa-1")
        self.assertEqual(result["deepseek_api_keys"], ["ds-1"])
        self.assertEqual(result["xai_api_keys"], ["xai-1"])
        self.assertEqual(result["xai_api_key"], "xai-1")
        self.assertEqual(result["default_text_provider"], "deepseek")

    def test_default_provider_is_moved_to_front_of_fallback_order(self):
        request = {
            "default_text_provider": "openai",
            "text_provider_order": ["gemini", "deepseek", "openai", "gemini"],
        }

        result = normalize_settings_update(request)

        self.assertEqual(result["text_provider_order"], ["openai", "gemini", "deepseek", "xai", "web2api"])

    def test_xai_can_be_the_default_provider(self):
        result = normalize_settings_update({"default_text_provider": "xai"})

        self.assertEqual(result["text_provider_order"][0], "xai")

    def test_unknown_provider_is_rejected(self):
        request = {"default_text_provider": "unknown"}

        with self.assertRaises(ValueError):
            normalize_settings_update(request)


if __name__ == "__main__":
    unittest.main()
