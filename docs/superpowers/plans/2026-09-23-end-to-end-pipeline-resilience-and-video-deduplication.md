# End-to-End Pipeline Resilience, Dual-Card Handling, and Video Deduplication System

**Plan & Implementation Review**: 2026-09-23  
**Components**: `backend/jobs_executor.py`, `backend/fleet_logger.py`, `engine/chrome-extension/`, `run_e2e_pipeline.py`  
**Status**: Completed & Verified

---

## 1. Background & Problems Solved

During end-to-end automated movie production runs on Google Flow, several critical failure modes and performance issues were identified:
1. **Context Exhaustion from Large Screenshots**: Uncompressed image attachments previously consumed hundreds of thousands of tokens, exhausting the context limit.
2. **Premature Video Generation Abort**: Google Flow operates a dual-generation pipeline (generating 2 video tiles per prompt). When 1 tile encountered an error, the extension previously aborted after 12 seconds, killing the render even while the sibling card was rendering normally at 18%..50%.
3. **Duplicate Scene Video Claiming**: Without strict URL tracking, Scene 2 occasionally claimed the same video URL as Scene 1 from the canvas.
4. **Canvas Harvest Timeout**: Project canvas video reconciliation timed out at 45 seconds when multiple cards were present on the project canvas.
5. **Backend Variable NameError**: An unresolved variable reference (`active_profiles`) in `jobs_executor.py` caused intermittent reconciliation crashes.

---

## 2. Implemented Architecture & Solutions

### A. Non-Destructive Polling & Dual-Card Resilience
- Updated `background.js` and `flow-executor.js` to continue the polling loop until `renderDeadline` even if an error card is detected.
- If a retry button is available on an error tile, the extension triggers up to 2 retry clicks automatically.
- Fatal generation failure errors are never returned early inside the loop; only when the entire timeout has elapsed without any usable video URL does the engine fail.

### B. Strict Multi-Scene Deduplication
- Integrated `claimed_urls` tracking in `backend/jobs_executor.py` and `_seenVideoUrls` in `flow-executor.js`.
- During video polling and canvas harvesting, previously claimed scene URLs are filtered out so each scene receives a distinct video file with unique size and content.

### C. Enhanced Harvest Timeout & Error Handling
- Increased backend harvest timeout from 45s to 90s in `backend/jobs_executor.py`.
- Fixed the `active_profiles` reference by properly deriving `live_instances` from `bridge.instance_snapshot()`.

### D. Production Diagnostic Logging System
- Built `ProductionExecutionLogger` in `run_e2e_pipeline.py` emitting structured JSONL (`data/logs/*.jsonl`) and formatted console cards with Root Cause, Evidence, and Technical Troubleshooting advice.

---

## 3. Verification & Evidence

1. **Unit Test Verification**:
   - `node engine/chrome-extension/flow-executor.test.js` (8/8 passing)
   - `node engine/chrome-extension/flow-retry.test.js` (4/4 passing)
   - `node engine/chrome-extension/flow-video-retry-isolation.test.js` (1/1 passing)
2. **Backend Syntax Verification**:
   - `python -m py_compile backend/jobs_executor.py` (0 errors)
   - `node -c engine/chrome-extension/*.js` (0 errors)
3. **Physical File Verification in `storage/jobs/<job_id>/`**:
   - Master Character Sheet images generated and cached (`Sheet Pak Danu.png`, `Sheet Baskoro Pratama.png`).
   - Storyboard Ingredient images downloaded (`storyboard_01.png`, `storyboard_02.png`, ~620–650 KB).
   - Distinct video outputs (`scene_01.mp4`, `scene_02.mp4`).
