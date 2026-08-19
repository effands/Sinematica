"""Safe filesystem cleanup for Gallery job deletion."""

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping


@dataclass
class CleanupResult:
    job_directory_deleted: bool = False
    deleted_uploads: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def job_source_files(theme_image_path: str | None, storyboard: Mapping[str, Any]) -> list[str]:
    """Return stable, de-duplicated local source paths owned by a Gallery job."""
    candidates = (
        theme_image_path,
        storyboard.get("_theme_image_path"),
        storyboard.get("music_track_path"),
    )
    return list(dict.fromkeys(
        path for path in candidates if isinstance(path, str) and path.strip()
    ))


def _source_files(job: Mapping[str, Any] | None) -> set[Path]:
    paths: set[Path] = set()
    for value in (job or {}).get("source_files", []):
        if isinstance(value, str) and value.strip():
            paths.add(Path(value).resolve())
    return paths


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def cleanup_job_files(
    job_id: str,
    job: Mapping[str, Any] | None,
    remaining_jobs: Iterable[Mapping[str, Any]],
    *,
    jobs_dir: Path,
    uploads_dir: Path,
) -> CleanupResult:
    """Delete one job directory and uploads that no remaining job references."""
    result = CleanupResult()
    jobs_root = Path(jobs_dir).resolve()
    uploads_root = Path(uploads_dir).resolve()
    job_directory = (jobs_root / job_id).resolve()

    if job_directory.parent == jobs_root and job_directory.exists():
        try:
            shutil.rmtree(job_directory)
            result.job_directory_deleted = True
        except OSError as ex:
            result.errors.append(f"Gagal menghapus {job_directory}: {ex}")

    referenced_elsewhere: set[Path] = set()
    for other_job in remaining_jobs:
        referenced_elsewhere.update(_source_files(other_job))

    for source in sorted(_source_files(job), key=str):
        if not _is_within(source, uploads_root) or source in referenced_elsewhere:
            continue
        if source.exists() and source.is_file():
            try:
                source.unlink()
                result.deleted_uploads.append(str(source))
            except OSError as ex:
                result.errors.append(f"Gagal menghapus {source}: {ex}")

    return result
