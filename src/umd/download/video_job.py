"""Download one probed video with yt-dlp.

The page URL is extracted again at download time so an expired media URL is
not reused. Progress uses byte counts yt-dlp reports. An estimated size does
not become a percentage.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from umd.netpolicy import DnsError, ExtractError, PolicyError, public_resolution, require_public

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class TransferStop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def download_video(
    page_url: str,
    directory: Path,
    *,
    format_id: str,
    should_stop,
    on_progress,
) -> tuple[Path, int]:
    if os.environ.get("UMD_IN_WORKER") != "1":
        return _download_via_child(page_url, directory, format_id, should_stop, on_progress)
    return _download_inline(page_url, directory, format_id, should_stop, on_progress)


def _download_via_child(page_url, directory, format_id, should_stop, on_progress) -> tuple[Path, int]:
    import json
    import threading

    from umd.net.isolated import IsolatedStop, call

    require_public(page_url)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    flag = directory / f".umd-video-{os.urandom(4).hex()}"
    progress = directory / f".umd-progress-{os.urandom(4).hex()}"
    stop = threading.Event()

    def watch() -> None:
        last = ""
        while not stop.wait(0.1):
            reason = should_stop() or ""
            if reason:
                flag.write_text(reason, encoding="ascii")
            if not progress.is_file():
                continue
            text = progress.read_text(encoding="utf-8")
            if text == last or not text:
                continue
            last = text
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            on_progress(int(data.get("downloaded") or 0), int(data.get("total") or -1))

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        result = call(
            "video-download",
            {
                "url": page_url,
                "directory": str(directory),
                "formatId": format_id,
                "cancelFlag": str(flag),
                "progressPath": str(progress),
            },
            timeout=600,
        )
    except IsolatedStop as exc:
        raise TransferStop(exc.reason) from exc
    finally:
        stop.set()
        thread.join(timeout=1)
        progress.unlink(missing_ok=True)
        flag.unlink(missing_ok=True)
    path = Path(str(result.get("path") or ""))
    return path, int(result.get("size") or 0)


def _download_inline(page_url, directory, format_id, should_stop, on_progress) -> tuple[Path, int]:
    require_public(page_url)
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    directory.mkdir(parents=True, exist_ok=True)
    base = _options()
    try:
        with public_resolution():
            with YoutubeDL(base) as probe:
                info = probe.extract_info(page_url, download=False)
    except (PolicyError, DnsError):
        raise
    except DownloadError as exc:
        raise ExtractError(str(exc)[:300]) from exc
    if not isinstance(info, dict):
        raise ExtractError("영상 정보를 읽지 못했습니다")
    ext = str(info.get("ext") or "mp4")
    stem = _SAFE.sub("-", str(info.get("id") or "video")).strip("-") or "video"
    filename = _unique(directory, f"{stem}.{ext}")
    options = _options()
    options["format"] = format_id or "b"
    options["outtmpl"] = str(directory / filename)
    options["progress_hooks"] = [_hook(should_stop, on_progress)]
    try:
        with public_resolution():
            with YoutubeDL(options) as ydl:
                finished = ydl.extract_info(page_url, download=True)
                path = _finished_path(ydl, finished if isinstance(finished, dict) else info, directory / filename)
    except TransferStop:
        raise
    except (PolicyError, DnsError):
        raise
    except DownloadError as exc:
        raise ExtractError(str(exc)[:300]) from exc
    if not path.is_file():
        raise ExtractError("영상 파일을 저장하지 못했습니다")
    return path, path.stat().st_size


def _options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "proxy": "",
        "nocheckcertificate": False,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "overwrites": False,
        "continuedl": True,
        "nopart": False,
    }


def _hook(should_stop, on_progress):
    def receive(status: dict) -> None:
        reason = should_stop() or ""
        if reason:
            raise TransferStop(reason)
        if status.get("status") != "downloading":
            return
        downloaded = int(status.get("downloaded_bytes") or 0)
        total = status.get("total_bytes")
        known = int(total) if isinstance(total, int) and total > 0 else -1
        on_progress(downloaded, known)

    return receive


def _finished_path(ydl, info: dict, fallback: Path) -> Path:
    downloads = info.get("requested_downloads") or []
    if downloads and isinstance(downloads[-1], dict) and downloads[-1].get("filepath"):
        return Path(str(downloads[-1]["filepath"]))
    try:
        prepared = Path(ydl.prepare_filename(info))
    except Exception:
        prepared = fallback
    return prepared if prepared.is_file() else fallback


def _unique(directory: Path, filename: str) -> str:
    candidate = directory / filename
    if not candidate.exists():
        return filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 2
    while (directory / f"{stem}-{index}{suffix}").exists():
        index += 1
    return f"{stem}-{index}{suffix}"
