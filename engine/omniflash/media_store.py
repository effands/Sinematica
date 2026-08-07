"""Media store for saving uploaded image IDs."""
import json
import os
from .config import MEDIA_ID_FILE

_cache = {}

def save(filename: str, media_id: str):
    _cache[filename] = media_id
    try:
        data = {}
        if os.path.exists(MEDIA_ID_FILE):
            try:
                with open(MEDIA_ID_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content.startswith("window."):
                        json_str = content.split("=", 1)[1].rstrip(";")
                        data = json.loads(json_str)
            except Exception:
                data = {}
        data[filename] = media_id
        with open(MEDIA_ID_FILE, "w", encoding="utf-8") as f:
            f.write(f"window.MEDIA_IDS = {json.dumps(data, indent=2)};")
    except Exception:
        pass

def get(filename: str) -> str | None:
    return _cache.get(filename)
