# Storyboard-First Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every Flow video starts from a locally cached scene storyboard uploaded into the rendering profile's own project.

**Architecture:** Character sheets remain inputs to scene-storyboard composition. A local storyboard artifact becomes the boundary between composition and rendering; each candidate Chrome profile uploads that artifact into its own Flow project before I2V submission. Submission/render failures may change profiles, while download failures retry against the profile that owns the completed media and never submit another render.

**Tech Stack:** Python 3, FastAPI backend, `unittest`, Google Flow Chrome-extension bridge, existing OmniFlash generators

**Spec:** `docs/superpowers/specs/2026-08-19-storyboard-first-and-multi-provider-design.md`

## Global Constraints

- Character sheets must never be submitted as a video's start image.
- The local storyboard image is the sole I2V start-image reference.
- Flow media IDs must only be used with the Chrome profile and project that created them.
- A download failure must not submit a second render.
- Complete storyboard failure must fail the scene explicitly; no silent T2V fallback.
- Preserve unrelated working-tree changes.

---

### Task 1: Local storyboard artifact helpers

**Files:**
- Modify: `backend/jobs_executor.py` near `download_file` and storyboard creation
- Create: `tests/test_storyboard_artifacts.py`

**Interfaces:**
- Consumes: `ExtensionBridge.download_url(url, instance_id)` and `Path`
- Produces: `async cache_remote_media(bridge, source: str, destination: Path, instance_id: str | None) -> Path`
- Produces: `find_character_sheet_path(character: dict, character_image_paths: dict) -> str | None`

- [ ] **Step 1: Write failing tests for deterministic local-path lookup and authenticated caching**

```python
class StoryboardArtifactTests(unittest.IsolatedAsyncioTestCase):
    def test_character_sheet_lookup_accepts_numeric_id_and_lowercase_name(self):
        paths = {1: "rara.png", "siska": "siska.png"}
        self.assertEqual(find_character_sheet_path({"id": 1, "name": "Rara"}, paths), "rara.png")
        self.assertEqual(find_character_sheet_path({"id": "2", "name": "Siska"}, paths), "siska.png")

    async def test_remote_storyboard_is_cached_through_owning_profile(self):
        bridge = FakeDownloadBridge(b"png-bytes")
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "storyboard_01.png"
            result = await cache_remote_media(bridge, "https://private/image", target, "profile-a")
            self.assertEqual(result.read_bytes(), b"png-bytes")
            self.assertEqual(bridge.calls, [("https://private/image", "profile-a")])
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_storyboard_artifacts -v`

Expected: FAIL because both helper functions are absent.

- [ ] **Step 3: Implement the helpers and use local paths when composing via Gemini**

```python
def find_character_sheet_path(character, paths):
    cid = character.get("id")
    name = str(character.get("name") or "").strip()
    for key in (cid, str(cid) if cid is not None else None, name, name.lower()):
        if key is not None and paths.get(key):
            return paths[key]
    return None


async def cache_remote_media(bridge, source, destination, instance_id=None):
    result = await bridge.download_url(source, instance_id=instance_id)
    destination.write_bytes(result["data"])
    return destination
```

When assembling Gemini references, prefer `find_character_sheet_path(c, character_image_paths)` and read the local bytes. Do not fall back to a private Flow URL when a local sheet exists.

- [ ] **Step 4: Run the focused tests and compile the module**

Run: `python -m unittest tests.test_storyboard_artifacts -v`

Expected: PASS.

Run: `python -m compileall -q backend/jobs_executor.py`

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/jobs_executor.py tests/test_storyboard_artifacts.py
git commit -m "fix: cache storyboard inputs locally"
```

### Task 2: Require a local storyboard before rendering

**Files:**
- Modify: `backend/jobs_executor.py` in the per-scene storyboard block
- Modify: `tests/test_storyboard_artifacts.py`

**Interfaces:**
- Consumes: `cache_remote_media(bridge, source, destination, instance_id)`
- Produces: `async materialize_storyboard_image(bridge, image_result: dict, destination: Path, instance_id: str | None) -> Path`
- Produces: scene field `storyboard_local_path: str`

- [ ] **Step 1: Write failing tests for Flow-created storyboard materialization**

```python
async def test_flow_storyboard_result_becomes_local_artifact(self):
    bridge = FakeDownloadBridge(b"flow-storyboard")
    result = {"media_id": "media-1", "image_url": "https://private/storyboard.png"}
    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / "storyboard_01.png"
        path = await materialize_storyboard_image(bridge, result, target, "profile-a")
        self.assertEqual(path.read_bytes(), b"flow-storyboard")

async def test_storyboard_without_bytes_or_url_raises_specific_error(self):
    with self.assertRaisesRegex(RuntimeError, "storyboard.*lokal"):
        await materialize_storyboard_image(FakeDownloadBridge(b""), {"media_id": "media-1"}, Path("unused"), "profile-a")
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_storyboard_artifacts.StoryboardArtifactTests -v`

Expected: FAIL because `materialize_storyboard_image` is absent.

- [ ] **Step 3: Implement materialization and enforce the boundary**

```python
async def materialize_storyboard_image(bridge, image_result, destination, instance_id=None):
    inline = image_result.get("image_bytes")
    if inline:
        destination.write_bytes(inline)
        return destination
    source = image_result.get("image_url")
    if source:
        return await cache_remote_media(bridge, source, destination, instance_id)
    raise RuntimeError("Gambar storyboard tidak tersedia sebagai file lokal")
```

Set `scene_record["storyboard_local_path"]` after either Gemini or Flow composition. If no local artifact exists after both composition routes, set the scene error to `Gambar storyboard adegan gagal dibuat` and skip video submission.

- [ ] **Step 4: Run focused and existing tests**

Run: `python -m unittest tests.test_storyboard_artifacts tests.test_bridge_download -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/jobs_executor.py tests/test_storyboard_artifacts.py
git commit -m "fix: require local storyboard artifacts"
```

### Task 3: Upload storyboard per rendering profile and submit I2V only

**Files:**
- Create: `backend/flow_scene_renderer.py`
- Modify: `backend/jobs_executor.py` in the Chrome-profile render loop
- Create: `tests/test_flow_scene_renderer.py`

**Interfaces:**
- Consumes: `upload_image`, `generate_video_i2v`, local storyboard path, profile ID, project ID
- Produces: `async submit_storyboard_i2v(bridge, storyboard_path: str, prompt: str, aspect: str, duration: int, project_id: str, instance_id: str) -> dict`
- Return shape: `{"media_id": str, "storyboard_media_id": str, "project_id": str, "instance_id": str, "generation_mode": "I2V_STORYBOARD"}`

- [ ] **Step 1: Write the failing renderer contract tests**

```python
class FlowSceneRendererTests(unittest.IsolatedAsyncioTestCase):
    async def test_uploads_storyboard_to_candidate_project_then_uses_it_as_start_image(self):
        calls = []
        async def fake_upload(bridge, path, project_id, instance_id):
            calls.append(("upload", path, project_id, instance_id))
            return "storyboard-media-a"
        async def fake_i2v(**kwargs):
            calls.append(("i2v", kwargs))
            return ["video-media-a"]

        result = await submit_storyboard_i2v(
            object(), "storyboard.png", "prompt", "portrait", 10,
            "project-a", "profile-a", upload_fn=fake_upload, i2v_fn=fake_i2v,
        )

        self.assertEqual(calls[0], ("upload", "storyboard.png", "project-a", "profile-a"))
        self.assertEqual(calls[1][1]["start_image_id"], "storyboard-media-a")
        self.assertEqual(result["generation_mode"], "I2V_STORYBOARD")
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_flow_scene_renderer -v`

Expected: FAIL because `backend.flow_scene_renderer` is absent.

- [ ] **Step 3: Implement the focused renderer module**

```python
async def submit_storyboard_i2v(bridge, storyboard_path, prompt, aspect, duration,
                                project_id, instance_id, upload_fn=upload_image,
                                i2v_fn=generate_video_i2v):
    storyboard_media_id = await upload_fn(
        bridge, storyboard_path, project_id=project_id, instance_id=instance_id
    )
    media_ids = await i2v_fn(
        bridge=bridge, prompt=prompt, aspect=aspect, project_id=project_id,
        start_image_id=storyboard_media_id, duration=duration,
        instance_id=instance_id,
    )
    if not media_ids:
        raise RuntimeError("Flow tidak mengembalikan media ID video I2V")
    return {
        "media_id": media_ids[0], "storyboard_media_id": storyboard_media_id,
        "project_id": project_id, "instance_id": instance_id,
        "generation_mode": "I2V_STORYBOARD",
    }
```

Replace the R2V/character-sheet-I2V/T2V branch in `jobs_executor.py` with this function. Record `flow_project_id`, `storyboard_media_id`, and `generation_mode` on the scene.

- [ ] **Step 4: Run renderer tests and compilation**

Run: `python -m unittest tests.test_flow_scene_renderer -v`

Expected: PASS.

Run: `python -m compileall -q backend engine`

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/flow_scene_renderer.py backend/jobs_executor.py tests/test_flow_scene_renderer.py
git commit -m "fix: render scenes from storyboard images"
```

### Task 4: Separate render failover from download retry

**Files:**
- Modify: `backend/flow_scene_renderer.py`
- Modify: `backend/jobs_executor.py`
- Modify: `tests/test_flow_scene_renderer.py`

**Interfaces:**
- Consumes: successful submission record from `submit_storyboard_i2v`
- Produces: `async download_completed_video(bridge, video_url: str, destination: Path, instance_id: str, attempts: int = 3) -> Path`

- [ ] **Step 1: Write a failing test proving download retry never resubmits**

```python
async def test_download_retries_owner_profile_without_submitting_again(self):
    bridge = FlakyDownloadBridge(failures=1, payload=b"video")
    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / "scene.mp4"
        result = await download_completed_video(
            bridge, "https://private/video", target, "profile-a", attempts=2
        )
        self.assertEqual(result.read_bytes(), b"video")
        self.assertEqual(bridge.instance_ids, ["profile-a", "profile-a"])
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_flow_scene_renderer.FlowSceneRendererTests.test_download_retries_owner_profile_without_submitting_again -v`

Expected: FAIL because the helper is absent.

- [ ] **Step 3: Implement bounded download retry and restructure the caller**

```python
async def download_completed_video(bridge, video_url, destination, instance_id, attempts=3):
    last_error = None
    for _ in range(attempts):
        try:
            result = await bridge.download_url(video_url, instance_id=instance_id)
            destination.write_bytes(result["data"])
            return destination
        except Exception as ex:
            last_error = ex
    raise RuntimeError(f"Unduhan video selesai gagal: {last_error}")
```

In `jobs_executor.py`, profile failover surrounds only upload, I2V submission, and polling. Once polling succeeds, store the owner profile and exit the submission loop before downloading. Invoke `download_completed_video` afterward.

- [ ] **Step 4: Run the full tests and static checks**

Run: `python -m unittest discover -s tests -v`

Expected: all PASS.

Run: `python -m compileall -q backend engine`

Expected: exit 0.

Run: `node --check engine/chrome-extension/background.js`

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/flow_scene_renderer.py backend/jobs_executor.py tests/test_flow_scene_renderer.py
git commit -m "fix: keep downloads on render owner profile"
```

### Task 5: Flow smoke verification and log clarity

**Files:**
- Modify: `backend/jobs_executor.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: scene render metadata from Tasks 2–4
- Produces: stage-specific logs and documented reload/smoke procedure

- [ ] **Step 1: Add assertions to existing renderer tests for metadata and stage-specific errors**

```python
self.assertEqual(result["project_id"], "project-a")
self.assertEqual(result["instance_id"], "profile-a")
self.assertEqual(result["storyboard_media_id"], "storyboard-media-a")
```

- [ ] **Step 2: Run the tests and confirm any missing metadata assertion fails**

Run: `python -m unittest tests.test_flow_scene_renderer -v`

Expected: FAIL if a required metadata field is not yet recorded by the caller-facing result.

- [ ] **Step 3: Add explicit logs and README smoke steps**

Required log stages:

```text
[Storyboard] File lokal siap
[Storyboard Upload] profile/project/media ID
[I2V Storyboard] request diterima
[Render Poll] completed media ID
[Download] attempt N on owner profile
```

README smoke procedure: reload the unpacked Chrome extension, restart the backend, run one two-scene film with two connected profiles, and verify the Flow project shows character sheets, storyboard images, then videos in that order.

- [ ] **Step 4: Run final automated verification**

Run: `python -m unittest discover -s tests -v`

Expected: all PASS.

Run: `python -m compileall -q backend engine && node --check engine/chrome-extension/background.js`

Expected: exit 0.

- [ ] **Step 5: Perform manual two-profile smoke run**

Expected: each scene uploads its storyboard into the selected profile's project immediately before I2V; no character-sheet I2V, R2V 404, or T2V fallback appears in logs.

- [ ] **Step 6: Commit**

```bash
git add backend/jobs_executor.py README.md tests/test_flow_scene_renderer.py
git commit -m "docs: verify storyboard-first Flow pipeline"
```
