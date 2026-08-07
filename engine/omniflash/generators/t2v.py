"""Omni Flash — Text to Video (T2V) generator."""

import logging
import random
from typing import List

from ..config import ENDPOINTS
from .common import build_client_context, build_generation_context
from .i2v import extract_api_error, generate_video_t2v

log = logging.getLogger("omniflash.generators.t2v")

__all__ = ["generate_video_t2v"]
