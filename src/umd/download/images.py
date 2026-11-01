"""Save one image to a directory.

Bytes are written to a temporary ``.part`` file in the destination directory.
The final name is created with ``os.replace`` only after the status, the
length, and the image signature have all been checked. A cancelled or failed
transfer deletes the partial file and does not report completion.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, url2pathname, urlopen
from uuid import uuid4

from umd.netpolicy import is_allowed_url

_CHUNK = 64 * 1024
_EXT = {"png": ".png", "jpeg": ".jpg", "gif": ".gif", "webp": ".webp"}


@dataclass(frozen=True)
class DownloadResult:
    status: str
    path: str
    size: int
    error: str


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _filename(url: str, kind: str) -> str:
    raw_name = unquote(urlsplit(url).path).rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw_name).strip(" .") or "image"
    ext = _EXT[kind]
    suffix = Path(name).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
        name = f"{Path(name).stem}.jpg"
    if suffix != ext:
        name = f"{Path(name).stem}{ext}"
    return name


def _allocate(directory: Path, filename: str, reserved: set[str]) -> Path:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = filename
    number = 2
    while candidate in reserved or (directory / candidate).exists():
        candidate = f"{stem}-{number}{suffix}"
        number += 1
    reserved.add(candidate)
    return directory / candidate


def _fail(message: str) -> DownloadResult:
    return DownloadResult("실패", "", 0, message)


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def download_one(
    url: str,
    directory: str | Path,
    *,
    cancel: threading.Event | None = None,
    reserved: set[str] | None = None,
    timeout: float = 30,
) -> DownloadResult:
    folder = Path(directory)
    if not folder.is_dir():
        return _fail("저장 경로가 올바르지 않습니다")
    if not is_allowed_url(url):
        return _fail("허용되지 않은 주소입니다")
    names = reserved if reserved is not None else set()
    last = _fail("다운로드에 실패했습니다")
    for _ in range(4):
        if cancel is not None and cancel.is_set():
            return DownloadResult("취소", "", 0, "사용자가 취소했습니다")
        try:
            return _transfer(url, folder, names, cancel, timeout)
        except ConnectionResetError as exc:
            last = _fail(str(exc))
    return last


def _transfer(
    url: str,
    folder: Path,
    names: set[str],
    cancel: threading.Event | None,
    timeout: float,
) -> DownloadResult:
    part = folder / f".umd-{uuid4().hex}.part"
    try:
        if urlsplit(url).scheme == "file":
            return _save_bytes(Path(url2pathname(urlsplit(url).path)).read_bytes(), url, folder, part, names, cancel)
        request = Request(url, headers={"User-Agent": "UniversalMediaDownloader/0.1"})
        with urlopen(request, timeout=timeout) as response:
            final = response.geturl()
            if not is_allowed_url(final):
                return _fail("리다이렉트 주소가 허용되지 않습니다")
            status = int(getattr(response, "status", 0) or response.getcode() or 0)
            if status != 200:
                return _fail(f"HTTP {status}")
            declared = response.headers.get("Content-Length")
            expected = int(declared) if declared and declared.isdigit() else None
            written = 0
            with part.open("wb") as handle:
                while True:
                    if cancel is not None and cancel.is_set():
                        handle.close()
                        _discard(part)
                        return DownloadResult("취소", "", 0, "사용자가 취소했습니다")
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
            if cancel is not None and cancel.is_set():
                _discard(part)
                return DownloadResult("취소", "", 0, "사용자가 취소했습니다")
            if expected is not None and written != expected:
                _discard(part)
                return _fail("응답이 잘렸습니다")
            return _commit(part, url, folder, names, written)
    except HTTPError as exc:
        _discard(part)
        return _fail(f"HTTP {exc.code}")
    except ConnectionResetError:
        _discard(part)
        raise
    except Exception as exc:  # noqa: BLE001 — surfaced to the job row
        _discard(part)
        if getattr(exc, "partial", None) is not None:
            return _fail("응답이 잘렸습니다")
        return _fail(str(exc))


def _save_bytes(
    data: bytes,
    url: str,
    folder: Path,
    part: Path,
    names: set[str],
    cancel: threading.Event | None,
) -> DownloadResult:
    if cancel is not None and cancel.is_set():
        return DownloadResult("취소", "", 0, "사용자가 취소했습니다")
    part.write_bytes(data)
    return _commit(part, url, folder, names, len(data))


def _commit(part: Path, url: str, folder: Path, names: set[str], written: int) -> DownloadResult:
    if written <= 0 or not part.is_file():
        _discard(part)
        return _fail("빈 응답")
    with part.open("rb") as handle:
        kind = sniff_image(handle.read(16))
    if kind is None:
        _discard(part)
        return _fail("허용되지 않은 이미지 형식")
    target = _allocate(folder, _filename(url, kind), names)
    os.replace(part, target)
    if not target.is_file() or target.stat().st_size != written:
        _discard(target)
        return _fail("저장한 파일 크기가 응답과 다릅니다")
    return DownloadResult("완료", str(target), written, "")
