"""Direct, streamed media downloads that avoid large base64 WebSocket transfers."""

import asyncio
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, urlparse


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
    # Ensure media_id is fully qualified as projects/{project}/media/{id}
    full_name = media_id
    if not full_name.startswith("projects/") and project_id:
        clean_id = media_id.rsplit("/", 1)[-1]
        full_name = f"projects/{project_id}/media/{clean_id}"
        
    url = f"{_MEDIA_REDIRECT_ENDPOINT}?name={quote(str(full_name), safe='')}"
    result = await bridge.trpc_request(
        url,
        method="GET",
        body=None,
        timeout=20,
        instance_id=instance_id,
    )
    response_url = str((result or {}).get("responseUrl") or "")
    parsed = urlparse(response_url)
    if int((result or {}).get("status") or 0) == 200 and parsed.scheme == "https" and (
        parsed.hostname == "flow-content.google"
        or str(parsed.hostname or "").endswith(".googleusercontent.com")
    ):
        return response_url
    return _find_exact_url(result, media_id)


async def resolve_exact_media_url_with_retry(
    bridge, media_id: str, project_id: str = "", instance_id: str = None,
    *, attempts: int = 4, delay: float = 2.0,
) -> str:
    """Wait briefly for Flow to publish the signed CDN URL after a completed render."""
    for attempt in range(1, max(1, attempts) + 1):
        exact_url = await resolve_exact_media_url(bridge, media_id, project_id, instance_id)
        if exact_url:
            return exact_url
        if attempt < attempts:
            await asyncio.sleep(delay)
    return ""


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
