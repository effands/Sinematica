# Automated E2E Scene Master Test Runner & Batch Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a one-click automated E2E testing tool (`test_generation.bat` and `scripts/test_e2e_generation.py`) that executes real scene generation directly from Scene Master / saved job history without requiring browser UI interaction, auto-starts the server if needed, verifies Chrome fleet connectivity, and streams clean, real-time generation logs with exit status reporting.

**Architecture:**
- `scripts/test_e2e_generation.py`: Core CLI test runner that:
  - Probes `http://127.0.0.1:8888` health; auto-starts uvicorn background server if not already running.
  - Verifies Chrome Extension WebSocket fleet connection (`/api/fleet`, `/api/status`).
  - Reads Scene Master / latest job from `data/jobs_history.json` or `/api/jobs/list`.
  - Invokes `/api/jobs/{job_id}/resume` (or `/api/jobs/create`) with optional scene limit/range flags (`--scene`, `--limit`, `--job-id`).
  - Streams real-time formatted log events (`[SYS]`, `[IMAGE]`, `[VIDEO]`, `[PROGRESS]`, `[SUCCESS]`, `[ERROR]`).
  - Evaluates job completion, verifies generated asset files on disk, and outputs a formatted summary table before exiting with code `0` (success) or `1` (failure).
- `test_generation.bat`: Windows batch launcher in the root workspace that sets UTF-8 mode, activates Python environment, passes CLI arguments, and keeps the terminal open for review.
- `tests/test_e2e_runner.py`: Unit test suite for the CLI test runner logic (argument parser, history discovery, log formatting, and server probe).

**Tech Stack:** Python 3 (FastAPI, urllib/requests, asyncio/threading, argparse), Windows Batch Script (.bat), ANSI terminal formatting, pytest.

**Spec:** Requirement from user query: automated E2E generation testing from Scene Master scenes via single batch file with clean, high-detail test logs and zero manual browser clicking.

---

## Global Constraints
- Run against real production backend endpoints (`/api/jobs/resume`, `/api/jobs/create`, `/api/fleet`, `/api/status`) so test success guarantees actual application functionality.
- Filter out unrelated HTTP polling logs (`GET /api/fleet 200 OK`) and present clean, color-coded generation milestones.
- Support both already-running server instances and automatic headless server startup.
- Graceful shutdown handling (`Ctrl+C` cancels job cleanly via `/api/jobs/{id}/cancel`).

---

### Task 1: Core E2E Test Runner Engine (`scripts/test_e2e_generation.py`)

**Files:**
- Create: `scripts/test_e2e_generation.py`
- Test: `tests/test_e2e_runner.py`

**Interfaces:**
- Produces:
  - `check_server_health(base_url: str, timeout: float = 2.0) -> bool`
  - `ensure_server_running(base_url: str, port: int = 8888) -> Optional[subprocess.Popen]`
  - `check_fleet_ready(base_url: str) -> tuple[bool, str, list]`
  - `find_latest_scene_master_job(history_file_path: Path) -> Optional[dict]`
  - `trigger_job_resume(base_url: str, job_id: str, limit: Optional[int] = None, scene_start: Optional[int] = None, scene_end: Optional[int] = None) -> dict`
  - `stream_job_logs_until_completion(base_url: str, job_id: str, poll_interval: float = 1.0) -> dict`
  - `format_log_line(entry: dict) -> str`
  - `main(argv: Optional[List[str]] = None) -> int`

- [x] **Step 1: Write the failing test**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Implement `scripts/test_e2e_generation.py`**
- [x] **Step 4: Run test to verify it passes**

---

### Task 2: Windows Batch Launcher (`test_generation.bat`)

**Files:**
- Create: `test_generation.bat`

**Interfaces:**
- Windows command file executing `python scripts/test_e2e_generation.py %*` with proper environment activation and terminal pause on exit.

- [x] **Step 1: Create `test_generation.bat`**
- [x] **Step 2: Test CLI argument passing and help flags**

---

### Task 3: Comprehensive Verification & Regression Check

**Files:**
- Test: `python -m pytest tests/`
- Test: `node --test engine/chrome-extension/*.test.js`

- [x] **Step 1: Run all Python backend unit tests**
- [x] **Step 2: Run all Chrome Extension tests**
- [x] **Step 3: Test runner dry-run / probe validation**
