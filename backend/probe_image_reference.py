"""Sinematica Backend — Find the field Google Flow uses to attach reference images.

The image endpoint is undocumented, so instead of guessing one name at a time this sweeps a
broad candidate list through the real API and reads the protobuf error to classify each one:

  * "Unknown name X"      -> the field does not exist at all
  * "Invalid value at X"  -> the field EXISTS, only the value shape was wrong
  * HTTP 200              -> the field exists and the value was accepted

That turns a guessing game into a search with a definite answer.
"""

import logging
import random
from typing import Any, Dict, List, Optional

from .bridge_manager import get_bridge

log = logging.getLogger("sinematica.probe")

# Names worth trying at the top level of a request item.
TOP_LEVEL_CANDIDATES = [
    "referenceImages", "referenceImage", "referenceMedia", "referenceMediaIds",
    "inputImages", "inputImage", "inputMedia", "sourceImages", "sourceMedia",
    "subjectReferences", "characterReferences", "styleReferences", "styleImages",
    "ingredients", "ingredientImages", "ingredientMedia",
    "assets", "assetIds", "mediaInputs", "imageInputs", "mediaIds", "imageIds",
    "conditioningImages", "controlImages", "baseImages", "seedImages",
    "contextImages", "attachments", "attachedMedia", "promptImages", "guideImages",
]

# Names worth trying inside structuredPrompt.parts[].
PROMPT_PART_CANDIDATES = [
    "mediaId", "media", "image", "imageId", "mediaRef", "mediaReference",
    "inputImage", "referenceImage", "asset", "assetId", "imageInput", "mediaInput",
    "inlineMedia", "generatedImage", "mediaPart", "imagePart",
]


"""Flow exposes one endpoint per generation mode rather than one endpoint with a mode field
(see the video side: ...VideoText, ...VideoStartImage, ...VideoReferenceImages). So the image
equivalent for reference-guided generation is most likely a sibling endpoint, not a field."""

ENDPOINT_CANDIDATES = [
    "/v1/image:batchGenerateImageReferenceImages",
    "/v1/image:batchAsyncGenerateImageReferenceImages",
    "/v1/image:batchGenerateImageStartImage",
    "/v1/image:batchGenerateImageText",
    "/v1/image:batchGenerateImages",
    "/v1/projects/{p}/flowMedia:batchGenerateImagesReferenceImages",
    "/v1/projects/{p}/flowMedia:batchGenerateImagesFromReferences",
    "/v1/projects/{p}/flowMedia:batchGenerateImagesWithReferences",
    "/v1/projects/{p}/flowMedia:batchEditImages",
    "/v1/projects/{p}/flowMedia:batchAsyncGenerateImages",
    "/v1/projects/{p}/flowMedia:batchGenerateImagesEditImage",
    "/v1/projects/{p}/flowMedia:batchGenerateImagesStartImage",
]


def _classify_endpoint(response: Dict[str, Any]) -> str:
    """Tell a missing endpoint apart from a real one that merely disliked our body."""
    status = response.get("status")
    blob = str(response.get("data") or "")
    if status == 200:
        return "accepted"
    if status == 404 or "not found" in blob.lower() or "was not found" in blob.lower():
        return "no_such_endpoint"
    if status == 400:
        # A real endpoint validates fields; that means it exists.
        return "exists_body_rejected"
    return f"status_{status}"


async def probe_reference_endpoint(project_id: str, media_ids: List[str],
                                   instance_id: Optional[str] = None) -> Dict[str, Any]:
    """Look for a sibling image endpoint that takes reference images, like the video one does."""
    bridge = get_bridge()
    media = [{"mediaId": m} for m in media_ids]
    findings = []
    hit = None

    for template in ENDPOINT_CANDIDATES:
        endpoint = template.replace("{p}", project_id)
        body = {
            "clientContext": {"tool": "PINHOLE", "projectId": project_id},
            "requests": [{
                "clientContext": {"tool": "PINHOLE", "projectId": project_id},
                "seed": random.randint(100000, 999999),
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_PORTRAIT",
                "imageModelName": "HARBOR_SEAL",
                "structuredPrompt": {"parts": [{"text": "A red circle."}]},
                "referenceImages": media,
            }],
        }
        try:
            resp = await bridge.api_request(endpoint, body, instance_id=instance_id)
        except Exception as ex:
            findings.append({"endpoint": endpoint, "verdict": f"error: {ex}"})
            continue

        verdict = _classify_endpoint(resp)
        # The extension reports its own failures on `error`, not inside `data`.
        detail = str(resp.get("data") or resp.get("error") or resp)[:300]
        findings.append({"endpoint": endpoint, "verdict": verdict, "detail": detail})
        log.info("Probe endpoint %s -> %s", endpoint, verdict)

        if verdict in ("accepted", "exists_body_rejected"):
            hit = {"endpoint": endpoint, "verdict": verdict, "detail": detail}
            if verdict == "accepted":
                break

    return {"found": hit, "checked": len(findings),
            "interesting": [f for f in findings if f.get("verdict") != "no_such_endpoint"]}


def _classify(response: Dict[str, Any], field: str) -> str:
    """Turn one API response into a verdict about `field`."""
    if response.get("status") == 200:
        return "accepted"

    blob = str(response.get("data") or "")
    if f'Unknown name \\"{field}\\"' in blob or f'Unknown name "{field}"' in blob:
        return "absent"
    if "Invalid value" in blob and field in blob:
        return "exists_wrong_shape"
    if "Unknown name" in blob:
        return "absent"
    return "unclear"


async def probe_reference_field(project_id: str, media_ids: List[str],
                                instance_id: Optional[str] = None) -> Dict[str, Any]:
    """Sweep candidate field names and report which one Flow actually recognises."""
    bridge = get_bridge()
    endpoint = f"/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    def body_for(extra: Dict[str, Any], parts_extra: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        parts = [{"text": "A simple test image of a red circle."}]
        if parts_extra:
            parts = parts + parts_extra
        item = {
            "clientContext": {"tool": "PINHOLE", "projectId": project_id},
            "seed": random.randint(100000, 999999),
            "imageAspectRatio": "IMAGE_ASPECT_RATIO_PORTRAIT",
            "imageModelName": "HARBOR_SEAL",
            "structuredPrompt": {"parts": parts},
        }
        item.update(extra)
        return {"clientContext": {"tool": "PINHOLE", "projectId": project_id},
                "requests": [item]}

    findings: List[Dict[str, str]] = []
    accepted: Optional[Dict[str, Any]] = None

    media = [{"mediaId": m} for m in media_ids]

    for name in TOP_LEVEL_CANDIDATES:
        try:
            resp = await bridge.api_request(endpoint, body_for({name: media}), instance_id=instance_id)
        except Exception as ex:
            findings.append({"field": name, "where": "top_level", "verdict": f"error: {ex}"})
            continue
        verdict = _classify(resp, name)
        findings.append({"field": name, "where": "top_level", "verdict": verdict})
        log.info("Probe top-level '%s' -> %s", name, verdict)
        if verdict in ("accepted", "exists_wrong_shape"):
            accepted = {"style": "top_level", "field": name, "verdict": verdict}
            if verdict == "accepted":
                break

    if not accepted:
        for name in PROMPT_PART_CANDIDATES:
            try:
                resp = await bridge.api_request(
                    endpoint, body_for({}, [{name: media[0]["mediaId"] if name.endswith("Id") else media[0]}]),
                    instance_id=instance_id)
            except Exception as ex:
                findings.append({"field": name, "where": "prompt_part", "verdict": f"error: {ex}"})
                continue
            verdict = _classify(resp, name)
            findings.append({"field": name, "where": "prompt_part", "verdict": verdict})
            log.info("Probe prompt-part '%s' -> %s", name, verdict)
            if verdict in ("accepted", "exists_wrong_shape"):
                accepted = {"style": "prompt_part", "field": name, "verdict": verdict}
                if verdict == "accepted":
                    break

    return {
        "found": accepted,
        "checked": len(findings),
        "candidates": [f for f in findings if f["verdict"] != "absent"],
    }
