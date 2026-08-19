"""Sinematica Backend — Fleet Status & WebSocket Router."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging

from ..bridge_manager import get_bridge, status_snapshot
from engine.omniflash.bridge import is_routable_bridge_message

router = APIRouter(tags=["Status & Fleet"])

log = logging.getLogger("sinematica.routers.status")


@router.get("/api/status")
def get_system_status():
    return status_snapshot()


@router.get("/api/fleet")
def get_fleet_profiles():
    try:
        bridge = get_bridge()
        return {"profiles": bridge.instance_snapshot()}
    except Exception:
        return {"profiles": []}


@router.get("/api/fleet_credits")
async def get_fleet_credits():
    """Query status & quota state for all connected Chrome Fleet profiles."""
    bridge = get_bridge()
    instances = bridge.instance_snapshot()
    results = {}

    for inst in instances:
        iid = inst.get("instance_id")
        if not iid:
            continue
        connected = inst.get("connected", False)
        logged_in = inst.get("logged_in", False)
        ready = inst.get("ready", True)

        if connected and logged_in and ready:
            c_val = "Unlimited"
            try:
                res = await bridge.api_request("/v1/credits", None, instance_id=iid, timeout=6)
                if res.get("status") == 200:
                    d = res.get("data", {})
                    if isinstance(d, dict) and d.get("credits"):
                        c_val = str(d["credits"])
            except Exception:
                pass
            results[iid] = {
                "success": True,
                "credits": c_val,
                "status": "READY"
            }
        elif connected:
            results[iid] = {
                "success": False,
                "credits": inst.get("readiness_error") or "Perlu Login/Window Flow",
                "status": inst.get("readiness_error") or "NOT_READY"
            }
        else:
            results[iid] = {
                "success": False,
                "credits": "Terputus",
                "status": "DISCONNECTED"
            }

    return {"credits": results}


@router.get("/api/test_image_probe")
async def test_image_probe():
    """Probe all candidate reference image shapes directly on the live connected bridge."""
    bridge = get_bridge()
    snap = bridge.instance_snapshot()
    connected = [i for i in snap if i["connected"]]
    if not connected:
        return {"error": "No connected Chrome Extension profile found!"}

    proj = connected[0].get("project_id") or "0183e37a-10ef-465a-b0b8-6443ee075758"
    inst_id = connected[0].get("instance_id")
    endpoint = f"/v1/projects/{proj}/flowMedia:batchGenerateImages"

    test_media_id = "1c650c2b-0d29-480e-947d-59570369484d"

    import random
    candidates = [
        ("multimodal_part_media", lambda m: {"_prompt_parts": [{"media": {"mediaId": m}}]}),
        ("multimodal_part_image", lambda m: {"_prompt_parts": [{"image": {"mediaId": m}}]}),
        ("multimodal_part_mediaId", lambda m: {"_prompt_parts": [{"mediaId": m}]}),
        ("multimodal_part_mediaRef", lambda m: {"_prompt_parts": [{"mediaRef": {"mediaId": m}}]}),
        ("multimodal_part_fileData", lambda m: {"_prompt_parts": [{"fileData": {"fileUri": m}}]}),
        ("top_level_referenceMedia", lambda m: {"referenceMedia": [{"mediaId": m}]}),
        ("top_level_referenceImages", lambda m: {"referenceImages": [{"mediaId": m}]}),
        ("top_level_inputImages", lambda m: {"inputImages": [{"mediaId": m}]}),
        ("top_level_subjectReferences", lambda m: {"subjectReferences": [{"mediaId": m}]}),
        ("top_level_characterReferences", lambda m: {"characterReferences": [{"mediaId": m}]}),
        ("top_level_styleReferences", lambda m: {"styleReferences": [{"mediaId": m}]}),
        ("top_level_ingredientMedia", lambda m: {"ingredientMedia": [{"mediaId": m}]}),
        ("top_level_ingredients", lambda m: {"ingredients": [{"mediaId": m}]}),
    ]

    results = []
    accepted_shape = None

    for name, builder in candidates:
        variant = builder(test_media_id)
        parts = [{"text": "A test concept storyboard sheet of a cute 3D character."}]
        prompt_parts = variant.pop("_prompt_parts", None)
        if prompt_parts:
            parts = parts + prompt_parts

        request_item = {
            "clientContext": {"tool": "PINHOLE", "projectId": proj},
            "seed": random.randint(100000, 999999),
            "imageAspectRatio": "IMAGE_ASPECT_RATIO_PORTRAIT",
            "imageModelName": "HARBOR_SEAL",
            "structuredPrompt": {"parts": parts}
        }
        request_item.update(variant)
        body = {"clientContext": {"tool": "PINHOLE", "projectId": proj}, "requests": [request_item]}

        try:
            resp = await bridge.api_request(endpoint, body, instance_id=inst_id, timeout=10)
            status = resp.get("status")
            err_msg = str(resp.get("data") or resp.get("error"))[:200]
            results.append({"candidate": name, "status": status, "error": err_msg})
            if status == 200:
                accepted_shape = {"candidate": name, "request_item": request_item}
                break
        except Exception as ex:
            results.append({"candidate": name, "status": 500, "error": str(ex)})

    return {"accepted": accepted_shape, "results": results}


import asyncio

async def _ws_ping_loop(websocket: WebSocket):
    try:
        while True:
            await asyncio.sleep(20)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except Exception:
        pass

@router.websocket("/ws")
@router.websocket("/ws/agent")
@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    bridge = get_bridge()

    instance_id = None
    log.info("Chrome Extension WebSocket connected!")
    
    ping_task = asyncio.create_task(_ws_ping_loop(websocket))

    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                msg = json.loads(data_str)
                msg_type = msg.get("type")

                if msg_type == "register":
                    instance_id = msg.get("instance_id")
                    bridge.register_instance(
                        instance_id=instance_id,
                        ws=websocket,
                        instance_name=msg.get("name"),
                        project_id=msg.get("project_id"),
                        ready=msg.get("ready", True),
                        readiness_error=msg.get("readiness_error"),
                    )
                    if msg.get("flow_key"):
                        bridge.record_instance_token(instance_id, msg["flow_key"])

                elif msg_type == "token_captured":
                    instance_id = msg.get("instance_id") or instance_id
                    if instance_id and msg.get("flow_key"):
                        bridge.record_instance_token(instance_id, msg["flow_key"])

                elif is_routable_bridge_message(msg_type):
                    bridge.handle_message(data_str, websocket, instance_id)

                elif msg_type == "flow_ui_request":
                    # The Flow website just made an image request; copy its exact shape.
                    learned = flow_schema.record_ui_request(msg.get("url", ""), msg.get("payload", ""))
                    if learned:
                        log.info("Skema Flow dipelajari dari UI: %s", learned)

            except Exception as ex:
                log.warning("WebSocket payload parsing error: %s", ex)

    except WebSocketDisconnect:
        log.info("Chrome Extension WebSocket disconnected: %s", instance_id)
    except Exception as ex:
        log.error("WebSocket handler error (%s): %s", instance_id, ex)
    finally:
        ping_task.cancel()
        log.info("Cleaning up WebSocket connection for instance: %s", instance_id or "unnamed")
        if hasattr(bridge, "remove_ws_reference"):
            bridge.remove_ws_reference(websocket)
        elif instance_id:
            bridge.unregister_instance(instance_id, websocket)


from pydantic import BaseModel
from typing import Optional
from fastapi import HTTPException
from .. import settings
from .. import flow_schema
from omniflash.generators import generate_character_image, generate_video_t2v
import random


class TestPromptRequest(BaseModel):
    prompt: Optional[str] = "A handsome wise scholar character portrait, cinematic lighting, 8k"
    seed: Optional[int] = 492817


@router.post("/api/fleet/test_prompt")
async def test_fleet_prompt(req: TestPromptRequest):
    """Test sending video generation prompt directly to connected Chrome Google Flow extension."""
    bridge = get_bridge()
    instances = bridge.instance_snapshot()
    log.info("test_fleet_prompt instances: %s", instances)
    ready = [i for i in instances if i.get("connected") and i.get("ready", True)]
    if not ready:
        raise HTTPException(
            status_code=400,
            detail=f"Tidak ada Chrome Extension yang terhubung! Total instances: {len(instances)}"
        )

    target_prompt = req.prompt or "A handsome wise scholar character portrait, cinematic lighting, 8k"

    try:
        cfg = settings.get_settings()
        proj_id = cfg.get("flow_project_id") or ready[0].get("project_id") or "0fe1acd1-8e99-48a4-aade-cd3b764086d1"
        first_target_id = ready[0].get("instance_id")

        media_ids = await generate_video_t2v(
            bridge=bridge,
            prompt=target_prompt,
            aspect="landscape",
            project_id=proj_id,
            duration=10,
            instance_id=first_target_id
        )

        return {
            "success": True,
            "message": "Berhasil submit generasi video ke Google Flow!",
            "media_ids": media_ids,
            "profile_used": ready[0].get("name")
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Gagal generate video T2V: {ex}")
