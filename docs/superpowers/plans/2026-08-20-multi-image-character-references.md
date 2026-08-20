# Multi-Image Character References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every Casting Karakter entry own one to four images and use only those images as direct Google Flow references when generating that character's anchor sheet.

**Architecture:** A focused actor-reference module normalizes legacy records, validates uploads, and resolves exact character ownership. The actor API persists multiple images, the storyboard router carries an internal actor-reference map, and the executor uploads each character's files separately before calling Flow's existing `reference_media_ids` interface. Existing text-only characters remain unchanged.

**Tech Stack:** Python 3, FastAPI multipart forms, JSON file persistence, vanilla JavaScript/HTML/CSS, `unittest`, Google Flow bridge.

**Spec:** `docs/superpowers/specs/2026-08-20-multi-image-character-references-design.md`

## Global Constraints

- Accept JPEG, PNG, or WebP only; at most four files and 10 MiB per file.
- Preserve legacy `image_path` and `image_url` as aliases of the primary image.
- Never fuzzy-match an actor reference to a generated character.
- Never mix reference images belonging to different actors.
- Actor assets are persistent and are deleted only through explicit actor deletion.
- Characters without registered references continue through the existing text-only seed path.
- `engine/media-id.js` is unrelated user-owned work and must not be staged or modified.

---

### Task 1: Actor Reference Domain Helpers

**Files:**
- Create: `backend/actor_references.py`
- Create: `tests/test_actor_references.py`

**Interfaces:**
- Produces: `normalize_actor(actor: dict) -> dict`
- Produces: `validate_image_uploads(files: list, max_files: int = 4, max_bytes: int = 10 * 1024 * 1024) -> None`
- Produces: `actor_reference_paths(actor: dict) -> list[str]`
- Produces: `resolve_character_actor(character: dict, actors: list[dict]) -> dict | None`

- [ ] **Step 1: Write failing normalization and exact-resolution tests**

```python
def test_legacy_actor_becomes_one_primary_image():
    actor = normalize_actor({"id": "a1", "name": "Boboiboy", "image_path": "one.png", "image_url": "/one.png"})
    assert actor["images"] == [{"path": "one.png", "url": "/one.png", "primary": True}]

def test_actor_resolution_prefers_id_then_exact_normalized_name():
    actors = [{"id": "a1", "name": "Boboiboy"}, {"id": "a2", "name": "Boy"}]
    assert resolve_character_actor({"source_actor_id": "a1", "name": "Wrong"}, actors)["id"] == "a1"
    assert resolve_character_actor({"name": " boboiboy "}, actors)["id"] == "a1"
    assert resolve_character_actor({"name": "Bobo"}, actors) is None
```

- [ ] **Step 2: Run the new test and confirm RED**

Run: `python -m unittest tests.test_actor_references`
Expected: import failure because `backend.actor_references` does not exist.

- [ ] **Step 3: Implement normalization and exact ownership resolution**

```python
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

def normalize_actor(actor):
    result = dict(actor)
    images = [dict(item) for item in result.get("images") or [] if item.get("path")]
    if not images and result.get("image_path"):
        images = [{"path": result["image_path"], "url": result.get("image_url", ""), "primary": True}]
    for index, image in enumerate(images):
        image["primary"] = index == 0
    result["images"] = images
    if images:
        result["image_path"], result["image_url"] = images[0]["path"], images[0].get("url", "")
    return result

def resolve_character_actor(character, actors):
    source_id = str(character.get("source_actor_id") or "")
    if source_id:
        return next((a for a in actors if str(a.get("id")) == source_id), None)
    wanted = " ".join(str(character.get("name") or "").casefold().split())
    return next((a for a in actors if " ".join(str(a.get("name") or "").casefold().split()) == wanted), None)
```

- [ ] **Step 4: Add real fake-upload tests for count, MIME, and size validation; implement minimal validation**

Use upload-shaped objects with `content_type`, `filename`, and a seekable `file`; verify five files,
`image/gif`, and a stream larger than 10 MiB raise `ValueError`, while four valid files pass and are
rewound to position zero.

- [ ] **Step 5: Run helper tests and commit**

Run: `python -m unittest tests.test_actor_references`
Expected: PASS.

```powershell
git add -- backend/actor_references.py tests/test_actor_references.py
git commit -m "Add actor reference domain helpers"
```

### Task 2: Multi-Image Actor API and File Lifecycle

**Files:**
- Modify: `backend/routers/actors.py`
- Create: `tests/test_actors_router.py`

**Interfaces:**
- Consumes: `normalize_actor`, `validate_image_uploads`, `actor_reference_paths`
- Produces: `POST /api/actors` multipart field `image_files` plus legacy `image_file`
- Produces: actor responses containing `images`, `image_path`, and `image_url`

- [ ] **Step 1: Write failing API tests**

```python
def test_create_actor_persists_multiple_images(client):
    files = [("image_files", ("front.png", PNG, "image/png")),
             ("image_files", ("side.webp", WEBP, "image/webp"))]
    response = client.post("/api/actors", data={"name": "Boboiboy"}, files=files)
    assert response.status_code == 200
    assert len(response.json()["actor"]["images"]) == 2
    assert response.json()["actor"]["image_path"] == response.json()["actor"]["images"][0]["path"]
```

Also test five uploads return 400 without changing `actors.json`, and actor deletion removes every
image path while preserving another actor's files.

- [ ] **Step 2: Run router tests and confirm RED**

Run: `python -m unittest tests.test_actors_router`
Expected: FAIL because the endpoint accepts only `image_file`.

- [ ] **Step 3: Implement transactional multi-file persistence**

Change the endpoint signature to optional `image_files: List[UploadFile] = File(None)` and optional
legacy `image_file`. Combine them, validate before DB mutation, save UUID filenames under
`storage/actors`, build the `images` array, and unlink files written during a failed request.

- [ ] **Step 4: Normalize list responses and delete every owned actor image**

Make `list_actors()` return normalized records. In deletion, iterate `actor_reference_paths(actor)`
and unlink only resolved paths inside `ACTORS_IMAGE_DIR`; de-duplicate the legacy primary path.

- [ ] **Step 5: Run API and regression tests and commit**

Run: `python -m unittest tests.test_actors_router tests.test_gallery_cleanup`
Expected: PASS, proving Gallery cleanup still ignores `storage/actors`.

```powershell
git add -- backend/routers/actors.py tests/test_actors_router.py
git commit -m "Support multiple images per casting character"
```

### Task 3: Preserve Actor Ownership Through Storyboard Generation

**Files:**
- Modify: `backend/routers/storyboard.py`
- Modify: `backend/gemini_storyboard.py`
- Create: `tests/test_storyboard_actor_references.py`

**Interfaces:**
- Consumes: normalized actors and `actor_reference_paths`
- Produces: `_inject_actors_info(...) -> tuple[str, list[dict]]`
- Produces: storyboard `character_references: {actor_id: {name, paths}}`
- Produces: generated character field `source_actor_id`

- [ ] **Step 1: Write failing association tests**

```python
def test_selected_actor_keeps_all_owned_paths():
    info, selected = inject_selected_actors("a1", "", actors=[ACTOR_WITH_TWO_IMAGES])
    assert "source_actor_id=a1" in info
    assert selected[0]["paths"] == ["front.png", "side.png"]

def test_storyboard_reference_map_is_keyed_by_actor_id():
    storyboard = attach_character_references({"characters": [{"name": "Boboiboy"}]}, selected)
    assert storyboard["characters"][0]["source_actor_id"] == "a1"
    assert storyboard["character_references"]["a1"]["paths"] == ["front.png", "side.png"]
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m unittest tests.test_storyboard_actor_references`
Expected: FAIL because selected actor metadata is currently flattened into one string/path list.

- [ ] **Step 3: Implement selected-actor metadata and exact attachment**

Refactor the current `_inject_actors_info` into testable helpers. Continue adding all selected images
to Gemini's `image_paths`, but also attach `character_references` after storyboard generation. Match
generated characters by returned `source_actor_id`, then normalized exact name only.

- [ ] **Step 4: Require `source_actor_id` in storyboard prompts**

Add `source_actor_id` to the character JSON schema and instruct providers to copy the supplied actor
ID exactly. Apply the same association helper to normal storyboard and music-video generation.

- [ ] **Step 5: Run storyboard tests and commit**

Run: `python -m unittest tests.test_storyboard_actor_references`
Expected: PASS.

```powershell
git add -- backend/routers/storyboard.py backend/gemini_storyboard.py tests/test_storyboard_actor_references.py
git commit -m "Preserve actor references in storyboards"
```

### Task 4: Generate Character Sheets From Owned Flow References

**Files:**
- Create: `backend/character_reference_flow.py`
- Modify: `backend/jobs_executor.py`
- Create: `tests/test_character_reference_flow.py`

**Interfaces:**
- Produces: `resolve_character_reference_paths(character, storyboard) -> list[str]`
- Produces: `upload_character_references(bridge, paths, project_id, instance_id) -> list[str]`
- Consumes: `generate_character_image(..., reference_media_ids=list[str])`

- [ ] **Step 1: Write failing isolation tests**

```python
def test_character_gets_only_its_actor_paths():
    storyboard = {"character_references": {
        "a1": {"name": "Boboiboy", "paths": ["b1.png", "b2.png"]},
        "a2": {"name": "Yaya", "paths": ["y1.png"]}}}
    assert resolve_character_reference_paths({"source_actor_id": "a1"}, storyboard) == ["b1.png", "b2.png"]

def test_missing_id_does_not_fuzzy_match():
    assert resolve_character_reference_paths({"name": "Bobo"}, storyboard) == []
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m unittest tests.test_character_reference_flow`
Expected: import failure because the resolver module does not exist.

- [ ] **Step 3: Implement resolver and upload helper**

Resolve by actor ID then exact normalized name. Ignore missing/non-file paths. Upload each path through
the existing `upload_image` function, preserving order, and return the media IDs.

- [ ] **Step 4: Integrate references into mandatory seed generation**

Before each character seed attempt, resolve and upload that character's images. Pass returned IDs as
`reference_media_ids`. Add a source-of-truth clause to `char_prompt`. If IDs were supplied but
`img_res["reference_applied"]` is false, treat the attempt as failed. Log the character name and
reference count without logging local paths.

- [ ] **Step 5: Prove text-only fallback and seed guard remain intact**

Add a test where no reference mapping returns `[]` and the generated call omits reference IDs. Run:
`python -m unittest tests.test_character_reference_flow tests.test_character_seed_guard tests.test_scene_continuity`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- backend/character_reference_flow.py backend/jobs_executor.py tests/test_character_reference_flow.py
git commit -m "Guide character sheets with owned references"
```

### Task 5: Casting UI for One-to-Four Images

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/style.css`
- Create: `tests/test_actor_reference_ui.py`

**Interfaces:**
- Consumes: actor `images` array with legacy `image_url` fallback
- Produces: multipart field `image_files` repeated once per selected file

- [ ] **Step 1: Write failing source-level UI contract test**

```python
def test_actor_form_supports_multi_image_preview_and_payload():
    html = INDEX.read_text(encoding="utf-8")
    js = APP.read_text(encoding="utf-8")
    assert 'id="actorImages"' in html and "multiple" in html
    assert 'id="actorImagePreview"' in html
    assert "formData.append('image_files'" in js
    assert "MAX_ACTOR_REFERENCE_IMAGES = 4" in js
```

- [ ] **Step 2: Run UI test and confirm RED**

Run: `python -m unittest tests.test_actor_reference_ui`
Expected: FAIL because the form still has singular `actorImage`.

- [ ] **Step 3: Implement selection preview and validation**

Replace the singular input with `multiple`, render object-URL thumbnails, support removing one
selection before save, show `N/4`, reject the fifth file, and revoke object URLs when the modal resets.

- [ ] **Step 4: Submit repeated multipart fields and render actor cards**

Append every selected file under `image_files`. Render `actor.images[0]` as the primary card image,
up to three secondary thumbnails, and a visible reference count; fall back to legacy `image_url`.

- [ ] **Step 5: Run UI syntax and tests**

Run: `python -m unittest tests.test_actor_reference_ui`
Run: `node --check frontend/app.js`
Expected: both PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- frontend/index.html frontend/app.js frontend/style.css tests/test_actor_reference_ui.py
git commit -m "Add multi-image casting references UI"
```

### Task 6: Full Regression and Final Backup

**Files:**
- Modify only files required by failures directly caused by Tasks 1–5.

**Interfaces:**
- Consumes all earlier task outputs.
- Produces a verified, backward-compatible multi-image reference flow.

- [ ] **Step 1: Run the complete backend suite**

Run: `python -m unittest discover -s tests -p 'test_*.py'`
Expected: all tests PASS.

- [ ] **Step 2: Run syntax and diff checks**

Run: `python -m py_compile backend/actor_references.py backend/character_reference_flow.py backend/routers/actors.py backend/routers/storyboard.py backend/jobs_executor.py backend/gemini_storyboard.py`
Run: `node --check frontend/app.js`
Run: `git diff --check`
Expected: exit code 0 for every command.

- [ ] **Step 3: Inspect staged scope**

Run: `git status --short`
Expected: only planned files are modified; `engine/media-id.js` remains untracked and unstaged.

- [ ] **Step 4: Commit any final integration-only fixes**

```powershell
git add -- backend frontend tests
git commit -m "Complete multi-image character references"
```
