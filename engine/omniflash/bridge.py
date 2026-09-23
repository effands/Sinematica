"""Sinematica — ExtensionBridge with Multi-Profile Fleet Support.

WebSocket bridge routing requests across multiple connected Chrome extension instances.
"""

import asyncio
import base64
import json
import logging
import random
import time
import uuid

from .config import API_REQUEST_TIMEOUT, MAX_CONCURRENT_REQUESTS, REQUEST_MIN_INTERVAL

log = logging.getLogger("sinematica.engine.bridge")

_ROUTABLE_BRIDGE_MESSAGES = frozenset({
    "api_response",
    "trpc_response",
    "task_response",
    "download_response",
    "download_start",
    "download_chunk",
    "download_complete",
})


def is_routable_bridge_message(message_type: str) -> bool:
    """Return whether a WebSocket payload belongs to a pending bridge request."""
    return message_type in _ROUTABLE_BRIDGE_MESSAGES


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
        self._download_chunks: dict[str, dict] = {}
        self._flow_key = None
        self._connected = asyncio.Event()
        self._rr_idx = 0
        self._seen_ids: dict[str, bool] = {}
        self._rate_sem: asyncio.Semaphore | None = None
        self._rate_lock: asyncio.Lock | None = None
        self._last_request_at: float = 0.0
        self._last_api_auth_mode: str | None = None
        self._last_api_status: int | None = None
        self._progress_listeners: list = []

    def add_progress_listener(self, callback):
        """Register a callback for real-time Chrome Extension automation progress events."""
        if callback not in self._progress_listeners:
            self._progress_listeners.append(callback)

    def remove_progress_listener(self, callback):
        """Remove a previously registered progress callback."""
        if callback in self._progress_listeners:
            self._progress_listeners.remove(callback)

    def _notify_progress(self, msg: dict):
        for cb in list(self._progress_listeners):
            try:
                cb(msg)
            except Exception as ex:
                log.warning("Error executing progress listener: %s", ex)

    def _get_rate_limit(self):
        if self._rate_sem is None:
            self._rate_sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            self._rate_lock = asyncio.Lock()
        return self._rate_sem, self._rate_lock

    def set_preferred_instance(self, instance_id: str | None):
        """Select a preferred Chrome profile instance or None for load-balancing across all."""
        self._preferred_instance_id = (instance_id or "").strip() or None
        selected = self._instances.get(self._preferred_instance_id) if self._preferred_instance_id else None
        if selected and selected.get("ready", True) and _is_ws_connected(selected.get("ws")):
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
        if self._flow_key and entry.get("ready", True):
            self._connected.set()
        else:
            self._connected.clear()

    def register_instance(
        self, instance_id: str, ws, instance_name: str = None, project_id: str = None,
        ready: bool = True, readiness_error: str = None, version: str = None, session_ready: bool = False,
        credits=None,
    ):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            instance_id = f"profile-{uuid.uuid4().hex[:6]}"
        previous = self._instances.get(instance_id, {})
        entry = {
            "instance_id": instance_id,
            "ws": ws,
            "name": (instance_name or previous.get("name") or f"Profile {instance_id[:6]}").strip(),
            "flow_key": previous.get("flow_key"),
            "session_ready": bool(session_ready) or previous.get("session_ready", False),
            "project_id": project_id or previous.get("project_id"),
            "ready": bool(ready),
            "readiness_error": readiness_error,
            "version": version or previous.get("version"),
            "last_api_auth_mode": previous.get("last_api_auth_mode"),
            "last_api_status": previous.get("last_api_status"),
            "credits": credits if credits is not None else previous.get("credits"),
            "last_active": time.time(),
            "busy": False
        }
        self._instances[instance_id] = entry
        log.info("Registered Chrome extension profile instance: %s (%s)", entry["name"], instance_id)
        if entry.get("ready", True) and (
            instance_id == self._preferred_instance_id or instance_id == self.active_instance_id
        ):
            self._activate_instance(instance_id, entry)
        elif entry.get("ready", True) and self._preferred_instance_id is None and (
            self._ws is None or not _is_ws_connected(self._ws)
        ):
            self._activate_instance(instance_id, entry)
        elif not entry.get("ready", True) and instance_id == self.active_instance_id:
            self._ws = None
            self._flow_key = None
            self.active_instance_id = None
            self._connected.clear()
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

    def record_instance_token(self, instance_id: str, flow_key: str | None):
        entry = self._instances.get(instance_id)
        if entry is not None:
            entry["flow_key"] = flow_key
            entry["last_active"] = time.time()
        if instance_id == self.active_instance_id or self.active_instance_id is None:
            self._flow_key = flow_key
            if flow_key and (entry is None or entry.get("ready", True)):
                self._connected.set()
            elif not flow_key:
                self._connected.clear()

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
                "logged_in": bool(entry.get("flow_key") or entry.get("session_ready")),
                "oauth_ready": bool(entry.get("flow_key")),
                "session_ready": bool(entry.get("session_ready")),
                "project_id": entry.get("project_id"),
                "ready": bool(entry.get("ready", True)),
                "readiness_error": entry.get("readiness_error"),
                "version": entry.get("version", "1.3.8"),
                "last_api_auth_mode": entry.get("last_api_auth_mode"),
                "last_api_status": entry.get("last_api_status"),
                "last_ui_auth_summary": entry.get("last_ui_auth_summary"),
                "credits": entry.get("credits"),
                "is_active": iid == self.active_instance_id,
                "is_preferred": iid == self._preferred_instance_id,
            })
        return res

    def _get_target_ws_with_entry(self, specific_instance_id: str = None):
        self.cleanup_dead_instances()

        if specific_instance_id and specific_instance_id in self._instances:
            entry = self._instances[specific_instance_id]
            if entry.get("ready", True) and entry.get("ws") and _is_ws_connected(entry["ws"]):
                return entry["ws"], entry

        if self._preferred_instance_id:
            entry = self._instances.get(self._preferred_instance_id)
            if entry and entry.get("ready", True) and entry.get("ws") and _is_ws_connected(entry["ws"]):
                return entry["ws"], entry

        available = [
            e for e in self._instances.values()
            if e.get("ready", True) and e.get("ws") and _is_ws_connected(e["ws"])
        ]
        if available:
            entry = available[self._rr_idx % len(available)]
            self._rr_idx += 1
            return entry["ws"], entry

        active_entry = self._instances.get(self.active_instance_id)
        if self._ws and _is_ws_connected(self._ws) and (
            active_entry is None or active_entry.get("ready", True)
        ):
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

    async def download_url(self, url: str, instance_id: str = None, timeout: float = 180) -> dict:
        """Download private Flow media inside the authenticated Chrome tab."""
        req_id = str(uuid.uuid4())
        ws, entry = self._get_target_ws_with_entry(instance_id)
        if not ws:
            raise RuntimeError("Tidak ada profil Chrome Extension untuk mengunduh media Flow.")

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut
        message = {
            "type": "download_request",
            "id": req_id,
            "url": url,
            "instance_id": entry.get("instance_id") if entry else self.active_instance_id,
        }
        try:
            payload = json.dumps(message)
            if hasattr(ws, "send_str"):
                await ws.send_str(payload)
            elif hasattr(ws, "send_text"):
                await ws.send_text(payload)
            else:
                await ws.send(payload)
            result = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as ex:
            self._pending.pop(req_id, None)
            self._download_chunks.pop(req_id, None)
            raise RuntimeError(
                f"Unduhan media Flow via Chrome ({entry.get('name') if entry else instance_id}) "
                f"timeout setelah {timeout}s; render tetap tersimpan di Flow."
            ) from ex
        except Exception:
            self._pending.pop(req_id, None)
            self._download_chunks.pop(req_id, None)
            raise

        status = int(result.get("status") or 0)
        if status != 200 or not result.get("data_base64"):
            raise RuntimeError(result.get("error") or f"Unduhan media Flow gagal (HTTP {status})")
        return {
            "data": base64.b64decode(result["data_base64"]),
            "content_type": result.get("content_type") or "application/octet-stream",
        }

    async def execute_task(
        self, task_payload: dict, instance_id: str = None, timeout: float = 300,
    ) -> dict:
        """Dispatch a high-level UI automation task to the Chrome extension and await its completion."""
        req_id = str(uuid.uuid4())
        ws, entry = self._get_target_ws_with_entry(instance_id)

        if not ws:
            raise RuntimeError("Tidak ada profil Chrome Extension yang terhubung untuk menjalankan task Google Flow.")

        target_instance_id = entry["instance_id"] if entry else self.active_instance_id
        project_id = entry.get("project_id") if entry else None

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut

        payload = dict(task_payload)
        payload.setdefault("taskId", req_id)
        if project_id and not payload.get("projectId"):
            payload["projectId"] = project_id

        msg = {
            "type": "execute_task",
            "id": req_id,
            "params": payload,
            "instance_id": target_instance_id,
        }

        try:
            raw = json.dumps(msg)
            if hasattr(ws, "send_str"):
                await ws.send_str(raw)
            elif hasattr(ws, "send_text"):
                await ws.send_text(raw)
            elif hasattr(ws, "send"):
                await ws.send(raw)
            else:
                raise RuntimeError("Unsupported WebSocket object type")
        except Exception as ex:
            self._pending.pop(req_id, None)
            self.remove_ws_reference(ws)
            raise RuntimeError(f"Gagal mengirim task ke Chrome Extension ({target_instance_id}): {ex}")

        try:
            res = await asyncio.wait_for(fut, timeout=timeout)
            return res
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"Task Google Flow via Chrome ({target_instance_id}) mengalami timeout ({timeout}s)")

    async def harvest_project_videos(
        self, instance_id: str = None, project_id: str = None, timeout: float = 60
    ) -> dict:
        """Harvest all rendered videos from the Google Flow canvas in chronological order."""
        ws, entry = self._get_target_ws_with_entry(instance_id)
        if not ws:
            raise RuntimeError("Tidak ada profil Chrome Extension yang terhubung untuk mengambil video kanvas Flow.")

        target_instance_id = entry["instance_id"] if entry else self.active_instance_id
        target_project_id = project_id or (entry.get("project_id") if entry else None)

        try:
            res = await self.api_request(
                "/internal/harvest_project_videos",
                {"projectId": target_project_id},
                instance_id=target_instance_id,
                timeout=timeout,
            )
            data = res.get("data", {})
            if isinstance(data, dict) and "videos" in data:
                return data
            if isinstance(res, dict) and "videos" in res:
                return res
        except Exception as api_err:
            log.warning("Harvest via api_request failed (%s), trying execute_task fallback...", api_err)

        task_res = await self.execute_task(
            {
                "action": "FLOW_HARVEST_PROJECT_VIDEOS",
                "projectId": target_project_id,
            },
            instance_id=target_instance_id,
            timeout=timeout,
        )
        return task_res.get("data") or task_res.get("result") or task_res

    async def trpc_request(
        self, url: str, method: str = "POST", headers: dict = None, body=None,
        timeout: float = 20, instance_id: str = None,
    ) -> dict:
        """Run a silent authenticated Flow tRPC request in the selected Chrome profile."""
        req_id = str(uuid.uuid4())
        ws, entry = self._get_target_ws_with_entry(instance_id)
        if not ws:
            return {"error": "Extension not connected"}
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut
        message = {
            "type": "trpc_request",
            "id": req_id,
            "params": {
                "url": url,
                "method": method,
                "headers": headers or {},
                "body": body,
            },
        }
        try:
            payload = json.dumps(message)
            if hasattr(ws, "send_str"):
                await ws.send_str(payload)
            elif hasattr(ws, "send_text"):
                await ws.send_text(payload)
            else:
                await ws.send(payload)
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return {"error": "TIMEOUT"}
        finally:
            self._pending.pop(req_id, None)

    async def download_url_with_retry(
        self, url: str, instance_id: str = None, timeout: float = 180,
        attempts: int = 2, delay: float = 1.0,
    ) -> dict:
        """Retry only the authenticated download; the completed Flow render is reused."""
        last_error = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                return await self.download_url(url, instance_id=instance_id, timeout=timeout)
            except Exception as ex:
                last_error = ex
                if attempt < attempts:
                    log.warning("Unduhan Flow gagal (%s/%s): %s. Mengulang unduhan yang sama...", attempt, attempts, ex)
                    await asyncio.sleep(delay)
        raise RuntimeError(f"Unduhan media Flow gagal setelah {attempts} percobaan: {last_error}") from last_error

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
            self.register_instance(
                iid, ws, name, project_id,
                ready=msg.get("ready", True),
                readiness_error=msg.get("readiness_error"),
                credits=msg.get("credits"),
            )
            if "flow_key" in msg:
                self.record_instance_token(iid, msg.get("flow_key"))

        elif msg_type == "token_captured":
            iid = msg.get("instance_id") or self.active_instance_id
            flow_key = msg.get("flow_key")
            if iid and flow_key:
                self.record_instance_token(iid, flow_key)

        elif msg_type == "flow_ui_request_meta":
            iid = msg.get("instance_id") or instance_id or self.active_instance_id
            entry = self._instances.get(iid)
            summary = {
                "has_authorization": bool(msg.get("has_authorization")),
                "has_bearer": bool(msg.get("has_bearer")),
                "has_cookie": bool(msg.get("has_cookie")),
                "header_names": sorted(set(str(x).lower() for x in (msg.get("header_names") or []))),
            }
            if entry is not None:
                entry["last_ui_auth_summary"] = summary
            log.info("Flow UI auth metadata instance=%s summary=%s", iid, summary)

        elif msg_type == "download_start":
            req_id = msg.get("id")
            total = int(msg.get("total_chunks") or 0)
            if req_id in self._pending and total > 0:
                self._download_chunks[req_id] = {
                    "chunks": [None] * total,
                    "content_type": msg.get("content_type") or "application/octet-stream",
                    "status": int(msg.get("status") or 200),
                }

        elif msg_type == "download_chunk":
            req_id = msg.get("id")
            transfer = self._download_chunks.get(req_id)
            index = int(msg.get("index") or 0)
            if transfer and 0 <= index < len(transfer["chunks"]):
                transfer["chunks"][index] = base64.b64decode(msg.get("data_base64") or "")

        elif msg_type == "download_complete":
            req_id = msg.get("id")
            transfer = self._download_chunks.pop(req_id, None)
            fut = self._pending.pop(req_id, None)
            if fut and not fut.done():
                if not transfer or any(chunk is None for chunk in transfer["chunks"]):
                    fut.set_result({"status": 500, "error": "Transfer MP4 tidak lengkap dari Chrome."})
                else:
                    joined = b"".join(transfer["chunks"])
                    fut.set_result({
                        "status": int(msg.get("status") or transfer["status"]),
                        "content_type": transfer["content_type"],
                        "data_base64": base64.b64encode(joined).decode("ascii"),
                    })

        elif msg_type in ("task_progress", "flow_progress"):
            self._notify_progress(msg)
            stage = msg.get("stage", "FLOW")
            message = msg.get("message", "")
            if message:
                log.info("[%s] [%s] %s", str(msg.get("id", "task"))[:8], stage, message)

        elif msg_type in ("api_response", "download_response", "trpc_response", "task_response"):
            req_id = msg.get("id")
            if req_id and req_id in self._pending:
                fut = self._pending.pop(req_id)
                if msg_type == "api_response":
                    auth_mode = msg.get("auth_mode") or "unknown"
                    status = msg.get("status")
                    target_entry = self._instances.get(instance_id or self.active_instance_id)
                    if target_entry is not None:
                        target_entry["last_api_auth_mode"] = auth_mode
                        target_entry["last_api_status"] = status
                    self._last_api_auth_mode = auth_mode
                    self._last_api_status = status
                    log.info(
                        "Flow API response id=%s status=%s auth_mode=%s",
                        req_id,
                        status,
                        auth_mode,
                    )
                if not fut.done():
                    fut.set_result(msg)

    async def wait_for_extension(self, timeout: float = 15, max_retries: int = 1) -> bool:
        start_t = time.time()
        while time.time() - start_t < timeout:
            if any(_is_ws_connected(e.get("ws")) for e in self._instances.values()):
                return True
            await asyncio.sleep(0.5)
        return False
