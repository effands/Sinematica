"""Durable film-owned sheets. Flow IDs are transport handles, never the master asset."""

import asyncio
from functools import wraps
import hashlib
from io import BytesIO
import json
from pathlib import Path
import uuid
import weakref

from PIL import Image


class AssetRecoveryRequired(RuntimeError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ensure_film_asset_id(storyboard):
    # Old storyboards have no UUID. A deterministic compatibility ID keeps repeated
    # API submissions of that same film reusable; new UI storyboards use UUIDs.
    if not storyboard.get('film_asset_id'):
        storyboard['film_asset_id'] = 'legacy-' + _digest({
            k: storyboard.get(k) for k in ('film_title', 'premise', 'character_seed', 'source_script')
        })[:32]
    return str(storyboard['film_asset_id'])


def character_asset_key(character, visual_style, reference_paths=()):
    references = []
    for path in reference_paths:
        file = Path(path)
        if not file.is_file():
            raise AssetRecoveryRequired(f'Referensi karakter tidak ditemukan: {file.name}')
        references.append(hashlib.sha256(file.read_bytes()).hexdigest())
    return _digest({
        'character': {k: character.get(k) for k in (
            'id', 'name', 'source_actor_id', 'seed', 'description', 'visual_signature', 'sheet_revision',
        )},
        'style': visual_style, 'references': references,
    })


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class FilmAssetCache:
    def __init__(self, root, film_id):
        # Never turn a client-provided identifier into a filesystem path.
        self.directory = Path(root) / _digest(str(film_id))

    def paths(self, key):
        directory = self.directory / 'characters' / _digest(str(key))
        return directory / 'sheet.png', directory / 'asset.json'

    def state(self, key):
        _, manifest = self.paths(key)
        if not manifest.exists():
            return None
        try:
            return json.loads(manifest.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            raise AssetRecoveryRequired('Manifest sheet rusak; pulihkan cache, jangan generate ulang.') from error

    def record(self, key, **state):
        _, manifest = self.paths(key)
        _atomic_write(manifest, json.dumps(state, ensure_ascii=False).encode())

    def ready_path(self, key):
        state = self.state(key)
        path, _ = self.paths(key)
        if state and state.get('status') == 'ready':
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != state.get('sha256'):
                raise AssetRecoveryRequired('Master sheet hilang/rusak; pulihkan file cache sebelum Resume.')
            return str(path)
        return None

    def save(self, key, data, **metadata):
        # Decode and re-encode once: reject HTML/error bodies and incomplete images.
        try:
            with Image.open(BytesIO(data)) as image:
                image.load()
                if min(image.size) < 16:
                    raise ValueError('image too small')
                output = BytesIO()
                image.convert('RGB').save(output, format='PNG')
                payload = output.getvalue()
        except Exception as error:
            raise AssetRecoveryRequired('Unduhan sheet bukan gambar valid; ulangi unduhan, bukan generasi.') from error
        path, _ = self.paths(key)
        _atomic_write(path, payload)
        self.record(key, **{**metadata, 'status': 'ready', 'sha256': hashlib.sha256(payload).hexdigest()})
        return str(path)


_film_locks = weakref.WeakKeyDictionary()


def serialize_film_execution(function):
    """One job per film at a time prevents duplicate paid sheet generation in-process."""
    @wraps(function)
    async def run(job_id=None, storyboard=None, *args, **kwargs):
        # execute_storyboard_job is called with keywords by the API and Resume path.
        if job_id is None:
            job_id = kwargs.pop('job_id')
        if storyboard is None:
            storyboard = kwargs.pop('storyboard')
        film_id = ensure_film_asset_id(storyboard)
        locks = _film_locks.setdefault(asyncio.get_running_loop(), {})
        lock = locks.setdefault(film_id, asyncio.Lock())
        async with lock:
            return await function(job_id, storyboard, *args, **kwargs)
    return run
