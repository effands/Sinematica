"""Sinematica AI — Main FastAPI Application Entry Point with Auto Global Error Diagnostics (v1.4.1)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
import logging
import traceback
import time
import os

# Fix gRPC SSL Handshake issue on Windows with Google APIs
os.environ["GRPC_DNS_RESOLVER"] = "native"

from . import settings
from .bridge_manager import init_bridge, close_bridge
from .routers import status, storyboard, jobs, gallery, settings as settings_router, actors
import importlib
importlib.reload(status)
importlib.reload(storyboard)
importlib.reload(jobs)
importlib.reload(gallery)
importlib.reload(settings_router)
importlib.reload(actors)

ERROR_LOG_FILE = settings.DATA_DIR / "error_diagnostics.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("sinematica.main")


def log_error_diagnostic(source: str, err: Exception):
    """Automatically record detailed stack trace & error diagnostics for automatic debugging."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    tb = traceback.format_exc()
    entry = f"[{timestamp}] [AUTO-DIAGNOSTIC] Source: {source}\nError: {err}\nTraceback:\n{tb}\n"
    log.error(entry)
    try:
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n" + "=" * 50 + "\n")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Sinematica AI Studio Backend...")
    await init_bridge()
    yield
    log.info("Closing Sinematica AI Studio Backend...")
    await close_bridge()


app = FastAPI(
    title="Sinematica AI Studio",
    description="Auto Video Generator via Google Flow with Gemini 3.6 Flash & Multi-Profile Chrome Fleet Manager",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auto_error_detection_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as ex:
        log_error_diagnostic(f"HTTP {request.method} {request.url.path}", ex)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Terdeteksi Kendala Sistem ({ex}). Detail telah tersimpan di Auto-Diagnostics Log."}
        )


# Include API Routers
app.include_router(status.router)
app.include_router(storyboard.router)
app.include_router(jobs.router)
app.include_router(gallery.router)
app.include_router(settings_router.router)
app.include_router(actors.router)

# Mount Static Storage
app.mount("/storage", StaticFiles(directory=str(settings.STORAGE_DIR)), name="storage")

# Mount Web Dashboard Frontend
frontend_dir = settings.BASE_DIR / "frontend"
frontend_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
