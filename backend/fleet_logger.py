"""Sinematica Backend — Fleet Structured Logger.
Persists structured Chrome Extension agent logs to dated files and memory ring buffer.
"""

from collections import deque
import datetime
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

log = logging.getLogger("sinematica.fleet_logger")

_RECENT_FLEET_LOGS: deque = deque(maxlen=200)


def get_default_log_dir() -> Path:
    from backend import settings
    log_dir = settings.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def record_fleet_log(entry: Dict[str, Any], log_dir: Optional[Path] = None) -> None:
    if not isinstance(entry, dict):
        return

    _RECENT_FLEET_LOGS.append(entry)

    target_dir = log_dir or get_default_log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = target_dir / f"flow_fleet_{today_str}.log"

    ts = entry.get("timestamp", datetime.datetime.now().isoformat())
    level = str(entry.get("level", "INFO")).upper()
    tag = str(entry.get("tag", "GENERAL")).upper()
    msg = str(entry.get("message", ""))
    inst = str(entry.get("instance_id", "unknown"))

    meta = entry.get("meta")
    meta_str = f" | meta={json.dumps(meta)}" if meta else ""

    line = f"[{ts}] [{level}] [{inst}] [{tag}] {msg}{meta_str}\n"

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as ex:
        log.warning("Gagal menulis log fleet ke %s: %s", log_file, ex)


def get_recent_fleet_logs(limit: int = 50) -> List[Dict[str, Any]]:
    return list(_RECENT_FLEET_LOGS)[-limit:]


def clear_fleet_logs() -> None:
    _RECENT_FLEET_LOGS.clear()
