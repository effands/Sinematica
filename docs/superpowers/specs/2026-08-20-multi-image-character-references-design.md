# Multi-Image References per Character

## Goal

Allow each Casting Karakter entry to own several reference images so its generated anchor character
sheet follows a recognizable existing design (for example, the correct face, costume, silhouette,
and accessories of a Boboiboy-like character). References must never leak from one character to
another.

## User Experience

- The Add Actor modal accepts between one and four images in a single selection.
- The first image is the primary thumbnail. The remaining images may show another angle, costume,
  body shape, or a distinctive feature.
- Before saving, the modal shows removable thumbnails and a `1/4` through `4/4` counter.
- The Casting Karakter card shows the primary image plus small secondary thumbnails and the number
  of saved references.
- Selected Casting Karakter entries continue to work in both AI Storyboard and Music Video.
- Existing actors containing only `image_path` and `image_url` remain valid and appear as actors with
  one reference.

## Actor Data Model and API

Actor records gain an `images` array:

```json
{
  "id": "actor-id",
  "name": "Boboiboy",
  "description": "Distinct visual description",
  "seed": 123456,
  "images": [
    {"path": "...", "url": "/storage/actors/...", "primary": true},
    {"path": "...", "url": "/storage/actors/...", "primary": false}
  ],
  "image_path": "primary path for backward compatibility",
  "image_url": "primary URL for backward compatibility"
}
```

`POST /api/actors` changes from one required `image_file` to a list named `image_files`. During a
transition it also accepts the old singular field. The backend accepts JPEG, PNG, or WebP, at most
four files and 10 MiB per file. It rejects empty, unsupported, or excessive input before updating
`actors.json`. If saving any image fails, already-written files from that request are removed.

Deleting an actor removes every path in `images`, plus legacy `image_path` when it is not already in
that list. It never removes references merely because a Gallery job was deleted.

## Storyboard Association

Selecting actors adds their name, seed, description, actor ID, and reference paths to storyboard
generation. The generated character registry is instructed to preserve `source_actor_id`. The
router also attaches an internal `character_references` mapping to the resulting storyboard, keyed
by actor ID, so image ownership does not depend only on an AI-generated name.

For compatibility when a provider omits `source_actor_id`, association falls back to a normalized
exact character name. It must not use fuzzy matching because a wrong reference is worse than no
reference. Free-form global storyboard images remain theme/composition references and do not become
character-owned references.

## Character-Sheet Generation

At job start, the executor resolves reference paths separately for each storyboard character. It
uploads only that character's references to the active Flow project, then calls the existing
`generate_character_image(..., reference_media_ids=[...])` route.

The character-sheet prompt states that the attached images are the source of truth for face,
costume, silhouette, palette, and accessories. Text description fills missing details but cannot
override visible reference identity. References from another actor are never included.

Success is strict:

- If a character has registered references, a generated sheet counts as valid only when Flow reports
  that references were applied.
- A transient upload or reference-generation failure retries through the existing retry mechanism.
- If mandatory seed generation still cannot create that character's sheet, the existing seed guard
  stops the job before scene rendering.
- A character without registered references continues through the current text-only seed path.

## Cleanup and Persistence

Actor reference files are persistent Casting Karakter assets. The Gallery cleanup system must not
claim or delete them. Storyboard/job records store their paths as references, not disposable upload
ownership. Explicit actor deletion is the only normal deletion path.

## Testing

Automated tests cover:

- legacy single-image actor normalization;
- one-to-four image validation and rejection of unsupported or excessive input;
- deletion of all files belonging to one actor;
- exact actor-ID/name mapping without cross-character leakage;
- executor passing only the correct character's media IDs to Flow;
- preservation of the text-only path for old/no-reference characters;
- frontend multi-file field, preview container, count, and payload field name;
- existing seed guard, Gallery cleanup, audio, continuity, and Flow readiness regression suites.

## Non-Goals

- Automatic web search for copyrighted character images;
- mixing references from different characters into one sheet;
- face recognition or fuzzy visual matching;
- unlimited reference storage;
- changing how scene videos use the completed anchor sheets.
