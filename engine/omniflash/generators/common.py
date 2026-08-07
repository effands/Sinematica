"""Common helpers for Flow generation calls."""
import random
from ..config import CLIENT_CTX

def build_client_context(project_id: str) -> dict:
    ctx = dict(CLIENT_CTX)
    if project_id:
        ctx["projectId"] = project_id
    return ctx

def build_generation_context() -> dict:
    return {}
