"""gallery-dl metadata. Direct images stay on the HTTPX engine.

The adapter lists files before it downloads them. A thumbnail URL is stored
on the original item and is not saved as a second file.
"""

from __future__ import annotations

import io
import os
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urljoin

from umd.extract.model import ExtractResult, MediaRecord
from umd.netpolicy import DnsError, ExtractError, PolicyError, public_resolution, require_public

_DIRECT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_SECRET = {"cookie", "cookies", "password", "authorization", "token", "api_key", "access_token"}
EXTRACTOR_ID = "gallery-dl"


def installed_version() -> str:
    import gallery_dl

    return str(gallery_dl.__version__)


def supported_site_count() -> int:
    import gallery_dl.extractor as extractor

    return len(extractor.modules)


def can_handle(url: str) -> bool:
    import gallery_dl.extractor as extractor

    try:
        return extractor.find(url) is not None
    except Exception:
        return False


def _disable_proxy() -> None:
    import gallery_dl.config as config

    config.set(("extractor",), "proxy-env", False)
    config.set(("extractor",), "proxy", None)


def extract_gallery(url: str) -> ExtractResult:
    if os.environ.get("UMD_IN_WORKER") != "1":
        require_public(url)
        from umd.extract.model import result_from_payload
        from umd.net.isolated import call

        return result_from_payload(call("gallery-extract", {"url": url}))
    import gallery_dl
    from gallery_dl.extractor.message import Message
    from gallery_dl.job import DataJob

    require_public(url)
    _disable_proxy()
    sink = io.StringIO()
    job = DataJob(url, file=sink)
    try:
        with public_resolution():
            job.run()
    except (PolicyError, DnsError):
        raise
    except Exception as exc:
        raise ExtractError(_public_error(exc)) from exc
    if job.exception is not None:
        raise ExtractError(_public_error(job.exception))
    records = records_from_messages(job.data, url, str(gallery_dl.__version__), url_message=Message.Url)
    return ExtractResult(url, EXTRACTOR_ID, records)


def records_from_messages(messages: list, page_url: str, version: str, *, url_message: int = 3) -> list[MediaRecord]:
    thumbs: set[str] = set()
    prepared: list[tuple[str, dict]] = []
    for message in messages:
        if not isinstance(message, tuple) or len(message) < 3 or message[0] != url_message:
            continue
        media_url = str(message[1] or "")
        meta = message[2] if isinstance(message[2], dict) else {}
        thumb = meta.get("thumbnail")
        if isinstance(thumb, str) and thumb.startswith(("http://", "https://")):
            absolute = urljoin(media_url, thumb)
            thumbs.add(absolute)
        prepared.append((media_url, meta))
    records: list[MediaRecord] = []
    seen: set[str] = set()
    for media_url, meta in prepared:
        if not media_url.startswith(("http://", "https://")):
            continue
        if media_url in thumbs or _flagged_thumbnail(meta):
            continue
        if media_url in seen:
            continue
        seen.add(media_url)
        records.append(_record(media_url, meta, page_url, version))
    return records


def _record(media_url: str, meta: dict, page_url: str, version: str) -> MediaRecord:
    suffix = PurePosixPath(urlsplit(media_url).path).suffix.lower()
    width = _int(meta.get("width"))
    height = _int(meta.get("height"))
    filename = str(meta.get("filename") or "").strip()
    title = str(meta.get("title") or filename or PurePosixPath(urlsplit(media_url).path).name or "image")
    thumb = meta.get("thumbnail") if isinstance(meta.get("thumbnail"), str) else ""
    extension = str(meta.get("extension") or suffix.lstrip("."))
    delivery = "http" if suffix in _DIRECT else "gallery-dl"
    filesize = _int(meta.get("filesize") or meta.get("size"))
    return MediaRecord(
        media_type="image" if delivery == "http" or suffix in _DIRECT else "file",
        extractor_id=EXTRACTOR_ID,
        extractor_version=version,
        source_page_url=page_url,
        media_reference=page_url,
        thumbnail_url=str(thumb or ""),
        original_url=media_url,
        title=title,
        width=width,
        height=height,
        duration=None,
        format=extension,
        filesize=filesize,
        classification="content",
        classification_reason="gallery-dl",
        selected=True,
        download_state="대기",
        delivery=delivery,
    )


def _flagged_thumbnail(meta: dict) -> bool:
    kind = str(meta.get("type") or meta.get("_type") or "").lower()
    if kind in {"thumbnail", "thumb"}:
        return True
    return meta.get("thumbnail") is True or meta.get("is_thumbnail") is True


def _int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _public_error(exc: BaseException) -> str:
    text = str(exc)
    for key in _SECRET:
        if key in text.lower():
            return "추출에 실패했습니다"
    return text[:300] or "추출에 실패했습니다"
