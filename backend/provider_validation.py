"""Safe API-key connectivity checks shared by all text providers."""

from typing import Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .provider_config import CLOUD_PROVIDERS, normalize_keys
from .text_generation import (
    OpenAICompatibleAdapter,
    ProviderCallError,
    build_chat_completions_endpoint,
    classify_error,
)


class GeminiConnectivityProbe:
    """Validate a Gemini key without consuming a text-generation request."""

    def __init__(self, transport=None, timeout=20):
        if transport is None:
            import requests
            transport = requests
        self.transport = transport
        self.timeout = timeout

    def generate(self, prompt, key, model, json_output=False):
        try:
            response = self.transport.get(
                "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                headers={"x-goog-api-key": key},
                timeout=self.timeout,
            )
        except Exception as ex:
            raise ProviderCallError("gemini", classify_error(ex), None, str(ex)) from ex
        if response.status_code != 200:
            message = response.text[:500]
            raise ProviderCallError("gemini", classify_error(message, response.status_code), response.status_code, message)
        return "connected"


def adapter_for(provider: str, timeout: int = 20, base_url: str = "", transport=None):
    if provider == "gemini":
        return GeminiConnectivityProbe(transport=transport, timeout=timeout)
    if provider == "openai":
        return OpenAICompatibleAdapter("openai", "https://api.openai.com/v1/chat/completions", transport=transport, timeout=timeout)
    if provider == "deepseek":
        return OpenAICompatibleAdapter("deepseek", "https://api.deepseek.com/chat/completions", transport=transport, timeout=timeout)
    if provider == "xai":
        return OpenAICompatibleAdapter(
            "xai",
            build_chat_completions_endpoint(
                base_url or "https://api.x.ai/v1"
            ),
            transport=transport,
            timeout=timeout,
        )
    raise ValueError(f"Provider tidak dikenal: {provider}")


def _preview(key: str) -> str:
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}••••{key[-4:]}"


def validate_provider_keys(
    provider: str, keys: Any, model: str, adapter=None, base_url: str = ""
) -> List[dict]:
    if provider not in CLOUD_PROVIDERS:
        raise ValueError(f"Provider tidak dikenal: {provider}")
    clean_keys = normalize_keys(keys)
    if not clean_keys:
        raise ValueError(f"API key {provider} belum diisi.")
    adapter = adapter or adapter_for(provider, base_url=base_url)
    statuses = {
        "quota": "quota_limited",
        "auth": "invalid",
        "transient": "unreachable",
        "other": "unreachable",
        "model": "model_unavailable",
    }
    def validate_one(index_key):
        index, key = index_key
        item = {"index": index, "key_preview": _preview(key), "status": "valid", "model": model}
        try:
            adapter.generate("Reply with exactly: pong", key, model, json_output=False)
        except ProviderCallError as ex:
            item["status"] = statuses.get(ex.classification, "unreachable")
            item["http_status"] = ex.status
            item["detail"] = str(ex).replace(key, "[redacted]")[:300]
        except Exception as ex:
            item["status"] = "unreachable"
            item["http_status"] = None
            item["detail"] = str(ex).replace(key, "[redacted]")[:300]
        return item

    indexed_keys = list(enumerate(clean_keys, start=1))
    # A small pool avoids both serial multi-minute waits and connection/API
    # saturation when users keep many keys in one provider.
    with ThreadPoolExecutor(max_workers=min(3, len(indexed_keys))) as executor:
        futures = [executor.submit(validate_one, item) for item in indexed_keys]
        results = [future.result() for future in as_completed(futures)]
    return sorted(results, key=lambda item: item["index"])
