import unittest
import threading
import time

from backend.provider_validation import GeminiConnectivityProbe, adapter_for, validate_provider_keys
from backend.text_generation import ProviderCallError


class FakeAdapter:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    def generate(self, prompt, key, model, json_output=False):
        outcome = self.outcomes[key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ConcurrencyAdapter:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def generate(self, prompt, key, model, json_output=False):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        with self.lock:
            self.active -= 1
        return "pong"


class ProviderValidationTests(unittest.TestCase):
    def test_xai_probe_uses_configured_openai_compatible_endpoint(self):
        adapter = adapter_for(
            "xai",
            base_url="https://api.x.ai/v1",
            transport=object(),
        )

        self.assertEqual(
            adapter.endpoint,
            "https://api.x.ai/v1/chat/completions",
        )
    def test_gemini_connectivity_probe_uses_lightweight_models_endpoint(self):
        class Response:
            status_code = 200
            text = '{}'
        class Transport:
            def get(self, url, headers, timeout):
                self.url, self.headers, self.timeout = url, headers, timeout
                return Response()
        transport = Transport()

        result = GeminiConnectivityProbe(transport=transport, timeout=10).generate("ping", "secret", "gemini-3.6-flash")

        self.assertEqual(result, "connected")
        self.assertEqual(transport.url, "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1")
        self.assertEqual(transport.headers["x-goog-api-key"], "secret")

    def test_multiple_keys_are_validated_in_parallel(self):
        adapter = ConcurrencyAdapter()

        results = validate_provider_keys("gemini", ["key-1", "key-2", "key-3"], "model", adapter=adapter)

        self.assertEqual([item["status"] for item in results], ["valid", "valid", "valid"])
        self.assertGreaterEqual(adapter.max_active, 3)

    def test_reports_each_key_status_without_returning_full_keys(self):
        adapter = FakeAdapter({
            "valid-secret-key": "pong",
            "quota-secret-key": ProviderCallError("openai", "quota", 429, "quota"),
            "invalid-secret-key": ProviderCallError("openai", "auth", 401, "invalid"),
            "offline-secret-key": ProviderCallError("openai", "transient", 503, "offline"),
            "model-secret-key": ProviderCallError("gemini", "model", 404, "model missing"),
        })

        results = validate_provider_keys(
            "openai",
            list(adapter.outcomes),
            "gpt-test",
            adapter=adapter,
        )

        self.assertEqual([item["status"] for item in results], [
            "valid", "quota_limited", "invalid", "unreachable", "model_unavailable"
        ])
        self.assertTrue(all("secret" not in item["key_preview"] for item in results))
        self.assertTrue(all("key" not in item for item in results))
        self.assertEqual(results[1]["http_status"], 429)
        self.assertIn("quota", results[1]["detail"])
        self.assertNotIn("secret", str(results))


if __name__ == "__main__":
    unittest.main()
