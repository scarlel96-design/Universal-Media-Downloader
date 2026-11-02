"""yt-dlp metadata. Signed media URLs are not stored.

The probe uses the official API with download disabled. DRM formats are
dropped. YouTube login and personal playlists are not enabled.
"""

from __future__ import annotations

import os
import re
import threading

from umd.extract.model import ExtractResult, MediaRecord, display_unknown
from umd.netpolicy import DnsError, ExtractError, PolicyError, public_resolution, require_public

EXTRACTOR_ID = "yt-dlp"
_SECRET = re.compile(r"(://)[^/\s@:]+:[^/\s@]+@")
_lock = threading.Lock()
_ydl = None


def installed_version() -> str:
    from yt_dlp.version import __version__

    return str(__version__)


def supported_site_count() -> int:
    return len(_client()._ies)


def can_handle(url: str) -> bool:
    ydl = _client()
    for name, extractor in ydl._ies.items():
        if name == "Generic":
            continue
        try:
            if extractor.suitable(url):
                return True
        except Exception:
            continue
    return False


def extract_video(url: str) -> ExtractResult:
    if os.environ.get("UMD_IN_WORKER") != "1":
        require_public(url)
        from umd.extract.model import result_from_payload
        from umd.net.isolated import call

        return result_from_payload(call("video-extract", {"url": url}))
    from yt_dlp.utils import DownloadError

    require_public(url)
    try:
        with public_resolution():
            info = _client().extract_info(url, download=False)
    except DownloadError as exc:
        raise ExtractError(redact(str(exc))) from exc
    except (PolicyError, DnsError):
        raise
    except Exception as exc:
        raise ExtractError(redact(str(exc))) from exc
    if not isinstance(info, dict):
        raise ExtractError("영상 정보를 읽지 못했습니다")
    if info.get("_type") == "playlist" or info.get("entries"):
        raise ExtractError("재생목록은 이 단계에서 받지 않습니다")
    record = record_from_info(info, page_url=url, version=installed_version())
    if record.error and not record.formats:
        raise ExtractError(record.error)
    return ExtractResult(url, EXTRACTOR_ID, [record], error=record.error)


def record_from_info(info: dict, *, page_url: str, version: str) -> MediaRecord:
    formats = []
    for fmt in info.get("formats") or []:
        if not isinstance(fmt, dict) or not _usable(fmt):
            continue
        formats.append(_format_choice(fmt))
    if not formats and (info.get("is_drm") or info.get("_has_drm")):
        error = "DRM 미디어는 지원하지 않습니다"
    elif not formats:
        error = "받을 수 있는 영상 형식이 없습니다" if info.get("formats") else ""
    else:
        error = ""
    chosen = _default_format(formats)
    subtitles = _subtitle_text(info.get("subtitles") or {})
    duration = info.get("duration")
    duration_value = float(duration) if isinstance(duration, (int, float)) and duration > 0 else None
    width = _positive(info.get("width"))
    height = _positive(info.get("height"))
    if chosen:
        width = width or chosen.get("width")
        height = height or chosen.get("height")
    filesize = chosen.get("filesize") if chosen else _positive(info.get("filesize"))
    note = chosen.get("filesizeNote") if chosen else ""
    title = str(info.get("title") or "").strip() or display_unknown(None)
    reference = str(info.get("webpage_url") or page_url)
    video_id = str(info.get("id") or "")
    if video_id:
        reference = f"{reference}#{video_id}"
    thumb = info.get("thumbnail") if isinstance(info.get("thumbnail"), str) else ""
    return MediaRecord(
        media_type="video",
        extractor_id=EXTRACTOR_ID,
        extractor_version=version,
        source_page_url=page_url,
        media_reference=reference.split("#", 1)[0] or page_url,
        thumbnail_url=thumb,
        original_url=page_url,
        title=title,
        width=width,
        height=height,
        duration=duration_value,
        format=str(chosen.get("label") if chosen else info.get("ext") or ""),
        filesize=filesize,
        classification="content",
        classification_reason=subtitles or "yt-dlp",
        selected=True,
        download_state="대기",
        delivery="yt-dlp",
        format_id=str(chosen.get("id") if chosen else ""),
        formats=formats,
        subtitles=subtitles,
        filesize_note=str(note or ""),
        error=error,
    )


def redact(text: str) -> str:
    from umd.secrets import scrub_text

    return scrub_text(_SECRET.sub(r"\1", text))[:300]


def _client():
    global _ydl
    with _lock:
        if _ydl is None:
            from yt_dlp import YoutubeDL

            _ydl = YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "skip_download": True,
                    "socket_timeout": 20,
                    "proxy": "",
                    "nocheckcertificate": False,
                }
            )
        return _ydl


def _usable(fmt: dict) -> bool:
    if fmt.get("has_drm") or fmt.get("drm"):
        return False
    video = str(fmt.get("vcodec") or "none")
    audio = str(fmt.get("acodec") or "none")
    if video == "none" and audio == "none":
        return False
    protocol = str(fmt.get("protocol") or "")
    if "mhtml" in protocol or protocol == "http_dash_segments" and video == "none":
        return video != "none" or audio != "none"
    return True


def _format_choice(fmt: dict) -> dict:
    height = _positive(fmt.get("height"))
    width = _positive(fmt.get("width"))
    ext = str(fmt.get("ext") or "")
    video = str(fmt.get("vcodec") or "none")
    audio = str(fmt.get("acodec") or "none")
    filesize = _positive(fmt.get("filesize"))
    approx = _positive(fmt.get("filesize_approx"))
    note = f"예상 {_bytes(approx)}" if filesize is None and approx else ""
    pieces = []
    if height:
        pieces.append(f"{height}p")
    elif fmt.get("format_note"):
        pieces.append(str(fmt.get("format_note")))
    if ext:
        pieces.append(ext)
    if video != "none" and audio != "none":
        pieces.append("영상+음성")
    elif video != "none":
        pieces.append("영상")
    elif audio != "none":
        pieces.append("음성")
    protocol = str(fmt.get("protocol") or "")
    if protocol and protocol not in {"http", "https"}:
        pieces.append(protocol)
    label = " ".join(pieces) or str(fmt.get("format_id") or "형식")
    return {
        "id": str(fmt.get("format_id") or label),
        "label": label,
        "width": width,
        "height": height,
        "ext": ext,
        "vcodec": video,
        "acodec": audio,
        "filesize": filesize,
        "filesizeApprox": approx,
        "filesizeNote": note,
        "protocol": protocol,
    }


def _default_format(formats: list[dict]) -> dict | None:
    if not formats:
        return None

    def rank(fmt: dict) -> tuple:
        both = fmt.get("vcodec") not in {None, "none"} and fmt.get("acodec") not in {None, "none"}
        protocol = str(fmt.get("protocol") or "")
        progressive = "m3u8" not in protocol and "dash" not in protocol and protocol in {"", "http", "https"}
        return (
            1 if both else 0,
            1 if progressive else 0,
            1 if fmt.get("filesize") else 0,
            int(fmt.get("height") or 0),
        )

    return max(formats, key=rank)


def _subtitle_text(subtitles: dict) -> str:
    if not isinstance(subtitles, dict) or not subtitles:
        return ""
    names = [str(name) for name in subtitles if name]
    if not names:
        return ""
    return "자막 " + ", ".join(sorted(names)[:8])


def _positive(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    return number if number > 0 else None


def _bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
