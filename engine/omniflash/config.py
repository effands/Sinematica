"""Sinematica Engine — Configuration for Google Flow Agent."""

import os
import sys

# Paths
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MEDIA_ID_FILE = os.path.join(ROOT_DIR, "media-id.js")

DEFAULT_PROJECT = os.environ.get("DEFAULT_PROJECT", "")

API_KEY = os.environ.get("API_KEY", "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY")
API_BASE = os.environ.get("API_BASE", "https://aisandbox-pa.googleapis.com")

CLIENT_CTX = {
    "tool": "PINHOLE",
}

ASPECTS = {
    "portrait": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "landscape": "VIDEO_ASPECT_RATIO_LANDSCAPE",
}

ENDPOINTS = {
    "generate_t2v": "/v1/video:batchAsyncGenerateVideoText",
    "generate_i2v": "/v1/video:batchAsyncGenerateVideoStartImage",
    "generate_fl": "/v1/video:batchAsyncGenerateVideoStartAndEndImage",
    "generate_r2v": "/v1/video:batchAsyncGenerateVideoReferenceImages",
    "generate_edit": "/v1/video:batchAsyncGenerateVideoEditVideo",
    "upload_image": "/v1/flow/uploadImage",
    "poll_status": "/v1/video:batchCheckAsyncVideoGenerationStatus",
    "get_media": "/v1/media/{media_id}",
    "get_credits": "/v1/credits",
}

CREDITS_PER_VIDEO = {
    4: 7,
    6: 10,
    8: 12,
    10: 15,
}

MODELS = {
    "t2v": {
        4: "abra_t2v_4s",
        6: "abra_t2v_6s",
        8: "abra_t2v_8s",
        10: "abra_t2v_10s",
    },
    "edit": "abra_edit",
}

DURATIONS = [4, 6, 8, 10]
DEFAULT_DURATION = 8

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "8"))
POLL_TIMEOUT = int(os.environ.get("POLL_TIMEOUT", "420"))

API_REQUEST_TIMEOUT = int(os.environ.get("API_REQUEST_TIMEOUT", "180"))
MAX_CONCURRENT_REQUESTS = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "5"))
REQUEST_MIN_INTERVAL = float(os.environ.get("REQUEST_MIN_INTERVAL", "2"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]
