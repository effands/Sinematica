# Multi-Provider Key Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide persistent per-provider API-key rotation and automatic text-generation fallback across Gemini, OpenAI, DeepSeek, Groq, and local Web2API.

**Architecture:** A thread-safe key store owns ordered provider keys and atomic persistence. Focused provider adapters normalize native Gemini and OpenAI-compatible APIs behind one text-generation contract, while a provider manager applies retry, rotation, and provider failover. Existing Gemini call sites migrate incrementally to that manager; Gemini image generation uses the same key store but remains Gemini-only.

**Tech Stack:** Python 3, FastAPI, `requests`, `google-generativeai`, `unittest`, vanilla JavaScript settings UI

**Spec:** `docs/superpowers/specs/2026-08-19-storyboard-first-and-multi-provider-design.md`

## Global Constraints

- Default provider order is Gemini, OpenAI, DeepSeek, Groq, then local Web2API.
- Only quota/rate-limit errors reorder keys.
- Full API keys must never appear in logs.
- Gemini remains the only cloud image provider.
- Saving keys removes blanks and duplicates while preserving order.
- Legacy `gemini_api_key` settings remain compatible.
- Preserve unrelated working-tree changes.

---

### Task 1: Thread-safe persistent provider key store

**Files:**
- Create: `backend/provider_keys.py`
- Modify: `backend/settings.py`
- Create: `tests/test_provider_keys.py`

**Interfaces:**
- Consumes: `settings.get_settings()` and `settings.save_settings(updates)`
- Produces: `normalize_keys(value) -> list[str]`
- Produces: `get_provider_keys(provider: str) -> list[str]`
- Produces: `demote_provider_key(provider: str, key: str) -> list[str]`
- Produces: `classify_provider_error(error) -> Literal["quota", "auth", "transient", "other"]`

- [ ] **Step 1: Write failing normalization, classification, and persistence tests**

```python
class ProviderKeyTests(unittest.TestCase):
    def test_demote_moves_quota_key_to_bottom_and_persists(self):
        store = InMemorySettings({"gemini_api_keys": ["a", "b", "c"]})
        result = demote_provider_key("gemini", "a", load=store.load, save=store.save)
        self.assertEqual(result, ["b", "c", "a"])
        self.assertEqual(store.data["gemini_api_keys"], ["b", "c", "a"])
        self.assertEqual(store.data["gemini_api_key"], "b")

    def test_quota_error_is_classified_without_matching_unrelated_400(self):
        self.assertEqual(classify_provider_error("429 RESOURCE_EXHAUSTED quota exceeded"), "quota")
        self.assertEqual(classify_provider_error("401 invalid api key"), "auth")
        self.assertEqual(classify_provider_error("400 malformed JSON"), "other")
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_provider_keys -v`

Expected: FAIL because `backend.provider_keys` is absent.

- [ ] **Step 3: Implement normalized fields and atomic locked demotion**

```python
PROVIDER_KEY_FIELDS = {
    "gemini": ("gemini_api_keys", "gemini_api_key"),
    "openai": ("openai_api_keys", "openai_api_key"),
    "deepseek": ("deepseek_api_keys", "deepseek_api_key"),
    "groq": ("groq_api_keys", "groq_api_key"),
}

def normalize_keys(value):
    raw = value if isinstance(value, list) else str(value or "").replace("\n", ",").split(",")
    return list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))
```

Use a module-level `threading.RLock`. Under the lock, reload current settings, rotate exactly one matching key, mirror the first key to the legacy field, and persist through `save_settings`.

- [ ] **Step 4: Add a concurrency test**

```python
def test_concurrent_demotions_preserve_each_key_once(self):
    store = InMemorySettings({"gemini_api_keys": ["a", "b", "c"]})
    threads = [
        threading.Thread(
            target=demote_provider_key,
            args=("gemini", key),
            kwargs={"load": store.load, "save": store.save},
        )
        for key in ("a", "b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    final_keys = store.data["gemini_api_keys"]
    self.assertEqual(sorted(final_keys), ["a", "b", "c"])
    self.assertEqual(len(final_keys), 3)
```

- [ ] **Step 5: Run tests and compile**

Run: `python -m unittest tests.test_provider_keys -v`

Expected: all PASS.

Run: `python -m compileall -q backend/provider_keys.py backend/settings.py`

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/provider_keys.py backend/settings.py tests/test_provider_keys.py
git commit -m "feat: persist provider key rotation"
```

### Task 2: Provider adapters and normalized result contract

**Files:**
- Create: `backend/text_providers.py`
- Create: `tests/test_text_providers.py`
- Modify: `requirements.txt` only if the existing `requests` dependency is insufficient (no new SDK is required)

**Interfaces:**
- Produces: `ProviderRequest(prompt: str, json_output: bool = False, model: str | None = None)`
- Produces: `ProviderResult(text: str, provider: str, model: str, key_index: int | None)`
- Produces: `GeminiAdapter.generate(request, key) -> ProviderResult`
- Produces: `OpenAICompatibleAdapter(name, base_url).generate(request, key) -> ProviderResult`

- [ ] **Step 1: Write failing adapter contract tests with HTTP transport injected**

```python
def test_openai_compatible_adapter_parses_chat_completion(self):
    transport = FakeTransport({"choices": [{"message": {"content": "{\"ok\":true}"}}]})
    adapter = OpenAICompatibleAdapter("deepseek", "https://api.deepseek.com/v1", transport=transport)
    result = adapter.generate(ProviderRequest("prompt", json_output=True, model="deepseek-chat"), "key-a")
    self.assertEqual(result.text, '{"ok":true}')
    self.assertEqual(transport.last_headers["Authorization"], "Bearer key-a")
    self.assertEqual(transport.last_json["response_format"], {"type": "json_object"})
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_text_providers -v`

Expected: FAIL because the adapter module is absent.

- [ ] **Step 3: Implement dataclasses and adapters**

```python
@dataclass
class ProviderRequest:
    prompt: str
    json_output: bool = False
    model: str | None = None

@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    key_index: int | None = None
```

OpenAI-compatible URLs:

- OpenAI: `https://api.openai.com/v1/chat/completions`
- DeepSeek: `https://api.deepseek.com/v1/chat/completions`
- Groq: `https://api.groq.com/openai/v1/chat/completions`

Raise `ProviderCallError(provider, classification, status, message)` for normalized failures. Do not log request headers.

- [ ] **Step 4: Add tests for 429 and authentication normalization**

```python
with self.assertRaises(ProviderCallError) as caught:
    quota_adapter.generate(request, "key-a")
self.assertEqual(caught.exception.classification, "quota")
```

- [ ] **Step 5: Run adapter tests**

Run: `python -m unittest tests.test_text_providers -v`

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/text_providers.py tests/test_text_providers.py requirements.txt
git commit -m "feat: add text provider adapters"
```

### Task 3: Provider manager with key and provider failover

**Files:**
- Create: `backend/text_generation.py`
- Modify: `tests/test_text_providers.py`

**Interfaces:**
- Consumes: adapters from Task 2 and key-store functions from Task 1
- Produces: `generate_text(prompt: str, json_output: bool = False, provider_order: list[str] | None = None) -> ProviderResult`

- [ ] **Step 1: Write failing manager behavior tests**

```python
def test_quota_demotes_key_and_immediately_uses_next_key(self):
    adapter = SequenceAdapter({"a": ProviderCallError("gemini", "quota", 429, "quota"), "b": "ok"})
    manager = TextGenerationManager(adapters={"gemini": adapter}, key_store=MemoryKeyStore({"gemini": ["a", "b"]}))
    result = manager.generate("prompt", provider_order=["gemini"])
    self.assertEqual(result.text, "ok")
    self.assertEqual(manager.key_store.keys("gemini"), ["b", "a"])

def test_exhausted_provider_advances_to_next_provider(self):
    manager = manager_with_quota_gemini_and_successful_openai()
    self.assertEqual(manager.generate("prompt").provider, "openai")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_text_providers -v`

Expected: FAIL because `TextGenerationManager` is absent.

- [ ] **Step 3: Implement ordered failover**

```python
for provider in order:
    keys = key_store.keys(provider)
    for key_index, key in enumerate(keys):
        try:
            return adapters[provider].generate(request, key, key_index=key_index)
        except ProviderCallError as ex:
            if ex.classification == "quota":
                key_store.demote(provider, key)
                continue
            if ex.classification == "auth":
                continue
            if ex.classification == "transient":
                retry_once()
                continue
            continue
```

After cloud providers are exhausted, call the existing Web2API endpoint through a `Web2APIAdapter`. Log provider name and one-based key index only.

- [ ] **Step 4: Add non-quota ordering and provider exhaustion tests**

```python
def test_malformed_response_does_not_reorder_keys(self):
    # Assert original order remains unchanged after classification "other".
```

- [ ] **Step 5: Run focused tests and compile**

Run: `python -m unittest tests.test_provider_keys tests.test_text_providers -v`

Expected: all PASS.

Run: `python -m compileall -q backend/text_generation.py backend/text_providers.py`

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/text_generation.py backend/text_providers.py tests/test_text_providers.py
git commit -m "feat: auto switch text providers"
```

### Task 4: Migrate text-only Gemini call sites

**Files:**
- Modify: `backend/gemini_storyboard.py`
- Create: `tests/test_gemini_storyboard_provider_fallback.py`

**Interfaces:**
- Consumes: `generate_text(prompt: str, json_output: bool = False, provider_order: list[str] | None = None)` from Task 3
- Produces: unchanged public return shapes from `auto_suggest_details`, `generate_storyboard`, `regenerate_single_scene`, `generate_youtube_metadata`, `generate_music_video_storyboard`, and `sanitize_prompt_for_policy`

- [ ] **Step 1: Write characterization tests for public JSON return shapes with injected text generator**

```python
def test_auto_suggest_accepts_provider_result_without_changing_response_shape(self):
    result = auto_suggest_details("theme", text_generator=lambda **_: ProviderResult(AUTO_SUGGEST_JSON, "openai", "gpt-4.1-mini"))
    self.assertIn("title", result)
    self.assertIn("premise", result)

def test_storyboard_records_non_gemini_provider(self):
    result = generate_storyboard(
        "A baker saves the family shop",
        scene_count=1,
        text_generator=fake_deepseek_generator,
    )
    self.assertEqual(result["generated_via"], "deepseek")
```

- [ ] **Step 2: Run characterization tests and verify RED on the injected interface**

Run: `python -m unittest tests.test_gemini_storyboard_provider_fallback -v`

Expected: FAIL because callers do not accept `text_generator` and still own key loops.

- [ ] **Step 3: Replace duplicated key/model loops with the central generator**

Use `generate_text(prompt=prompt, json_output=True)` at each text-only call site and keep `_extract_json_text` plus existing validation. Record `generated_via` and `generated_model` without changing required storyboard fields.

- [ ] **Step 4: Run migration tests and existing suite**

Run: `python -m unittest tests.test_gemini_storyboard_provider_fallback -v`

Expected: PASS.

Run: `python -m unittest discover -s tests -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/gemini_storyboard.py tests/test_gemini_storyboard_provider_fallback.py
git commit -m "refactor: route text generation through providers"
```

### Task 5: Apply persistent rotation to Gemini image requests

**Files:**
- Modify: `backend/storyboard_image.py`
- Create: `tests/test_storyboard_image_key_rotation.py`

**Interfaces:**
- Consumes: `get_provider_keys("gemini")`, `demote_provider_key("gemini", key)`, and `classify_provider_error`
- Produces: unchanged `generate_storyboard_sheet(prompt: str, reference_images: list[dict]) -> dict` result contract

- [ ] **Step 1: Write failing image-key rotation test**

```python
def test_image_quota_rotates_key_and_uses_next_key(self):
    transport = ImageSequenceTransport({"a": Response(429), "b": Response(200, image=PNG_BYTES)})
    result = generate_storyboard_sheet("prompt", [REFERENCE], transport=transport, key_store=store)
    self.assertEqual(result["image"], PNG_BYTES)
    self.assertEqual(store.keys("gemini"), ["b", "a"])
```

- [ ] **Step 2: Run test and verify RED**

Run: `python -m unittest tests.test_storyboard_image_key_rotation -v`

Expected: FAIL because image generation does not use the central key store.

- [ ] **Step 3: Rotate per exhausted key, not globally per session**

Remove the global `_quota_exhausted` short-circuit. On a quota response, demote that key and continue immediately with the next key. Continue trying image models only when the failure is model-not-found or model-specific, not when the key is quota exhausted.

- [ ] **Step 4: Run image and provider tests**

Run: `python -m unittest tests.test_storyboard_image_key_rotation tests.test_provider_keys -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/storyboard_image.py tests/test_storyboard_image_key_rotation.py
git commit -m "feat: rotate Gemini image keys"
```

### Task 6: Settings API and multi-provider UI

**Files:**
- Modify: `backend/settings.py`
- Modify: `backend/routers/settings.py`
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Create: `tests/test_provider_settings.py`

**Interfaces:**
- Consumes: provider field mapping from Task 1
- Produces settings fields: `openai_api_keys`, `deepseek_api_keys`, `groq_api_keys`, corresponding model fields, and `text_provider_order`
- Produces endpoint behavior: existing `POST /api/settings` normalizes all provider key lists

- [ ] **Step 1: Write failing settings normalization tests**

```python
def test_settings_save_normalizes_all_provider_key_lists(self):
    payload = SettingsUpdateRequest(
        openai_api_keys="oa1\noa2\noa1",
        deepseek_api_keys=["ds1", ""],
        groq_api_keys="g1,g2",
        text_provider_order=["gemini", "openai", "deepseek", "groq", "web2api"],
    )
    data = normalize_settings_update(payload)
    self.assertEqual(data["openai_api_keys"], ["oa1", "oa2"])
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_provider_settings -v`

Expected: FAIL because the request fields and normalization helper are absent.

- [ ] **Step 3: Add backend defaults, request fields, normalization, and provider-aware key tests**

Default models:

```python
"openai_model": "gpt-4.1-mini",
"deepseek_model": "deepseek-chat",
"groq_model": "llama-3.3-70b-versatile",
"text_provider_order": ["gemini", "openai", "deepseek", "groq", "web2api"],
```

Extend `/test_gemini` into `/test_ai_keys` while retaining `/test_gemini` as a backward-compatible alias. Return `valid`, `quota_limited`, `invalid`, or `unreachable` per key.

- [ ] **Step 4: Add provider inputs and order control to the existing Settings screen**

Use one multiline textarea and model input per provider. Update the existing load/save handlers in `frontend/app.js`; never render full keys outside password-style inputs.

- [ ] **Step 5: Run backend tests and JavaScript syntax check**

Run: `python -m unittest tests.test_provider_settings tests.test_provider_keys -v`

Expected: all PASS.

Run: `node --check frontend/app.js`

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/settings.py backend/routers/settings.py frontend/index.html frontend/app.js tests/test_provider_settings.py
git commit -m "feat: configure multiple AI providers"
```

### Task 7: Full regression verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-19-storyboard-first-and-multi-provider-design.md` only if implementation reveals a documented mismatch

**Interfaces:**
- Consumes: all prior tasks
- Produces: operator documentation and verified release state

- [ ] **Step 1: Document provider configuration and rotation behavior**

Document provider order, multiline keys, default models, quota rotation, safe log previews, and the fact that non-Gemini providers handle text only.

- [ ] **Step 2: Run complete automated verification**

Run: `python -m unittest discover -s tests -v`

Expected: all PASS.

Run: `python -m compileall -q backend engine`

Expected: exit 0.

Run: `node --check frontend/app.js && node --check engine/chrome-extension/background.js`

Expected: exit 0.

- [ ] **Step 3: Manually test provider failover with sacrificial test keys**

Configure one quota-limited Gemini key followed by a valid Gemini key, trigger auto-suggest, and verify the first key moves to the bottom and the second succeeds. Then disable valid Gemini keys, configure a valid secondary provider, and verify the same JSON workflow succeeds through that provider.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-08-19-storyboard-first-and-multi-provider-design.md
git commit -m "docs: explain AI provider failover"
```
