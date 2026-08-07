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


DEFAULT_CHARACTER_SHEET_TEMPLATE = """CHARACTER SHEET MASTER PROMPT V4.1

Studio Portfolio Edition
Clean • Elegant • Professional • AI Optimized

Create a clean, elegant, studio-quality Character Sheet for {char_name} (Character Seed: {char_seed}): {char_desc}.

Transform the subject into a consistent original character design while preserving the overall appearance, proportions, hairstyle, outfit style, silhouette, and recognizable visual language.

The layout should resemble a professional concept art portfolio page with generous white space, minimal typography, thin divider lines, and a balanced editorial composition.

LAYOUT:
Large "CHARACTER SHEET" title | Character Name: {char_name} | Soft beige or warm white background | Thin black divider lines | Minimal editorial typography | Spacious composition | Balanced margins | Professional portfolio presentation.

TURNAROUND:
Front View | Side View | Back View
Use identical character proportions, hairstyle, clothing design, silhouette, and visual appearance across all three views.

FACIAL EXPRESSIONS:
Three close-up portraits only: Neutral, Smile, Thoughtful. Expressions should modify only facial muscles while maintaining the same character appearance.

DYNAMIC POSES:
Three natural full-body poses only: Walking, Standing, Sitting. Keep body proportions, clothing behavior, hairstyle, and overall design consistent.

REFERENCE PORTRAIT:
One clean portrait showing the definitive appearance of {char_name}. Centered composition. Natural expression. Soft studio lighting.

CONSISTENCY:
Maintain a single coherent character design across every panel. Keep consistent: Facial structure | Hairstyle | Body proportions | Clothing construction | Accessories | Colors | Silhouette | Fabric behavior | Visual style.

RENDER STYLE:
Ultra photorealistic | Editorial fashion photography | Premium concept art | Soft studio lighting | Clean shadows | High detail | Natural skin texture | Accurate anatomy | Realistic fabric | Elegant presentation | Minimalistic portfolio design.

NEGATIVE PROMPT:
Busy layout, cluttered composition, excessive annotations, technical blueprint, production diagram, material callouts, color palette, measurement chart, camera reference, lighting reference, oversized text, crowded design, duplicate panels, inconsistent character design, different hairstyle, different clothing, different proportions, low quality, blurry textures, AI artifacts, cartoon style, anime style, painterly rendering, distorted anatomy."""


DEFAULT_SCENE_STORYBOARD_TEMPLATE = """SCENE STORYBOARD SHEET

Professional film pre-visualization board for ONE scene, laid out as a clean 4-panel
storyboard page — the scene equivalent of a character sheet.

SCENE: {scene_title}   |   DURATION: {scene_duration} seconds
SHOT TYPE: {shot_type}
CAMERA: {camera_movement}
ACTION: {scene_action}

LAYOUT:
Title bar at the top reading "SCENE {scene_number} - {scene_title}" with a small duration tag.
Below it, a grid/row of 4 storyboard panels with thin borders and generous white space, reading
left to right as the beat progression of this single scene:
  PANEL 1 "ESTABLISHING SHOT" — wide setup: character placement, environment, camera angle.
  PANEL 2 "OPENING ACTION" — how the movement begins: character interaction & motion.
  PANEL 3 "PEAK ACTION & CLIMAX" — the main key movement/emotional peak of the scene.
  PANEL 4 "REACTION & RESOLUTION" — close-up reaction or resolution just before the cut.
Under each panel, a thin caption strip with a short framing note (e.g. "Medium Shot, eye level").

CHARACTER LOCK (HIGHEST PRIORITY):
The attached character sheet images define exactly who these people are. Reproduce those exact
faces, skin tones, hairstyles, body proportions, wardrobe, colours and accessories with no
reinvention whatsoever. Treat the sheets as the single source of truth for appearance — if the
written description and a sheet ever disagree, the sheet wins. Do not substitute, age, restyle,
recolour or swap any character, and do not introduce anyone who is not in the sheets.

CONSISTENCY (CRITICAL):
All four panels show the SAME characters, SAME wardrobe, SAME hairstyle, SAME set and props,
SAME time of day and SAME lighting direction. Only the pose, distance and framing change
between panels. Keep the established art direction, lens character and colour grading: {art_direction}

RENDER STYLE:
Ultra photorealistic panels | Cinematic pre-visualization quality | Accurate character blocking |
Clear spatial relationships | Consistent set dressing | Natural skin texture | Realistic fabric |
Correct anatomy | Clean editorial storyboard presentation | Minimal typography.

NEGATIVE PROMPT:
Cluttered layout, oversized text, unreadable annotations, comic speech bubbles, watermark,
different character design between panels, wardrobe change between panels, inconsistent lighting,
new unfamiliar faces, characters that do not match the reference sheets, restyled hair,
recoloured clothing, low quality, blurry, distorted anatomy, extra limbs."""


def get_settings() -> dict:
    defaults = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "gemini_api_keys": [os.getenv("GEMINI_API_KEY", "")] if os.getenv("GEMINI_API_KEY") else [],
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
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
        # How many times Gemini may rewrite a prompt that Flow rejected on content policy.
        "max_policy_rewrites": 2,
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
