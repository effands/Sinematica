"""Normalization, validation, and exact ownership for actor reference images."""

from typing import Any, Dict, Iterable, List, Optional


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_ACTOR_REFERENCE_IMAGES = 4
MAX_ACTOR_REFERENCE_BYTES = 10 * 1024 * 1024


def _normalized_name(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def normalize_actor(actor: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(actor or {})
    images = [dict(item) for item in (result.get("images") or []) if isinstance(item, dict) and item.get("path")]
    if not images and result.get("image_path"):
        images = [{
            "path": result["image_path"],
            "url": result.get("image_url") or "",
            "primary": True,
        }]
    for index, image in enumerate(images):
        image["primary"] = index == 0
    result["images"] = images
    if images:
        result["image_path"] = images[0]["path"]
        result["image_url"] = images[0].get("url") or ""
    return result


def actor_reference_paths(actor: Dict[str, Any]) -> List[str]:
    normalized = normalize_actor(actor)
    return list(dict.fromkeys(
        str(item["path"]) for item in normalized.get("images") or [] if item.get("path")
    ))


def resolve_character_actor(character: Dict[str, Any], actors: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    actor_list = list(actors or [])
    source_id = str(character.get("source_actor_id") or "").strip()
    if source_id:
        return next((actor for actor in actor_list if str(actor.get("id")) == source_id), None)
    wanted = _normalized_name(character.get("name"))
    if not wanted:
        return None
    return next((actor for actor in actor_list if _normalized_name(actor.get("name")) == wanted), None)


def validate_image_uploads(
    files: Iterable[Any],
    max_files: int = MAX_ACTOR_REFERENCE_IMAGES,
    max_bytes: int = MAX_ACTOR_REFERENCE_BYTES,
) -> None:
    uploads = [item for item in (files or []) if item and getattr(item, "filename", None)]
    if not uploads:
        raise ValueError("Minimal satu gambar referensi karakter wajib diunggah.")
    if len(uploads) > max_files:
        raise ValueError(f"Setiap karakter maksimal {max_files} gambar referensi.")
    for item in uploads:
        if str(getattr(item, "content_type", "")).casefold() not in ALLOWED_IMAGE_TYPES:
            raise ValueError("Format gambar harus JPEG, PNG, atau WebP.")
        stream = item.file
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        if size > max_bytes:
            raise ValueError("Ukuran setiap gambar referensi maksimal 10 MB.")
