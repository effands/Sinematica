"""Sinematica Backend — ExtensionBridge Singleton Manager."""

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

from . import settings

if str(settings.ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(settings.ENGINE_DIR))

from omniflash import ExtensionBridge

_bridge: Optional[ExtensionBridge] = None


async def init_bridge() -> ExtensionBridge:
    global _bridge
    if _bridge is None:
        _bridge = ExtensionBridge()
    cfg = settings.get_settings()
    _bridge.set_preferred_instance(cfg.get("preferred_instance_id"))
    return _bridge


async def close_bridge() -> None:
    global _bridge
    _bridge = None


def get_bridge() -> ExtensionBridge:
    global _bridge
    if _bridge is None:
        _bridge = ExtensionBridge()
        cfg = settings.get_settings()
        _bridge.set_preferred_instance(cfg.get("preferred_instance_id"))
    return _bridge


def status_snapshot() -> dict:
    if _bridge is None:
        return {"state": "starting", "extension_connected": False, "logged_in": False, "instances": []}

    instances = _bridge.instance_snapshot()
    any_connected = len(instances) > 0
    any_logged_in = any(i["logged_in"] for i in instances)
    any_ready = any(i.get("ready", True) and i["logged_in"] for i in instances)

    if any_connected and any_ready:
        state = "ready"
    elif any_connected:
        state = "connected_no_login"
    else:
        state = "disconnected"

    return {
        "state": state,
        "extension_connected": any_connected,
        "logged_in": any_logged_in,
        "active_instance_id": _bridge.active_instance_id,
        "instances": instances,
        "total_connected_profiles": len(instances),
    }


async def ensure_ready(timeout: float = 30, poll_interval: float = 0.5) -> None:
    """Wait through short extension reconnects until a profile is genuinely usable."""
    get_bridge()
    deadline = time.monotonic() + max(0, timeout)
    while True:
        if status_snapshot()["state"] == "ready":
            return
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(max(0, poll_interval))
    raise RuntimeError(
        "Belum ada Chrome extension Flow Agent yang terhubung atau ter-login. "
        "Pastikan extension dimuat di Chrome (chrome://extensions) dan profil ter-login di flow.google.com."
    )
