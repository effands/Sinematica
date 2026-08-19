# Storyboard-First Flow Pipeline and Multi-Provider Key Rotation

## Purpose

Restore the intended character-consistency pipeline and centralize text-AI failover. Every scene must be composed as a storyboard image before video generation. Text requests may fall back across Gemini, OpenAI, DeepSeek, Groq, and the existing local Web2API service.

## Flow Media Pipeline

### Required order

1. Generate one character sheet for every character and cache each image locally.
2. Resolve the characters participating in a scene.
3. Generate one cinematic storyboard image for the scene using those character sheets as visual references.
4. Cache the storyboard image locally.
5. Select the Chrome profile and Flow project that will render the video.
6. Upload the local storyboard image into that exact profile's Flow project.
7. Generate the video through I2V with the uploaded storyboard media ID as `startImage`.
8. Poll and download the completed video through the same Chrome profile.

Character sheets are inputs to storyboard composition. They must never be used as the video's opening frame. The generated storyboard is the video's sole start-image reference.

### Profile failover

Flow media IDs are scoped to a project. An ID created in one project must not be submitted from another profile/project.

For every candidate Chrome profile:

- use that profile's own project ID;
- upload the locally cached storyboard into that project;
- submit I2V and poll through that same profile;
- download through that same authenticated profile.

If the profile fails before accepting the render, the next profile receives a fresh upload of the same local storyboard. A failed download must not trigger a second render; download failures are retried separately against the profile that owns the completed media.

### Fallback behavior

- If Gemini cannot compose the storyboard, Google Flow may create it from the locally cached character sheets.
- Regardless of which service creates it, the final storyboard must be cached locally before video generation.
- If storyboard creation fails completely, mark the scene failed with a specific storyboard error. Do not silently fall back to character-sheet I2V or plain T2V because those paths break visual continuity.
- R2V multi-image is not part of the normal video path. It may be reintroduced only after its endpoint and project-scoping behavior are proven by tests.

## Text Provider Architecture

### Provider chain

Use one central text-generation service with this default order:

1. Gemini
2. OpenAI
3. DeepSeek
4. Groq
5. Local Web2API

The order is stored in settings and may be changed by the user. Gemini remains the only configured cloud provider used for image generation; Google Flow remains responsible for image/video generation where applicable.

### Provider adapters

Each adapter exposes one text contract:

- input prompt or message list;
- optional JSON-output requirement;
- selected model;
- response text;
- normalized error classification.

OpenAI, DeepSeek, and Groq use OpenAI-compatible chat-completions adapters with provider-specific base URLs and models. Gemini uses its native SDK/API. Existing callers such as auto-suggest, storyboard generation, scene regeneration, YouTube metadata, music-video planning, and policy rewriting call the central service instead of implementing their own key loops.

### API-key rotation

Each cloud provider accepts multiple ordered keys. On `429`, `RESOURCE_EXHAUSTED`, quota exhaustion, or provider-equivalent rate-limit errors:

1. move the failed key to the bottom of that provider's list;
2. persist the new list atomically;
3. stop trying other models with that exhausted key;
4. immediately try the next key;
5. after all keys for a provider fail with quota errors, move to the next provider.

Authentication errors such as invalid or revoked keys are skipped and reported but are not treated as temporary quota exhaustion. Network and server errors receive a small bounded retry without changing key order.

Concurrent requests use a settings lock so key reordering cannot lose updates. Logs identify providers and key indices but never print full keys.

## Settings and UI

Settings store:

- ordered Gemini keys and model;
- ordered OpenAI keys and model;
- ordered DeepSeek keys and model;
- ordered Groq keys and model;
- ordered provider fallback chain;
- existing Web2API configuration.

The Settings screen provides one multiline key input per provider and a provider-order control. Saving removes empty entries and duplicates while preserving order. The first key remains mirrored to any legacy single-key field needed for backward compatibility.

API-key test results must distinguish valid, quota-limited, invalid, and unreachable keys. Testing keys must not consume or reorder production keys unless the test receives a real quota response.

## Error Handling and Observability

Logs must clearly distinguish:

- storyboard creation;
- storyboard upload and owning Flow project/profile;
- I2V submission;
- render polling;
- MP4 download;
- provider/key rotation.

Scene records retain the storyboard URL, rendering profile, Flow project ID, generation mode, and final media ID. User-facing errors identify the failing stage instead of labeling every error as a profile quota problem.

## Testing

Tests are written before implementation and cover:

- a quota-limited key moves to the bottom and the order persists;
- the next key is used immediately;
- exhausting one provider advances to the next provider;
- non-quota errors do not reorder keys;
- concurrent rotations preserve every key exactly once;
- storyboard media, not character-sheet media, is passed to I2V;
- a profile switch uploads the local storyboard into the new project before I2V;
- download failure does not submit another render;
- complete storyboard failure does not silently use T2V;
- legacy Gemini-only settings continue working.

Verification includes the Python test suite, Python compilation, JavaScript syntax checks, and a manual smoke run with two Chrome profiles to confirm project-scoped media handling.
