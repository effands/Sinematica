"""Text generation adapters with API-key rotation and provider failover."""

from dataclasses import dataclass
import base64
import json
from io import BytesIO
import logging
import threading
from typing import Any, Dict, Optional

from .provider_config import ALL_TEXT_PROVIDERS, normalize_keys, provider_order

log = logging.getLogger("sinematica.text_generation")
_settings_lock = threading.RLock()


def _extract_json_payload(raw: str) -> str:
    """Return the JSON body even when a provider wraps it in a markdown fence."""
    text = (raw or "").strip()
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text


def _validate_json_output(text: str) -> None:
    """Reject truncated/malformed model output before provider failover stops."""
    json.loads(_extract_json_payload(text))


def build_chat_completions_endpoint(base_url: str) -> str:
    """Normalize an OpenAI-compatible base URL to the Chat Completions endpoint."""
    clean = str(base_url or "").strip().rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    key_index: Optional[int] = None


class ProviderCallError(RuntimeError):
    def __init__(self, provider: str, classification: str, status: Optional[int], message: str):
        super().__init__(message)
        self.provider = provider
        self.classification = classification
        self.status = status


def classify_error(error: Any, status: Optional[int] = None) -> str:
    text = str(error).lower()
    if status == 404 or any(word in text for word in (
        "model not found", "model is not found", "unsupported model",
        "accessdenied.unpurchased", "access to model denied", "unpurchased",
    )):
        return "model"
    if status == 429 or any(word in text for word in ("resource_exhausted", "quota", "rate limit", "too many requests")):
        return "quota"
    if status in (401, 403) or any(word in text for word in ("invalid api key", "unauthorized", "authentication")):
        return "auth"
    if status in (408, 500, 502, 503, 504) or any(word in text for word in ("timeout", "temporarily unavailable")):
        return "transient"
    return "other"


class SettingsKeyStore:
    def keys(self, provider: str):
        from . import settings
        cfg = settings.get_settings()
        keys = normalize_keys(cfg.get(f"{provider}_api_keys") or cfg.get(f"{provider}_api_key"))
        return keys

    def demote(self, provider: str, key: str):
        from . import settings
        with _settings_lock:
            keys = self.keys(provider)
            if key in keys:
                keys.remove(key)
                keys.append(key)
                settings.save_settings({
                    f"{provider}_api_keys": keys,
                    f"{provider}_api_key": keys[0] if keys else "",
                })


class GeminiAdapter:
    provider = "gemini"

    def __init__(self, transport=None, timeout=180):
        if transport is None:
            import requests
            transport = requests
        self.transport = transport
        self.timeout = timeout

    def generate(self, prompt, key, model, json_output=False):
        payload = {"model": model, "input": _gemini_interaction_input(prompt)}
        try:
            response = self.transport.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        except Exception as ex:
            raise ProviderCallError(self.provider, classify_error(ex), None, str(ex)) from ex
        if response.status_code != 200:
            message = response.text[:500]
            raise ProviderCallError(self.provider, classify_error(message, response.status_code), response.status_code, message)
        try:
            texts = []
            for step in response.json().get("steps", []):
                if step.get("type") != "model_output":
                    continue
                texts.extend(block.get("text", "") for block in step.get("content", []) if block.get("type") == "text")
            output = "\n".join(text for text in texts if text).strip()
            if not output:
                raise ValueError("Respons Interactions API tidak memiliki output teks")
            return output
        except ProviderCallError:
            raise
        except Exception as ex:
            raise ProviderCallError(self.provider, "other", response.status_code, str(ex)) from ex


def _gemini_interaction_input(prompt):
    if isinstance(prompt, str):
        return prompt
    parts = []
    for item in prompt:
        if isinstance(item, str):
            parts.append({"text": item})
        elif hasattr(item, "save"):
            buffer = BytesIO()
            image_format = (getattr(item, "format", None) or "PNG").upper()
            item.save(buffer, format=image_format)
            parts.append({"inline_data": {
                "mime_type": f"image/{image_format.lower().replace('jpg', 'jpeg')}",
                "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
            }})
    return {"parts": parts}


class OpenAICompatibleAdapter:
    def __init__(self, provider: str, endpoint: str, transport=None, timeout=180):
        self.provider = provider
        self.endpoint = endpoint
        if transport is None:
            import requests
            transport = requests
        self.transport = transport
        self.timeout = timeout

    def generate(self, prompt, key, model, json_output=False):
        if not isinstance(prompt, str):
            prompt = "\n\n".join(str(item) for item in prompt if isinstance(item, str))
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = self.transport.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        except Exception as ex:
            raise ProviderCallError(self.provider, classify_error(ex), None, str(ex)) from ex
        if response.status_code != 200:
            message = response.text[:500]
            raise ProviderCallError(self.provider, classify_error(message, response.status_code), response.status_code, message)
        try:
            return response.json()["choices"][0]["message"]["content"]
        except Exception as ex:
            raise ProviderCallError(self.provider, "other", response.status_code, "Respons provider tidak valid") from ex


class TextGenerationManager:
    def __init__(self, adapters=None, key_store=None, settings_loader=None):
        self.adapters = adapters or {
            "gemini": GeminiAdapter(),
            "openai": OpenAICompatibleAdapter("openai", "https://api.openai.com/v1/chat/completions"),
            "deepseek": OpenAICompatibleAdapter("deepseek", "https://api.deepseek.com/chat/completions"),
            "xai": OpenAICompatibleAdapter(
                "xai",
                "https://api.x.ai/v1/chat/completions",
            ),
        }
        self.key_store = key_store or SettingsKeyStore()
        self.settings_loader = settings_loader or _load_settings

    def generate(self, prompt, provider_order=None, json_output=False):
        cfg = self.settings_loader()
        default = cfg.get("default_text_provider", "gemini")
        order = provider_order or provider_order_from_settings(cfg, default)
        last_error = None
        for provider in order:
            if provider == "web2api":
                continue
            adapter = self.adapters.get(provider)
            if not adapter:
                continue
            if provider == "xai" and isinstance(adapter, OpenAICompatibleAdapter):
                adapter.endpoint = build_chat_completions_endpoint(
                    cfg.get("xai_base_url")
                    or "https://api.x.ai/v1"
                )
            keys = self.key_store.keys(provider)
            model = cfg.get(f"{provider}_model") or default_model(provider)
            for index, key in enumerate(keys, start=1):
                # A successful HTTP response can still contain JSON cut off by the
                # model's output limit. Retry that key once, then continue through
                # the normal key/provider failover chain.
                attempts = 2 if json_output else 1
                for attempt in range(1, attempts + 1):
                    try:
                        text = adapter.generate(prompt, key, model, json_output=json_output)
                        if json_output:
                            _validate_json_output(text)
                        log.info("Teks berhasil dibuat via %s key #%d (%s).", provider, index, model)
                        return ProviderResult(text=text, provider=provider, model=model, key_index=index)
                    except json.JSONDecodeError as ex:
                        last_error = ProviderCallError(
                            provider, "invalid_output", None,
                            f"Respons JSON tidak lengkap/valid: {ex}",
                        )
                        log.warning(
                            "Provider %s key #%d menghasilkan JSON tidak valid (percobaan %d/%d): %s",
                            provider, index, attempt, attempts, ex,
                        )
                    except ProviderCallError as ex:
                        last_error = ex
                        log.warning("Provider %s key #%d gagal (%s).", provider, index, ex.classification)
                        if ex.classification == "quota":
                            self.key_store.demote(provider, key)
                        break
        if last_error:
            raise last_error
        raise RuntimeError("Tidak ada API key provider AI yang dikonfigurasi.")


def default_model(provider):
    return {
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4.1-mini",
        "deepseek": "deepseek-chat",
        "xai": "grok-4.3",
    }[provider]


def provider_order_from_settings(cfg: Dict[str, Any], default: str):
    return provider_order(default, cfg.get("text_provider_order"))


def generate_text(prompt, json_output=False):
    return TextGenerationManager().generate(prompt, json_output=json_output)


def _load_settings():
    from . import settings
    return settings.get_settings()
