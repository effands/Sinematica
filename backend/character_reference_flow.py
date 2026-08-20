"""Resolve and upload only the Flow references owned by one character."""

from pathlib import Path
from typing import Any, Dict, Iterable, List


def _name(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def resolve_character_reference_paths(
    character: Dict[str, Any], storyboard: Dict[str, Any], *, require_exists: bool = True
) -> List[str]:
    mapping = storyboard.get("character_references") or {}
    source_id = str(character.get("source_actor_id") or "").strip()
    entry = mapping.get(source_id) if source_id else None
    if entry is None and not source_id:
        wanted = _name(character.get("name"))
        entry = next(
            (item for item in mapping.values() if _name((item or {}).get("name")) == wanted),
            None,
        ) if wanted else None
    paths = list(dict.fromkeys(str(path) for path in (entry or {}).get("paths") or [] if path))
    return [path for path in paths if not require_exists or Path(path).is_file()]


async def upload_character_references(
    bridge,
    paths: Iterable[str],
    project_id: str,
    instance_id: str,
    *,
    upload_fn=None,
) -> List[str]:
    if upload_fn is None:
        from omniflash.generators import upload_image
        upload_fn = upload_image
    media_ids = []
    for path in paths or []:
        if not Path(path).is_file():
            continue
        media_id = await upload_fn(
            bridge, path, project_id=project_id, instance_id=instance_id
        )
        if media_id:
            media_ids.append(media_id)
    return media_ids
