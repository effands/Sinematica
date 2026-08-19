"""Normalization helpers for multi-provider AI settings."""

from typing import Any, Dict, Iterable, List


CLOUD_PROVIDERS = ("gemini", "openai", "deepseek", "xai")
ALL_TEXT_PROVIDERS = (*CLOUD_PROVIDERS, "web2api")


def normalize_keys(value: Any) -> List[str]:
    if isinstance(value, str):
        values: Iterable[Any] = value.replace("\n", ",").split(",")
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        values = []
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def provider_order(default_provider: str, requested: Any = None) -> List[str]:
    if default_provider not in CLOUD_PROVIDERS:
        raise ValueError(f"Provider utama tidak dikenal: {default_provider}")
    raw = requested if isinstance(requested, list) else list(ALL_TEXT_PROVIDERS)
    clean = [name for name in raw if name in ALL_TEXT_PROVIDERS]
    clean = list(dict.fromkeys(clean))
    return [default_provider, *[name for name in clean if name != default_provider],
            *[name for name in ALL_TEXT_PROVIDERS if name not in clean and name != default_provider]]


def normalize_settings_update(data: Any) -> Dict[str, Any]:
    if hasattr(data, "model_dump"):
        result = data.model_dump(exclude_unset=True)
    elif hasattr(data, "dict"):
        result = data.dict(exclude_unset=True)
    else:
        result = dict(data)

    for provider in CLOUD_PROVIDERS:
        plural = f"{provider}_api_keys"
        singular = f"{provider}_api_key"
        if plural in result or singular in result:
            keys = normalize_keys(result.get(plural, result.get(singular)))
            result[plural] = keys
            result[singular] = keys[0] if keys else ""

    default = result.get("default_text_provider")
    if default is not None:
        result["text_provider_order"] = provider_order(default, result.get("text_provider_order"))
    elif "text_provider_order" in result:
        order = [name for name in result["text_provider_order"] if name in ALL_TEXT_PROVIDERS]
        result["text_provider_order"] = list(dict.fromkeys(order))
    return result
