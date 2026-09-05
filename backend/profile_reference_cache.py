"""Profile-owned Flow media IDs backed by durable local reference files."""

from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Tuple


ProfileKey = Tuple[str, str]
UploadFn = Callable[..., Awaitable[str]]


def profile_key(instance_id: str, project_id: str) -> ProfileKey:
    return (str(instance_id or ""), str(project_id or ""))


def character_aliases(character: Dict[str, Any], index: int) -> List[Any]:
    char_id = character.get("id", index)
    name = str(character.get("name") or f"Karakter {char_id}")
    return [char_id, str(char_id), name, name.lower()]


def local_character_path(character: Dict[str, Any], index: int, paths: Dict[Any, str]) -> str:
    for alias in character_aliases(character, index):
        candidate = str(paths.get(alias) or "")
        if candidate and Path(candidate).is_file():
            return candidate
    return ""


async def ensure_character_media_for_profile(
    bridge,
    characters: Iterable[Dict[str, Any]],
    local_paths: Dict[Any, str],
    project_id: str,
    instance_id: str,
    cache: Dict[ProfileKey, Dict[Any, str]],
    *,
    upload_fn: UploadFn,
) -> Tuple[Dict[Any, str], List[str]]:
    """Upload each local sheet once per Flow profile/project and return its alias map."""
    key = profile_key(instance_id, project_id)
    media_map = cache.setdefault(key, {})
    uploaded_names = []
    for index, character in enumerate(characters or [], 1):
        aliases = character_aliases(character, index)
        if next((media_map.get(alias) for alias in aliases if media_map.get(alias)), None):
            continue
        path = local_character_path(character, index, local_paths)
        if not path:
            raise RuntimeError(
                f"Character sheet lokal '{character.get('name') or aliases[0]}' tidak tersedia; "
                "referensi tidak boleh memakai media ID milik profil lain."
            )
        media_id = await upload_fn(
            bridge, path, project_id=project_id, instance_id=instance_id
        )
        if not media_id:
            raise RuntimeError(f"Flow tidak mengembalikan media ID untuk {Path(path).name}.")
        for alias in aliases:
            media_map[alias] = media_id
        uploaded_names.append(str(character.get("name") or aliases[0]))
    return media_map, uploaded_names


async def ensure_files_for_profile(
    bridge,
    paths: Iterable[str],
    project_id: str,
    instance_id: str,
    cache: Dict[ProfileKey, Dict[str, str]],
    *,
    upload_fn: UploadFn,
) -> Tuple[List[str], int]:
    """Upload arbitrary local references once per Flow profile/project, preserving order."""
    key = profile_key(instance_id, project_id)
    media_map = cache.setdefault(key, {})
    result = []
    uploaded = 0
    for raw_path in paths or []:
        path = str(Path(raw_path).resolve())
        if not Path(path).is_file():
            continue
        media_id = media_map.get(path)
        if not media_id:
            media_id = await upload_fn(
                bridge, path, project_id=project_id, instance_id=instance_id
            )
            if not media_id:
                raise RuntimeError(f"Flow tidak mengembalikan media ID untuk {Path(path).name}.")
            media_map[path] = media_id
            uploaded += 1
        result.append(media_id)
    return result, uploaded
