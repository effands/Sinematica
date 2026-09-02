import unittest

from backend.text_generation import (
    GeminiAdapter,
    ProviderCallError,
    TextGenerationManager,
    build_chat_completions_endpoint,
    classify_error,
)


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    def post(self, url, headers, json, timeout):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return self.response


class MemoryKeyStore:
    def __init__(self, values):
        self.values = {name: list(keys) for name, keys in values.items()}

    def keys(self, provider):
        return list(self.values.get(provider, []))

    def demote(self, provider, key):
        keys = self.values[provider]
        keys.remove(key)
        keys.append(key)


class SequenceAdapter:
    def __init__(self, provider, outcomes):
        self.provider = provider
        self.outcomes = outcomes

    def generate(self, prompt, key, model, json_output=False):
        outcome = self.outcomes[key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class OrderedAdapter:
    def __init__(self, provider, outcomes):
        self.provider = provider
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate(self, prompt, key, model, json_output=False):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TextGenerationManagerTests(unittest.TestCase):
    def test_xai_unavailable_model_is_not_mislabeled_as_invalid_key(self):
        error = '{"code":"model_not_found","message":"model not found"}'

        self.assertEqual(classify_error(error, 403), "model")
    def test_xai_base_url_gets_chat_completions_suffix_once(self):
        self.assertEqual(
            build_chat_completions_endpoint("https://api.x.ai/v1/"),
            "https://api.x.ai/v1/chat/completions",
        )
        self.assertEqual(
            build_chat_completions_endpoint("https://workspace.test/v1/chat/completions"),
            "https://workspace.test/v1/chat/completions",
        )
    def test_gemini_uses_interactions_api_and_parses_model_output(self):
        transport = FakeTransport(FakeResponse(200, {
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": "pong"}]}]
        }))
        adapter = GeminiAdapter(transport=transport)

        result = adapter.generate("ping", "secret", "gemini-3.6-flash")

        self.assertEqual(result, "pong")
        self.assertEqual(transport.last_url, "https://generativelanguage.googleapis.com/v1beta/interactions")
        self.assertEqual(transport.last_headers["x-goog-api-key"], "secret")
        self.assertEqual(transport.last_json, {"model": "gemini-3.6-flash", "input": "ping"})

    def test_gemini_reports_unavailable_model_separately_from_bad_key(self):
        transport = FakeTransport(FakeResponse(404, text="model not found"))
        adapter = GeminiAdapter(transport=transport)

        with self.assertRaises(ProviderCallError) as caught:
            adapter.generate("ping", "secret", "gemini-3.7-flash")

        self.assertEqual(caught.exception.classification, "model")

    def test_quota_rotates_key_then_uses_next_key(self):
        quota = ProviderCallError("gemini", "quota", 429, "quota exhausted")
        store = MemoryKeyStore({"gemini": ["key-a", "key-b"]})
        manager = TextGenerationManager(
            adapters={"gemini": SequenceAdapter("gemini", {"key-a": quota, "key-b": "ok"})},
            key_store=store,
            settings_loader=lambda: {"gemini_model": "gemini-test"},
        )

        result = manager.generate("hello", provider_order=["gemini"])

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(store.keys("gemini"), ["key-b", "key-a"])

    def test_failed_primary_provider_switches_to_next_provider(self):
        quota = ProviderCallError("openai", "quota", 429, "quota exhausted")
        store = MemoryKeyStore({"openai": ["oa"], "deepseek": ["ds"]})
        manager = TextGenerationManager(
            adapters={
                "openai": SequenceAdapter("openai", {"oa": quota}),
                "deepseek": SequenceAdapter("deepseek", {"ds": '{"ok":true}'}),
            },
            key_store=store,
            settings_loader=lambda: {
                "openai_model": "gpt-test",
                "deepseek_model": "deepseek-test",
            },
        )

        result = manager.generate("hello", provider_order=["openai", "deepseek"], json_output=True)

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.text, '{"ok":true}')

    def test_truncated_json_is_retried_once_on_same_provider(self):
        adapter = OrderedAdapter("openai", ['{"story": "cut off', '{"story":"complete"}'])
        manager = TextGenerationManager(
            adapters={"openai": adapter},
            key_store=MemoryKeyStore({"openai": ["oa"]}),
            settings_loader=lambda: {"openai_model": "gpt-test"},
        )

        result = manager.generate("hello", provider_order=["openai"], json_output=True)

        self.assertEqual(result.text, '{"story":"complete"}')
        self.assertEqual(adapter.calls, 2)

    def test_malformed_json_falls_through_to_next_provider(self):
        primary = OrderedAdapter("openai", ['{"bad":', '{"still_bad":'])
        fallback = OrderedAdapter("deepseek", ['```json\n{"ok":true}\n```'])
        manager = TextGenerationManager(
            adapters={"openai": primary, "deepseek": fallback},
            key_store=MemoryKeyStore({"openai": ["oa"], "deepseek": ["ds"]}),
            settings_loader=lambda: {
                "openai_model": "gpt-test",
                "deepseek_model": "deepseek-test",
            },
        )

        result = manager.generate(
            "hello", provider_order=["openai", "deepseek"], json_output=True
        )

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(primary.calls, 2)
        self.assertEqual(fallback.calls, 1)

    def test_default_provider_is_tried_before_fallbacks(self):
        store = MemoryKeyStore({"deepseek": ["ds"], "gemini": ["gm"]})
        manager = TextGenerationManager(
            adapters={
                "deepseek": SequenceAdapter("deepseek", {"ds": "deepseek result"}),
                "gemini": SequenceAdapter("gemini", {"gm": "gemini result"}),
            },
            key_store=store,
            settings_loader=lambda: {
                "default_text_provider": "deepseek",
                "text_provider_order": ["gemini", "deepseek"],
                "deepseek_model": "deepseek-test",
                "gemini_model": "gemini-test",
            },
        )

        result = manager.generate("hello")

        self.assertEqual(result.provider, "deepseek")


if __name__ == "__main__":
    unittest.main()
