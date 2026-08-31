"""Direct, streamed media downloads that avoid large base64 WebSocket transfers."""

import asyncio
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, urlparse


_MEDIA_REDIRECT_ENDPOINT = "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect"


def _is_trusted_media_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or ""))
    except Exception:
        return False
    hostname = str(parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        hostname == "flow-content.google"
        or hostname.endswith(".googleusercontent.com")
        or hostname.endswith(".googlevideo.com")
        or hostname == "storage.googleapis.com"
    )


def _find_exact_url(value, media_id: str) -> str:
    if isinstance(value, str):
        if _is_trusted_media_url(value) and media_id.lower() in value.lower():
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
    # Flow's redirect route accepts the media UUID shown in thumbnail/video URLs.
    # The generation API may return either that UUID or a resource name such as
    # projects/{project}/media/{uuid}; passing the full resource name makes the
    # redirect route return a non-media response instead of the signed CDN URL.
    clean_id = str(media_id or "").strip().rstrip("/").rsplit("/", 1)[-1]
    if not clean_id:
        return ""
    url = f"{_MEDIA_REDIRECT_ENDPOINT}?name={quote(clean_id, safe='')}"
    result = await bridge.trpc_request(
        url,
        method="GET",
        body=None,
        timeout=20,
        instance_id=instance_id,
    )
    response_url = str((result or {}).get("responseUrl") or "")
    # An extension fetch that follows a cross-origin CDN redirect can surface an
    # opaque response with status 0. The final trusted URL is sufficient proof;
    # requiring HTTP 200 here incorrectly discards that usable signed URL.
    if _is_trusted_media_url(response_url):
        return response_url
    exact_url = _find_exact_url(result, clean_id)
    if exact_url:
        return exact_url
    status = int((result or {}).get("status") or 0)
    error = str((result or {}).get("error") or "").strip()
    if error or status >= 400:
        raise RuntimeError(
            f"Resolver Flow gagal (HTTP {status or 'unknown'}): {error or result}"
        )
    return ""


async def resolve_exact_media_url_with_retry(
    bridge, media_id: str, project_id: str = "", instance_id: str = None,
    *, attempts: int = 4, delay: float = 2.0,
) -> str:
    """Wait briefly for Flow to publish the signed CDN URL after a completed render."""
    for attempt in range(1, max(1, attempts) + 1):
        try:
            exact_url = await resolve_exact_media_url(bridge, media_id, project_id, instance_id)
        except Exception:
            exact_url = ""
        if exact_url:
            return exact_url
        if attempt < attempts:
            await asyncio.sleep(delay)
    return ""


async def stream_exact_media_with_retry(
    bridge,
    media_id: str,
    project_id: str,
    instance_id: str,
    destination: Path,
    *,
    attempts: int = 5,
    delay: float = 3.0,
    resolver=None,
    downloader=None,
) -> str:
    """Re-resolve and stream a completed Flow render after transient CDN 404s.

    Flow can publish the media record slightly before its first signed CDN URL is
    readable. Retrying that same signed URL only repeats the 404, so every attempt
    deliberately asks Flow for a fresh redirect before downloading again.
    """
    resolver = resolver or resolve_exact_media_url
    downloader = downloader or stream_download
    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            exact_url = await resolver(bridge, media_id, project_id, instance_id)
            if not exact_url:
                raise RuntimeError("URL CDN bertanda tangan belum dipublikasikan Flow.")
            await asyncio.to_thread(downloader, exact_url, destination)
            return exact_url
        except Exception as ex:
            last_error = ex
            if attempt < attempts:
                await asyncio.sleep(delay)
    if last_error:
        raise RuntimeError(
            f"URL media Flow sudah di-resolve ulang {attempts} kali tetapi belum dapat diunduh: {last_error}"
        ) from last_error
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
