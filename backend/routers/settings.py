"""Sinematica Backend — Settings Router with Multi Gemini API Key Tester & Failover."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import google.generativeai as genai
import logging

from .. import settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])
log = logging.getLogger("sinematica.routers.settings")


from typing import Optional, List, Dict, Any, Union

class SettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[Union[str, List[str]]] = None
    gemini_api_keys: Optional[Union[str, List[str]]] = None
    gemini_model: Optional[str] = None
    default_flow_project_id: Optional[str] = None
    preferred_instance_id: Optional[str] = None
    aspect_ratio: Optional[str] = None
    scene_count: Optional[int] = None
    video_duration: Optional[int] = None
    enable_character_seed_image: Optional[bool] = None
    character_seed_template: Optional[str] = None
    enable_scene_storyboard_image: Optional[bool] = None
    scene_storyboard_template: Optional[str] = None
    max_policy_rewrites: Optional[int] = None
    enable_web2api_fallback: Optional[bool] = None
    web2api_base_url: Optional[str] = None
    web2api_model: Optional[str] = None
    web2api_api_key: Optional[str] = None


class TestGeminiRequest(BaseModel):
    gemini_api_keys: Optional[Union[str, List[str]]] = None
    gemini_api_key: Optional[Union[str, List[str]]] = None
    gemini_model: Optional[str] = "gemini-3.6-flash"


@router.get("")
def get_all_settings():
    return {"settings": settings.get_settings()}


@router.post("")
def update_settings(req: SettingsUpdateRequest):
    data = req.dict(exclude_unset=True)
    raw = data.get("gemini_api_keys") or data.get("gemini_api_key")
    if raw:
        if isinstance(raw, str):
            keys = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
        elif isinstance(raw, list):
            keys = [str(k).strip() for k in raw if str(k).strip()]
        else:
            keys = []
        data["gemini_api_keys"] = keys
        if keys:
            data["gemini_api_key"] = keys[0]

    updated = settings.save_settings(data)
    return {"success": True, "settings": updated}


@router.post("/test_gemini")
def test_gemini_keys(req: TestGeminiRequest):
    raw_input = req.gemini_api_key or ""
    keys = req.gemini_api_keys or []

    if raw_input:
        parsed = [k.strip() for k in raw_input.replace("\n", ",").split(",") if k.strip()]
        for p in parsed:
            if p not in keys:
                keys.append(p)

    if not keys:
        keys = settings.get_gemini_api_keys()

    if not keys:
        raise HTTPException(status_code=400, detail="Gemini API Key belum diisi!")

    model_name = req.gemini_model or "gemini-2.5-flash"
    candidates = [model_name, "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
    seen = set()
    models_to_test = [x for x in candidates if not (x in seen or seen.add(x))]

    results = []

    for idx, key in enumerate(keys, start=1):
        preview = key[:8] + "..." + key[-4:] if len(key) > 12 else key
        key_res = {"index": idx, "key_preview": preview, "valid": False, "model": None, "error": None}

        try:
            genai.configure(api_key=key)
            for m in models_to_test:
                try:
                    mod = genai.GenerativeModel(m)
                    resp = mod.generate_content("Ping test.")
                    if resp and resp.text:
                        key_res["valid"] = True
                        key_res["model"] = m
                        break
                except Exception as ex:
                    key_res["error"] = str(ex)
        except Exception as ex:
            key_res["error"] = str(ex)

        results.append(key_res)

    valid_count = sum(1 for r in results if r["valid"])
    if valid_count == 0:
        raise HTTPException(status_code=400, detail=f"Seluruh {len(keys)} Gemini API Key gagal saat dites: {results[0].get('error')}")

    return {
        "success": True,
        "valid_count": valid_count,
        "total_keys": len(keys),
        "results": results,
        "message": f"✅ {valid_count} dari {len(keys)} Gemini API Key Valid & Siap Digunakan (Auto-Rotation Active)!"
    }


class ProbeRefRequest(BaseModel):
    project_id: Optional[str] = None
    media_ids: Optional[List[str]] = None


@router.post("/probe_image_reference")
async def probe_image_reference(req: ProbeRefRequest):
    """Sweep Flow's image endpoint to discover how reference images must be attached."""
    from ..probe_image_reference import probe_reference_field
    from ..bridge_manager import get_bridge
    from .. import flow_schema

    bridge = get_bridge()
    project_id = req.project_id or settings.get_flow_project_id()
    instance_id = None
    for inst in bridge.instance_snapshot():
        if inst.get("connected"):
            instance_id = inst["instance_id"]
            project_id = project_id or inst.get("project_id")
            break

    if not instance_id:
        raise HTTPException(status_code=400, detail="Tidak ada profil Chrome yang terhubung.")
    if not project_id:
        raise HTTPException(status_code=400, detail="Flow Project ID tidak diketahui.")

    media_ids = req.media_ids or []
    if not media_ids:
        # Generate one throwaway image so the probe has a real media id to attach.
        from omniflash.generators import generate_character_image
        made = await generate_character_image(
            bridge, prompt="A plain grey placeholder square.", aspect="portrait",
            project_id=project_id, instance_id=instance_id)
        media_ids = [made["media_id"]]

    # Flow uses one endpoint per mode, so look for a sibling endpoint before field names.
    from ..probe_image_reference import probe_reference_endpoint
    ep_result = await probe_reference_endpoint(project_id, media_ids, instance_id)
    if ep_result.get("found"):
        return {"endpoint_probe": ep_result, "media_id_used": media_ids[0]}

    result = await probe_reference_field(project_id, media_ids, instance_id)
    result["endpoint_probe"] = ep_result

    if result.get("found") and result["found"].get("verdict") == "accepted":
        found = result["found"]
        learned = {"reference": {"style": found["style"], "field": found["field"],
                                 "example": [{"mediaId": media_ids[0]}]},
                   "image_model": "HARBOR_SEAL"}
        flow_schema._save(flow_schema.LEARNED_FILE, learned)
        flow_schema._learned_cache = learned
        try:
            from omniflash.generators.t2i import reset_reference_probing
            reset_reference_probing()
        except Exception:
            pass
        result["saved"] = True

    return result
