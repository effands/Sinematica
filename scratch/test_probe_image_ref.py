import asyncio
import json
import random
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.bridge_manager import get_bridge

async def probe_all_reference_shapes():
    bridge = get_bridge()
    snap = bridge.instance_snapshot()
    connected = [i for i in snap if i["connected"]]
    if not connected:
        print("ERROR: No connected Chrome Extension profile found! Please make sure Chrome with extension is open to labs.google/fx/tools/flow.")
        return

    proj = connected[0].get("project_id") or "0183e37a-10ef-465a-b0b8-6443ee075758"
    inst_id = connected[0].get("instance_id")
    endpoint = f"/v1/projects/{proj}/flowMedia:batchGenerateImages"

    # Test Media ID (e.g. Upi/Cici media id)
    test_media_id = "1c650c2b-0d29-480e-947d-59570369484d"

    # Candidate reference shapes to test
    candidates = [
        # Candidate 1: Multimodal part with media object (Google Flow standard part)
        ("multimodal_part_media", lambda m: {"_prompt_parts": [{"media": {"mediaId": m}}]}),
        # Candidate 2: Multimodal part with image object
        ("multimodal_part_image", lambda m: {"_prompt_parts": [{"image": {"mediaId": m}}]}),
        # Candidate 3: Multimodal part with direct mediaId
        ("multimodal_part_mediaId", lambda m: {"_prompt_parts": [{"mediaId": m}]}),
        # Candidate 4: Multimodal part with mediaRef
        ("multimodal_part_mediaRef", lambda m: {"_prompt_parts": [{"mediaRef": {"mediaId": m}}]}),
        # Candidate 5: Multimodal part with fileData
        ("multimodal_part_fileData", lambda m: {"_prompt_parts": [{"fileData": {"fileUri": m}}]}),
        # Candidate 6: Top-level referenceMedia
        ("top_level_referenceMedia", lambda m: {"referenceMedia": [{"mediaId": m}]}),
        # Candidate 7: Top-level referenceImages
        ("top_level_referenceImages", lambda m: {"referenceImages": [{"mediaId": m}]}),
        # Candidate 8: Top-level inputImages
        ("top_level_inputImages", lambda m: {"inputImages": [{"mediaId": m}]}),
        # Candidate 9: Top-level subjectReferences
        ("top_level_subjectReferences", lambda m: {"subjectReferences": [{"mediaId": m}]}),
        # Candidate 10: Top-level characterReferences
        ("top_level_characterReferences", lambda m: {"characterReferences": [{"mediaId": m}]}),
        # Candidate 11: Top-level styleReferences
        ("top_level_styleReferences", lambda m: {"styleReferences": [{"mediaId": m}]}),
        # Candidate 12: Top-level ingredientMedia
        ("top_level_ingredientMedia", lambda m: {"ingredientMedia": [{"mediaId": m}]}),
        # Candidate 13: Top-level ingredients
        ("top_level_ingredients", lambda m: {"ingredients": [{"mediaId": m}]}),
    ]

    print(f"=== STARTING PROBE FOR IMAGE GENERATION WITH REFERENCES ===")
    print(f"Project ID: {proj}, Profile: {connected[0]['name']}")

    for name, builder in candidates:
        variant = builder(test_media_id)
        parts = [{"text": "A test concept storyboard sheet of a cute character."}]
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

        print(f"\nTesting Candidate '{name}'...")
        try:
            resp = await bridge.api_request(endpoint, body, instance_id=inst_id)
            status = resp.get("status")
            if status == 200:
                print(f"🎉 SUCCESS! Candidate '{name}' ACCEPTED by Google Flow (HTTP 200)!")
                print("Payload accepted:", json.dumps(request_item, indent=2))
                return
            else:
                data_err = str(resp.get("data") or resp.get("error"))[:250]
                print(f"❌ Rejected ({status}): {data_err}")
        except Exception as ex:
            print(f"⚠️ Exception: {ex}")

    print("\nProbe completed. No candidate accepted.")

if __name__ == "__main__":
    asyncio.run(probe_all_reference_shapes())
