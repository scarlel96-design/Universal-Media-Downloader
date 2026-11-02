"""Save only the gallery files the user selected.

gallery-dl's DownloadJob would otherwise write every file on the page and the
worker kept only the first path. Selection is applied before any file is
written. A child process owns the global DNS guard so the parent can keep
using normal name resolution at the same time.
"""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from umd.netpolicy import public_resolution, require_public


@dataclass
class GalleryFile:
    url: str
    path: str
    size: int
    sha256: str
    state: str
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "state": self.state,
            "error": self.error,
        }


@dataclass
class GalleryBatch:
    files: list[GalleryFile] = field(default_factory=list)
    cancelled: bool = False

    def as_dict(self) -> dict:
        return {
            "files": [item.as_dict() for item in self.files],
            "cancelled": self.cancelled,
        }


def download_selected(
    page_url: str,
    directory: Path,
    only_urls: set[str],
    *,
    should_stop=None,
    isolated: bool | None = None,
) -> GalleryBatch:
    """Download ``only_urls`` from one gallery page and place each file once."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    allowed = {url for url in only_urls if url}
    if not allowed:
        return GalleryBatch()
    if _use_child(isolated):
        from umd.net.isolated import call

        flag = directory / ".umd-cancel"
        stop = threading.Event()

        def watch() -> None:
            while not stop.wait(0.1):
                if should_stop and should_stop():
                    flag.write_text("1", encoding="ascii")
                    return

        thread = threading.Thread(target=watch, daemon=True)
        thread.start()
        try:
            payload = call(
                "gallery-download",
                {
                    "url": page_url,
                    "directory": str(directory),
                    "only": sorted(allowed),
                    "cancelFlag": str(flag),
                },
            )
        finally:
            stop.set()
            thread.join(timeout=1)
        batch = GalleryBatch(cancelled=bool(payload.get("cancelled")))
        for item in payload.get("files") or []:
            batch.files.append(
                GalleryFile(
                    url=str(item.get("url") or ""),
                    path=str(item.get("path") or ""),
                    size=int(item.get("size") or 0),
                    sha256=str(item.get("sha256") or ""),
                    state=str(item.get("state") or "failed"),
                    error=str(item.get("error") or ""),
                )
            )
        return batch
    return _download_inline(page_url, directory, allowed, should_stop)


def place_file(directory: Path, source: Path, preferred: str) -> tuple[Path, str, str]:
    """Move ``source`` into ``directory`` without mixing two different files.

    A matching digest is an already stored file. A different digest keeps the
    existing bytes and stores the new file under a numbered name.
    """

    directory.mkdir(parents=True, exist_ok=True)
    digest = _digest(source)
    target = directory / _safe_name(preferred)
    if target.exists():
        if _digest(target) == digest:
            source.unlink(missing_ok=True)
            return target, "existing", digest
        target = _numbered(directory, target.name)
    source.replace(target)
    return target, "new", digest


def _download_inline(
    page_url: str,
    directory: Path,
    only_urls: set[str],
    should_stop,
) -> GalleryBatch:
    import gallery_dl.config as config
    from gallery_dl.job import DownloadJob

    require_public(page_url)
    staging = directory / f".umd-gallery-{os.urandom(4).hex()}"
    staging.mkdir(parents=True, exist_ok=True)
    config.set(("extractor",), "proxy-env", False)
    config.set(("extractor",), "proxy", None)
    config.set((), "base-directory", str(staging))
    batch = GalleryBatch()
    job = SelectiveDownloadJob(page_url, only_urls, should_stop, batch, staging)
    try:
        with public_resolution():
            job.run()
    finally:
        _discard_staging(staging, batch)
    return batch


class SelectiveDownloadJob:
    """Thin wrapper so tests can call ``handle_url`` without a live extractor.

    The real download still goes through gallery-dl's ``DownloadJob``.
    """

    def __init__(self, url: str, only_urls: set[str], should_stop, batch: GalleryBatch, staging: Path) -> None:
        from gallery_dl.job import DownloadJob

        self._job = DownloadJob(url)
        self.only_urls = set(only_urls)
        self.should_stop = should_stop
        self.batch = batch
        self.staging = staging
        self.rejected: list[str] = []
        self._job.handle_url = self.handle_url  # type: ignore[method-assign]

    def run(self) -> None:
        self._job.run()

    def handle_url(self, url, kwdict) -> None:
        from gallery_dl.job import DownloadJob

        if url not in self.only_urls:
            self.rejected.append(url)
            return
        if self.should_stop and self.should_stop():
            self.batch.cancelled = True
            from gallery_dl import exception

            raise exception.StopExtraction()
        before = _files(self.staging)
        try:
            DownloadJob.handle_url(self._job, url, kwdict)
        except Exception as exc:
            from gallery_dl import exception

            if isinstance(exc, exception.StopExtraction):
                self.batch.cancelled = True
                raise
            self.batch.files.append(GalleryFile(url, "", 0, "", "failed", str(exc)[:300]))
            return
        created = [path for path in _files(self.staging) if path not in before]
        if not created:
            existing = _existing_path(self._job)
            if existing is not None and existing.is_file():
                digest = _digest(existing)
                self.batch.files.append(
                    GalleryFile(url, str(existing), existing.stat().st_size, digest, "existing")
                )
            else:
                self.batch.files.append(GalleryFile(url, "", 0, "", "failed", "저장한 파일이 없습니다"))
            return
        source = created[-1]
        placed, state, digest = place_file(self.staging.parent, source, source.name)
        self.batch.files.append(
            GalleryFile(url, str(placed), placed.stat().st_size, digest, state)
        )


def _use_child(isolated: bool | None) -> bool:
    if os.environ.get("UMD_IN_WORKER") == "1":
        return False
    if isolated is None:
        return True
    return isolated


def _files(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {path.resolve() for path in directory.rglob("*") if path.is_file()}


def _existing_path(job) -> Path | None:
    pathfmt = getattr(job, "pathfmt", None)
    raw = getattr(pathfmt, "path", "") if pathfmt is not None else ""
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_file() else None


def _discard_staging(staging: Path, batch: GalleryBatch) -> None:
    kept = {Path(item.path).resolve() for item in batch.files if item.path}
    if staging.exists():
        for path in staging.rglob("*"):
            if path.is_file() and path.resolve() not in kept:
                path.unlink(missing_ok=True)
        for path in sorted(staging.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        if staging.exists():
            staging.rmdir()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in name).strip(" .")
    return cleaned or "media.bin"


def _numbered(directory: Path, name: str) -> Path:
    stem = Path(name).stem
    suffix = Path(name).suffix
    index = 2
    while (directory / f"{stem}-{index}{suffix}").exists():
        index += 1
    return directory / f"{stem}-{index}{suffix}"
