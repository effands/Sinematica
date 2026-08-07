"""Sinematica — ExtensionBridge with Multi-Profile Fleet Support.

WebSocket bridge routing requests across multiple connected Chrome extension instances.
"""

import asyncio
import json
import logging
import random
import time
import uuid

from .config import API_REQUEST_TIMEOUT, MAX_CONCURRENT_REQUESTS, REQUEST_MIN_INTERVAL

log = logging.getLogger("sinematica.engine.bridge")


def _is_ws_connected(ws) -> bool:
    """Check if a WebSocket object is active and connected."""
    if ws is None:
        return False
    if hasattr(ws, "client_state"):
        try:
            from starlette.websockets import WebSocketState
            return ws.client_state == WebSocketState.CONNECTED
        except Exception:
            val = getattr(ws.client_state, "value", None)
            name = getattr(ws.client_state, "name", "")
            return val == 1 or name == "CONNECTED"
    if hasattr(ws, "closed"):
        return not ws.closed
    return True


class ExtensionBridge:
    """WebSocket bridge that multiple Chrome extensions connect to."""

    def __init__(self):
        self._ws = None
        self._instances: dict[str, dict] = {}
        self._preferred_instance_id: str | None = None
        self.active_instance_id: str | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._flow_key = None
        self._connected = asyncio.Event()
        self._rr_idx = 0
        self._seen_ids: dict[str, bool] = {}
        self._rate_sem: asyncio.Semaphore | None = None
        self._rate_lock: asyncio.Lock | None = None
        self._last_request_at: float = 0.0

    def _get_rate_limit(self):
        if self._rate_sem is None:
            self._rate_sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            self._rate_lock = asyncio.Lock()
        return self._rate_sem, self._rate_lock

    def set_preferred_instance(self, instance_id: str | None):
        """Select a preferred Chrome profile instance or None for load-balancing across all."""
        self._preferred_instance_id = (instance_id or "").strip() or None
        selected = self._instances.get(self._preferred_instance_id) if self._preferred_instance_id else None
        if selected and _is_ws_connected(selected.get("ws")):
            self._activate_instance(self._preferred_instance_id, selected)
        elif self._preferred_instance_id:
            self._ws = None
            self._flow_key = None
            self.active_instance_id = None
            self._connected.clear()

    def _activate_instance(self, instance_id: str, entry: dict):
        self.active_instance_id = instance_id
        self._ws = entry["ws"]
        self._flow_key = entry.get("flow_key")
        if self._flow_key:
            self._connected.set()
        else:
            self._connected.clear()

    def register_instance(self, instance_id: str, ws, instance_name: str = None, project_id: str = None):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            instance_id = f"profile-{uuid.uuid4().hex[:6]}"
        previous = self._instances.get(instance_id, {})
        entry = {
            "instance_id": instance_id,
            "ws": ws,
            "name": (instance_name or previous.get("name") or f"Profile {instance_id[:6]}").strip(),
            "flow_key": previous.get("flow_key"),
            "project_id": project_id or previous.get("project_id"),
            "last_active": time.time(),
            "busy": False
        }
        self._instances[instance_id] = entry
        log.info("Registered Chrome extension profile instance: %s (%s)", entry["name"], instance_id)
        if instance_id == self._preferred_instance_id:
            self._activate_instance(instance_id, entry)
        elif self._preferred_instance_id is None and (self._ws is None or not _is_ws_connected(self._ws)):
            self._activate_instance(instance_id, entry)
        return entry

    def unregister_instance(self, instance_id: str, ws):
        entry = self._instances.get(instance_id)
        if not entry or entry.get("ws") is not ws:
            return
        self._instances.pop(instance_id, None)
        log.info("Unregistered Chrome extension profile instance: %s", instance_id)
        if self.active_instance_id == instance_id and self._ws is ws:
            self._ws = None
            self._flow_key = None
            self.active_instance_id = None
            self._connected.clear()

    def remove_ws_reference(self, ws):
        """Purge any dead WebSocket object from instances."""
        if ws is None:
            return
        to_remove = []
        for iid, entry in list(self._instances.items()):
            if entry.get("ws") is ws or not _is_ws_connected(entry.get("ws")):
                to_remove.append(iid)
        for iid in to_remove:
            entry = self._instances.pop(iid, None)
            if entry:
                log.info("Purged dead Chrome extension instance: %s (%s)", entry.get("name"), iid)
        if self._ws is ws or not _is_ws_connected(self._ws):
            self._ws = None
            self._flow_key = None
            self.active_instance_id = None
            self._connected.clear()

    def cleanup_dead_instances(self):
        """Sweep and remove all closed WebSocket instances."""
        dead_ids = [iid for iid, e in self._instances.items() if not _is_ws_connected(e.get("ws"))]
        for iid in dead_ids:
            entry = self._instances.pop(iid, None)
            if entry:
                log.info("Cleaned up dead WebSocket profile instance: %s (%s)", entry.get("name"), iid)
        if self._ws and not _is_ws_connected(self._ws):
            self._ws = None
            self._flow_key = None
            self.active_instance_id = None
            self._connected.clear()

    def record_instance_token(self, instance_id: str, flow_key: str):
        entry = self._instances.get(instance_id)
        if entry is not None:
            entry["flow_key"] = flow_key
            entry["last_active"] = time.time()
        if instance_id == self.active_instance_id or self.active_instance_id is None:
            self._flow_key = flow_key
            if flow_key:
                self._connected.set()

    def update_instance_project(self, instance_id: str, project_id: str):
        entry = self._instances.get(instance_id)
        if entry:
            entry["project_id"] = project_id

    def instance_snapshot(self) -> list[dict]:
        self.cleanup_dead_instances()
        res = []
        for iid, entry in self._instances.items():
            res.append({
                "instance_id": iid,
                "name": entry.get("name"),
                "connected": entry.get("ws") is not None and _is_ws_connected(entry["ws"]),
                "logged_in": bool(entry.get("flow_key")),
                "project_id": entry.get("project_id"),
                "is_active": iid == self.active_instance_id,
                "is_preferred": iid == self._preferred_instance_id,
            })
        return res

    def _get_target_ws_with_entry(self, specific_instance_id: str = None):
        self.cleanup_dead_instances()

        if specific_instance_id and specific_instance_id in self._instances:
            entry = self._instances[specific_instance_id]
            if entry.get("ws") and _is_ws_connected(entry["ws"]):
                return entry["ws"], entry

        if self._preferred_instance_id:
            entry = self._instances.get(self._preferred_instance_id)
            if entry and entry.get("ws") and _is_ws_connected(entry["ws"]):
                return entry["ws"], entry

        available = [e for e in self._instances.values() if e.get("ws") and _is_ws_connected(e["ws"])]
        if available:
            entry = available[self._rr_idx % len(available)]
            self._rr_idx += 1
            return entry["ws"], entry

        if self._ws and _is_ws_connected(self._ws):
            return self._ws, None

        return None, None

    async def api_request(self, endpoint: str, body: dict, instance_id: str = None, timeout: float = API_REQUEST_TIMEOUT, _retry_count: int = 0) -> dict:
        sem, lock = self._get_rate_limit()
        async with sem:
            async with lock:
                now = time.time()
                elapsed = now - self._last_request_at
                if elapsed < REQUEST_MIN_INTERVAL:
                    await asyncio.sleep(REQUEST_MIN_INTERVAL - elapsed)
                self._last_request_at = time.time()

            req_id = str(uuid.uuid4())
            ws, entry = self._get_target_ws_with_entry(instance_id)

            if not ws:
                raise RuntimeError("Tidak ada profil Chrome Extension yang terhubung/siap untuk memproses request Flow.")

            target_instance_id = entry["instance_id"] if entry else self.active_instance_id
            flow_key = entry.get("flow_key") if entry else self._flow_key

            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            self._pending[req_id] = fut

            msg = {
                "type": "api_request",
                "id": req_id,
                "endpoint": endpoint,
                "body": body,
                "flow_key": flow_key,
                "instance_id": target_instance_id
            }

            try:
                if hasattr(ws, "send_str"):
                    await ws.send_str(json.dumps(msg))
                elif hasattr(ws, "send_text"):
                    await ws.send_text(json.dumps(msg))
                elif hasattr(ws, "send"):
                    await ws.send(json.dumps(msg))
                else:
                    raise RuntimeError("Unsupported WebSocket object type")
            except Exception as ex:
                self._pending.pop(req_id, None)
                self.remove_ws_reference(ws)

                # Automatic failover retry if another profile is available
                if _retry_count < 3:
                    alt_ws, alt_entry = self._get_target_ws_with_entry(None)
                    if alt_ws and alt_ws is not ws:
                        alt_id = alt_entry.get("instance_id") if alt_entry else None
                        log.warning("Profil Chrome %s terputus (%s). Otomatis dialihkan ke %s...",
                                    target_instance_id, ex, alt_entry.get("name") if alt_entry else "profil lain")
                        return await self.api_request(endpoint, body, instance_id=alt_id, timeout=timeout, _retry_count=_retry_count + 1)

                raise RuntimeError(f"Gagal mengirim pesan ke extension Chrome ({target_instance_id}): {ex}")

            try:
                res = await asyncio.wait_for(fut, timeout=timeout)
                return res
            except asyncio.TimeoutError:
                self._pending.pop(req_id, None)
                raise RuntimeError(f"Request ke Google Flow via Chrome ({target_instance_id}) mengalami timeout ({timeout}s)")

    def handle_message(self, data_str: str, ws, instance_id: str = None):
        try:
            msg = json.loads(data_str)
        except Exception:
            return

        msg_type = msg.get("type")

        if msg_type == "register":
            iid = msg.get("instance_id") or instance_id or f"profile-{uuid.uuid4().hex[:6]}"
            name = msg.get("name") or f"Chrome Profile {iid[:6]}"
            project_id = msg.get("project_id")
            self.register_instance(iid, ws, name, project_id)
            if msg.get("flow_key"):
                self.record_instance_token(iid, msg["flow_key"])

        elif msg_type == "token_captured":
            iid = msg.get("instance_id") or self.active_instance_id
            flow_key = msg.get("flow_key")
            if iid and flow_key:
                self.record_instance_token(iid, flow_key)

        elif msg_type == "api_response":
            req_id = msg.get("id")
            if req_id and req_id in self._pending:
                fut = self._pending.pop(req_id)
                if not fut.done():
                    fut.set_result(msg)

    async def wait_for_extension(self, timeout: float = 15, max_retries: int = 1) -> bool:
        start_t = time.time()
        while time.time() - start_t < timeout:
            if any(_is_ws_connected(e.get("ws")) for e in self._instances.values()):
                return True
            await asyncio.sleep(0.5)
        return False
