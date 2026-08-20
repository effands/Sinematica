"""Carry exact Casting Karakter ownership into generated storyboards."""

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Tuple

from .actor_references import actor_reference_paths, normalize_actor, resolve_character_actor


def select_actor_references(
    actor_ids: str,
    character_info: str,
    actors: Iterable[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]]]:
    wanted = {value.strip() for value in str(actor_ids or "").split(",") if value.strip()}
    selected = []
    lines = []
    for actor in actors or []:
        normalized = normalize_actor(actor)
        actor_id = str(normalized.get("id") or "")
        if actor_id not in wanted:
            continue
        item = {
            "id": actor_id,
            "name": normalized.get("name") or "",
            "seed": normalized.get("seed"),
            "description": normalized.get("description") or "",
            "paths": actor_reference_paths(normalized),
        }
        selected.append(item)
        lines.append(
            f"- source_actor_id={actor_id}; Nama={item['name']}; Seed={item['seed']}; "
            f"Deskripsi Fisik={item['description']}; jumlah referensi={len(item['paths'])}"
        )
    if not lines:
        return character_info, []
    appendix = (
        "\n\nDAFTAR AKTOR SPESIFIK (salin source_actor_id persis ke registry karakter):\n"
        + "\n".join(lines)
    )
    return f"{character_info}{appendix}", selected


def attach_character_references(
    storyboard: Dict[str, Any], selected: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    result = deepcopy(storyboard)
    selected_list = [dict(item) for item in selected or []]
    actors = [{"id": item["id"], "name": item.get("name") or ""} for item in selected_list]
    for character in result.get("characters") or []:
        actor = resolve_character_actor(character, actors)
        if actor:
            character["source_actor_id"] = str(actor["id"])
    result["character_references"] = {
        str(item["id"]): {
            "name": item.get("name") or "",
            "paths": list(item.get("paths") or []),
        }
        for item in selected_list
    }
    return result
