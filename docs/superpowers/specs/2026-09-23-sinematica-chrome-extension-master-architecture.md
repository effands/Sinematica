# Sinematica Chrome Extension — Master Architecture & Internal Mechanics Specification

**Document Version**: 2.0.0  
**Date**: 2026-09-23  
**Target Environment**: Chrome / Brave Browser (Manifest V3)  
**Status**: Production & Verified

---

## 1. Executive Overview

The **Sinematica Chrome Extension** is an intelligent browser-side automation and RPC bridge agent designed to interface with Google Flow (`flow.google.com`). It serves as the physical execution arm for the Sinematica AI Studio backend, executing character seed sheet generation, storyboard ingredient generation, high-density multi-prompt video generation, interaction blocking, automated error-recovery/retries, and canvas asset harvesting.

---

## 2. Component Topology & Runtime Architecture

```
                                  ┌────────────────────────┐
                                  │ Sinematica Backend     │
                                  │ (Python FastAPI / WS)  │
                                  └───────────┬────────────┘
                                              │ ws://127.0.0.1:8888/ws/agent
                                              ▼
                             ┌──────────────────────────────────┐
                             │ Extension Background Worker      │
                             │ (background.js - MV3)            │
                             └───────┬──────────────────┬───────┘
                                     │                  │
                chrome.tabs.sendMessage │                  │ chrome.scripting.executeScript
                                     ▼                  ▼
┌──────────────────────────────────────┐     ┌──────────────────────────────────────┐
│ Content Script (content.js)          │     │ Injected / Isolated Scope Engines    │
├──────────────────────────────────────┤     ├──────────────────────────────────────┤
│ • Bidirectional message bridge       │     │ • flow-executor.js (Task Execution)  │
│ • UI state observer & credit probe   │     │ • flow-composer-editor.js (Composer) │
│ • Interaction Blocker & Fake Cursor  │     │ • flow-interceptor.js (Network Sniff)│
│ • Input event composition            │     │ • flow-watcher.js (Canvas DOM Watch) │
└──────────────────┬───────────────────┘     └──────────────────┬───────────────────┘
                   │                                            │
                   └──────────────────┬─────────────────────────┘
                                      ▼
                      ┌─────────────────────────────────┐
                      │ Google Flow Canvas & DOM        │
                      │ (https://flow.google.com/...)   │
                      └─────────────────────────────────┘
```

### Key Modules:
1. **`background.js`**: Manifest V3 Service Worker managing WebSocket lifecycle (`connectWebSocket`), profile registration, direct RPC routing (`/internal/upload_image`, `/internal/generate_video`, `/internal/harvest_project_videos`), heartbeat probes, and DOM fallback scripts.
2. **`flow-executor.js`**: Modular client-side task execution engine (`FlowTaskExecutor`), orchestrating character seed creation, storyboard generation, R2V video prompt submissions, multi-reference attachment, and canvas polling.
3. **`flow-composer-editor.js`**: DOM composer helper that handles text injection across contenteditable/textarea elements, prompt parameter toggles (10s duration, portrait/landscape ratios, camera presets), and model selection.
4. **`flow-interceptor.js` & `injected.js`**: Main-world network interception layer hooking into `fetch` and `XMLHttpRequest` to capture Google Flow SAPISID auth tokens, session credits, and tRPC backend responses.
5. **`flow-tab.js`**: Tab lifecycle manager providing resilient tab discovery, lazy creation, and focus management across Chromium windows.

---

## 3. Google Flow Dual-Card Generation Lifecycle

When a video prompt is dispatched to Google Flow, Google's engine automatically generates **two companion cards** simultaneously for every prompt (dual-generation model).

```
Video Prompt Submitted ──► Google Flow Spawns 2 Tiles
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
      Tile A (Glitched / Error)            Tile B (Generating)
            │                                     │
      Detects Error Message                 Progresses (18%..50%..90%)
            │                                     │
      Triggers Retry (Up to 2x)             Completes to 100%
            │                                     │
      DO NOT ABORT EARLY! ───────────────► Resolves Usable Video URL
                                                  │
                                            Scene Success & Saved!
```

### Critical Rules for Resilience:
1. **Never Abort Early on Single Tile Failure**: If Tile A produces `<flow-error-tile>` ("Maaf, video ini gagal dibuat" / "Sorry, this video failed"), the engine immediately attempts an automated click on the `Retry` button (up to 2 attempts).
2. **Sibling Polling Continuity**: The polling loop strictly continues until `renderDeadline` (or resolution of a completed video). The failure of one card never aborts the execution while the sibling card is rendering.
3. **Unclaimed Candidate Resolution**: When scanning completed video tiles, the engine compares candidates against `_seenVideoUrls` (Extension) and `claimed_urls` (Backend) to ensure scene videos are strictly distinct.

---

## 4. User Interaction Blocking & Synthetic Bypass Architecture

To ensure automation stability while keeping the user informed:

```
                  ┌────────────────────────────────────────────────────────┐
                  │ User Interaction Blocker Overlay                       │
                  │ ID: #sinematica-interaction-blocker                    │
                  │ Styles: pointer-events: all; z-index: 2147483647;       │
                  └──────────────────────────┬─────────────────────────────┘
                                             │
             ┌───────────────────────────────┴──────────────────────────────┐
             ▼                                                              ▼
   User Physical Clicks / Keystrokes                            Synthetic Automation Clicks
   • Blocked by overlay layer                                    • Sets window.__sinematicaAllowInput = true
   • Prevents accidental form resets                             • Dispatches bypass events (composed: true)
   • Prevents navigation interruptions                           • Direct element .click() & .focus()
```

### Safety Cleanup:
- Whenever an operation finishes, errors out, or disconnects, `window.__sinematicaUnblock()` and `document.getElementById('sinematica-interaction-blocker').remove()` are executed in a `finally` block to prevent UI lockups.

---

## 5. Ingredient Reference Attachment Subsystem

Video generation in Sinematica requires multi-image reference conditioning ("Ingredients"):
1. **Priority Hierarchy**:
   - **Priority 1 (Primary)**: Scene Storyboard Ingredient Image (`storyboard_XX.png`).
   - **Priority 2+ (Characters)**: Character Seed Sheet Masters (`Sheet Character 1.png`, `Sheet Character 2.png`).
2. **Clipboard Paste Emulation**:
   - Images are fetched as Base64/Blob, converted into standard `File` objects, and injected via a synthetic `ClipboardEvent('paste')` with full DataTransfer item lists.
3. **DOM Chip Verification**:
   - The composer verifies that image reference chips appear in the prompt bar before clicking the Generate button.

---

## 6. Multi-Scene Video Deduplication & Canvas Harvest Reconciliation

When multiple scenes are rendered in sequence:

```
Scene 1 Dispatched ──► Canvas Video A Generated ──► Claimed into claimed_urls { Video A }
                                                                 │
Scene 2 Dispatched ──► Canvas Video B Generated ──► Checked: Video B != Video A
                                                                 │
                                                    Claimed into claimed_urls { Video A, Video B }
```

### Harvest Reconciliation Algorithm:
If a network disconnect or browser restart occurs mid-render:
1. Backend calls `/internal/harvest_project_videos` via WebSocket bridge.
2. Extension scans the Google Flow canvas for all completed video tiles in chronological order.
3. Unclaimed videos (those not in `claimed_urls`) are matched against missing scenes by prompt/action keywords.
4. Each distinct video is downloaded to its dedicated file (`scene_01.mp4`, `scene_02.mp4`) without duplicating contents.

---

## 7. Multilingual Support & Selectors

Google Flow interfaces dynamically render in Indonesian, English, and other regional locales. All selector probes support bilingual patterns:

| Target Element | English Selector / Text | Indonesian Selector / Text |
| :--- | :--- | :--- |
| **Error Card** | `Sorry, this video failed`, `Could not generate` | `Maaf, video ini gagal dibuat`, `Gagal` |
| **Retry Button** | `Retry`, `Try again`, `aria-label="Retry"` | `Coba lagi`, `Ulang`, `aria-label="Coba lagi"` |
| **Play Badge** | `aria-label="Play"`, `play_arrow` | `aria-label="Putar"`, `play_arrow` |
| **Duration Switch** | `10s`, `10 seconds` | `10 dtk`, `10 detik` |
| **Aspect Ratio** | `Portrait (9:16)`, `Landscape (16:9)` | `Potret (9:16)`, `Lanskap (16:9)` |

---

## 8. Verification & Operational Protocols

- **Extension Syntax Verification**: `node -c engine/chrome-extension/*.js`
- **Unit & Integration Suite**: `node engine/chrome-extension/flow-executor.test.js`, `node engine/chrome-extension/flow-retry.test.js`, `node engine/chrome-extension/flow-video-retry-isolation.test.js`
- **End-to-End Execution**: `python run_e2e_pipeline.py --scenes 2 --duration 10`
