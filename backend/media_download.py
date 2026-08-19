"""Direct, streamed media downloads that avoid large base64 WebSocket transfers."""

from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote


_MEDIA_REDIRECT_ENDPOINT = "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect"


def _find_exact_url(value, media_id: str) -> str:
    if isinstance(value, str):
        if value.startswith(("https://", "http://")) and media_id.lower() in value.lower():
            return value
        return ""
    if isinstance(value, dict):
        for nested in value.values():
            found = _find_exact_url(nested, media_id)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _find_exact_url(nested, media_id)
            if found:
                return found
    return ""


async def resolve_exact_media_url(
    bridge, media_id: str, project_id: str = "", instance_id: str = None
) -> str:
    """Resolve the exact signed Flow URL using Affilia's proven silent tRPC route."""
    url = f"{_MEDIA_REDIRECT_ENDPOINT}?name={quote(str(media_id), safe='')}"
    result = await bridge.trpc_request(
        url,
        method="GET",
        body=None,
        timeout=20,
        instance_id=instance_id,
    )
    return _find_exact_url(result, media_id)


def stream_download(
    url: str,
    destination: Path,
    *,
    opener: Optional[Callable] = None,
    timeout: int = 120,
) -> int:
    """Stream an HTTP response atomically to disk and return the byte count."""
    if opener is None:
        import requests
        opener = requests.get

    destination = Path(destination)
    partial = destination.with_suffix(destination.suffix + ".part")
    total = 0
    try:
        response = opener(
            url,
            stream=True,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        content_type = str(response.headers.get("content-type", "")).lower()
        if content_type and "video" not in content_type and "octet-stream" not in content_type:
            raise RuntimeError(f"Respons unduhan bukan video ({content_type}).")
        with partial.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
                    total += len(chunk)
        if total == 0:
            raise RuntimeError("Respons unduhan video kosong.")
        partial.replace(destination)
        return total
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
