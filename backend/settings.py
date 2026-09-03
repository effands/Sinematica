"""Sinematica Backend — Settings & Configuration Manager."""

import json
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

ENGINE_DIR = BASE_DIR / "engine"
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
JOBS_DIR = STORAGE_DIR / "jobs"

DATA_DIR.mkdir(exist_ok=True)
STORAGE_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)

SETTINGS_FILE = DATA_DIR / "settings.json"


DEFAULT_CHARACTER_SHEET_TEMPLATE = """3×3 CHARACTER CONTACT SHEET MASTER PROMPT V5.0

Ultra-Photorealistic Studio Edition • 9-Panel Identity Lock • AI Optimized

Create an ultra-photorealistic 3×3 Character Contact Sheet for {char_name} (Character Seed: {char_seed}): {char_desc}.

Transform the subject into a consistent, definitive character design while strictly preserving and locking identity, bone structure, facial proportions, skin tone, hairstyle, outfit, silhouette, and recognizable visual language across all 9 panels.

COMPOSITION & LAYOUT:
One single vertical 9:16 image containing a clean, evenly arranged 3×3 contact sheet (9 panels total).
Title bar at top: "CHARACTER SHEET: {char_name}" with subtle seed tag.
All 9 panels must be clearly separated by thin, clean divider lines on a neutral studio background with subtle realistic shadows. Balanced margins, professional editorial portfolio presentation.
Consistent lighting, color, wardrobe, styling, and character identity across all panels. Each panel should feel like a different camera capture of the exact same person in the same studio session.

3×3 GRID — 9 UNIQUE PHOTOGRAPHIC VIEWS:
Every panel captures a distinct camera angle of the exact same person, with no identity drift and no duplicated camera angle:
  Panel 1: Front view (direct eye-level camera capture, natural neutral presence)
  Panel 2: 3/4 view (three-quarter angle revealing cheekbone structure and dimensional facial depth)
  Panel 3: Side profile view (clean lateral 90-degree profile showing jawline and posture)
  Panel 4: Low-angle view (subtle upward camera angle, cinematic grounded perspective)
  Panel 5: Top-down view (slight elevated downward perspective showing crown and shoulder line)
  Panel 6: Waist-up portrait (medium editorial framing with natural poise and hand gesture)
  Panel 7: Close-up facial portrait (macro facial capture showing eye detail, natural skin pores, and authentic expression)
  Panel 8: Over-the-shoulder view (cinematic dimensional capture with natural head turn)
  Panel 9: Full-body view (complete head-to-toe stance showing full costume silhouette, shoes, and authentic proportions)

IDENTITY LOCK (HIGHEST PRIORITY):
Preserve the exact identity of {char_name} across all 9 panels:
• Identical face structure and bone structure
• Identical facial proportions
• Identical skin tone and natural realistic skin texture
• Preserve natural asymmetry and distinctive facial features
• Do not beautify, reshape, smooth unnaturally, or alter the face
• No age change; no hairstyle change unless explicitly requested
• The same person must be immediately and unmistakably recognizable in every single panel

PHOTOGRAPHY & RENDER STYLE:
Ultra-photorealistic editorial photography | 85mm lens equivalent | RAW photography look | Extremely high detail and optical sharpness | Natural realistic skin texture with visible skin pores | Controlled professional studio lighting | Neutral studio background | Subtle realistic shadows | Accurate anatomy and natural fabric behavior.

ANTI-DRIFT & NEGATIVE PROMPT:
Do NOT change the person's identity, alter facial structure, beautify or airbrush the face, smooth skin unnaturally, change skin tone, redesign facial features, change body proportions, create different people, repeat identical camera angles, stylize into cartoon or anime, introduce inconsistent wardrobe or changing accessories, recoloured clothing, cluttered layout, oversized text, watermark, blurry textures, AI artifacts, extra limbs, distorted anatomy."""


DEFAULT_SCENE_STORYBOARD_TEMPLATE = """SCENE STORYBOARD CONTACT SHEET (4-6 MULTI-ANGLE SHOT FLOW)

Professional cinematic film pre-visualization contact sheet for ONE scene (0–10s), laid out as a
clean editorial grid of 4 to 6 storyboard panels showing the precise camera angle progression:

SCENE {scene_number}: {scene_title} | DURATION: {scene_duration} seconds
ACTION & BEAT: {scene_action}
ESTABLISHED CAMERA & MOVEMENT: {camera_movement}

GRID LAYOUT — 4 TO 6 MULTI-ANGLE SHOT PROGRESSION (0-10s):
Header reading: "SCENE {scene_number} – Multi-Angle Shot Flow (0–{scene_duration}s)"
Followed by a clean 2×3 or 1×4 storyboard panel grid with thin borders and distinct photographic camera angles:
  • PANEL S1 (0–2s): Low Angle Close Up — opening physical action & natural candid expression.
  • PANEL S2 (2–4s): Medium Wide Shot — interaction with immediate environment, space & blocking.
  • PANEL S3 (4–6s): Extreme Close-Up / Macro Detail or Over-The-Shoulder — key object focus, hand contact or gaze shift.
  • PANEL S4 (6–8s): Medium Close / Dynamic Angle — reaction beat, emotion peak or decisive turning point.
  • PANEL S5 (8–10s): Wide Shot / Final Resolution Look — concluding framing, open relaxed or cliffhanger posture.
Each panel features a clean dark caption bar below it showing: "[Shot Number] (Timecode) [Camera Angle] — [Brief Shot Description]".

CHARACTER LOCK (HIGHEST PRIORITY):
The attached character sheet images define exactly who these people are. Reproduce those exact
faces, skin tones, bone structure, hairstyles, body proportions, wardrobe, colours and accessories
with no reinvention whatsoever across ALL panels. Treat the sheets as the single source of truth.

CONSISTENCY (CRITICAL):
All panels depict the IDENTICAL character(s), SAME clothing, SAME hairstyle, SAME environment,
SAME lighting direction and time of day. Only camera distance, framing angle, and pose advance
between panels following the {scene_duration}-second timeline. Art direction: {art_direction}

RENDER STYLE:
Ultra photorealistic editorial contact sheet | High-end cinematic cinematography | Natural skin pores and textures |
Authentic fabric folds | Believable depth of field | Cohesive color grading | Crisp clean typography.

NEGATIVE PROMPT:
Different people in different panels, facial drift, morphing clothing, cartoon/anime style unless specified,
inconsistent lighting, comic speech bubbles, oversized floating text, blurry textures, AI artifacts, distorted hands."""


def get_settings() -> dict:
    defaults = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "gemini_api_keys": [os.getenv("GEMINI_API_KEY", "")] if os.getenv("GEMINI_API_KEY") else [],
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "openai_api_keys": [os.getenv("OPENAI_API_KEY", "")] if os.getenv("OPENAI_API_KEY") else [],
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "deepseek_api_keys": [os.getenv("DEEPSEEK_API_KEY", "")] if os.getenv("DEEPSEEK_API_KEY") else [],
        "deepseek_model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "xai_api_key": os.getenv("XAI_API_KEY", ""),
        "xai_api_keys": [os.getenv("XAI_API_KEY", "")] if os.getenv("XAI_API_KEY") else [],
        "xai_model": os.getenv("XAI_MODEL", "grok-4.3"),
        "xai_base_url": os.getenv(
            "XAI_BASE_URL",
            "https://api.x.ai/v1",
        ),
        "nine_router_api_key": os.getenv("NINE_ROUTER_API_KEY", ""),
        "nine_router_api_keys": [os.getenv("NINE_ROUTER_API_KEY", "")] if os.getenv("NINE_ROUTER_API_KEY") else [],
        "nine_router_model": os.getenv("NINE_ROUTER_MODEL", "premium-coding"),
        "nine_router_base_url": os.getenv("NINE_ROUTER_BASE_URL", "http://127.0.0.1:20128/v1"),
        "default_text_provider": os.getenv("DEFAULT_TEXT_PROVIDER", "gemini"),
        "text_provider_order": ["gemini", "openai", "deepseek", "xai", "9router", "web2api"],
        "default_flow_project_id": os.getenv("DEFAULT_FLOW_PROJECT_ID", ""),
        "preferred_instance_id": "",
        "aspect_ratio": "landscape",
        "scene_count": 4,
        "video_duration": 10,
        "enable_character_seed_image": True,
        "character_seed_template": DEFAULT_CHARACTER_SHEET_TEMPLATE,
        "enable_scene_storyboard_image": True,
        # Gemini image model used to compose scene storyboards from the character sheets.
        # Blank = try the built-in list newest-first.
        "storyboard_image_model": os.getenv("STORYBOARD_IMAGE_MODEL", ""),
        "scene_storyboard_template": DEFAULT_SCENE_STORYBOARD_TEMPLATE,
        # Last-resort text generator used only after every Gemini API key is exhausted.
        # Points at a local gemini-web2api bridge (OpenAI-compatible, no API key, no quota).
        # It cannot accept images, so reference pictures are dropped on this path.
        # How many times AI may rewrite a prompt that Flow rejected on content policy.
        "max_policy_rewrites": 5,
        "enable_web2api_fallback": False,
        "web2api_base_url": os.getenv("WEB2API_BASE_URL", "http://127.0.0.1:8081/v1"),
        "web2api_model": os.getenv("WEB2API_MODEL", "gemini-2.5-flash"),
        "web2api_api_key": os.getenv("WEB2API_API_KEY", ""),
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
                # Alibaba/Qwen was removed in favor of xAI/Grok. Never retain its
                # credentials invisibly or leave an invalid provider in failover order.
                for old_key in (
                    "alibaba_api_key", "alibaba_api_keys", "alibaba_model", "alibaba_base_url"
                ):
                    defaults.pop(old_key, None)
                if defaults.get("default_text_provider") == "alibaba":
                    defaults["default_text_provider"] = "xai"
                order = defaults.get("text_provider_order") or []
                defaults["text_provider_order"] = [
                    "xai" if provider == "alibaba" else provider for provider in order
                ]
        except Exception:
            pass
    return defaults


def save_settings(updates: dict) -> dict:
    current = get_settings()
    current.update(updates)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current


def get_gemini_api_keys() -> List[str]:
    cfg = get_settings()
    raw_list = cfg.get("gemini_api_keys") or []
    if isinstance(raw_list, str):
        raw_list = [k.strip() for k in raw_list.replace("\n", ",").split(",") if k.strip()]

    single_key = cfg.get("gemini_api_key", "").strip()
    if single_key:
        for k in single_key.replace("\n", ",").split(","):
            k_clean = k.strip()
            if k_clean and k_clean not in raw_list:
                raw_list.append(k_clean)

    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key and env_key not in raw_list:
        raw_list.append(env_key)

    return [k for k in raw_list if k]


def get_gemini_api_key() -> str:
    keys = get_gemini_api_keys()
    return keys[0] if keys else ""


def get_flow_project_id() -> str:
    cfg = get_settings()
    return cfg.get("default_flow_project_id") or os.getenv("DEFAULT_FLOW_PROJECT_ID", "")


CHILDREN_CHARACTER_SHEET_TEMPLATE = """CHARACTER SHEET — 3D CARTOON ANIMAL FOR PRESCHOOL SERIES

Create a bright, friendly character sheet for {char_name} (Character Seed: {char_seed}): {char_desc}.

CHARACTER TYPE (MANDATORY):
A cute anthropomorphic ANIMAL rendered as a soft 3D cartoon character, in the style of a modern
preschool animated series for 4-5 year olds. Never a human child.
Big friendly eyes, soft rounded shapes, chunky proportions, oversized head, small body,
gentle smile, simple colourful outfit. Appealing and huggable, never scary or edgy.

LAYOUT:
Large "CHARACTER SHEET" title | Character Name: {char_name} | Clean pastel background |
Turnaround: Front View, Side View, Back View with identical proportions and colours |
Three expressions: Happy, Curious, Surprised (gentle and friendly, never angry or frightening) |
Three poses: Standing, Walking, Waving.

RENDER STYLE:
Soft 3D cartoon render | Preschool animation style | Bright cheerful colours | Smooth rounded forms |
Soft even lighting with gentle shadows | Clean simple shapes | Highly appealing character design |
Consistent colour palette across every panel.

NEGATIVE PROMPT:
Human child, human children, realistic human, photorealistic, scary, creepy, sharp teeth, weapons,
dark shadows, horror, gore, moody lighting, harsh contrast, complex textures, adult themes,
inconsistent character design, different colours between panels, cluttered layout."""


CHILDREN_SCENE_STORYBOARD_TEMPLATE = """SCENE STORYBOARD SHEET — PRESCHOOL 3D CARTOON

Storyboard page for one scene of a gentle animated series for 4-5 year olds.

SCENE: {scene_title}   |   DURATION: {scene_duration} seconds
SHOT TYPE: {shot_type}
CAMERA: {camera_movement}
ACTION: {scene_action}

LAYOUT:
Title bar reading "SCENE {scene_number} - {scene_title}" with a small duration tag.
Below it, three storyboard panels with thin borders, reading left to right:
  PANEL 1 "OPENING FRAME" — how the shot begins.
  PANEL 2 "MID ACTION" — the happy peak of the action above.
  PANEL 3 "END FRAME" — how the shot resolves.
A short framing note under each panel.

CHARACTER LOCK (HIGHEST PRIORITY):
The attached character sheets define exactly who these characters are. Reproduce those exact
animal characters, colours, shapes, proportions and outfits with no reinvention. The sheets are
the single source of truth. Never replace them with humans or with different animals.

RENDER STYLE:
Soft 3D cartoon render | Preschool animation style | Bright cheerful colours | Soft even lighting |
Simple readable backgrounds | Friendly happy mood | Consistent character design across all panels.

NEGATIVE PROMPT:
Human child, realistic human, photorealistic, scary, creepy, weapons, violence, dark moody lighting,
harsh shadows, horror, sad crying faces, characters that do not match the reference sheets,
different colours between panels, cluttered layout, oversized text."""
