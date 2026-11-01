"""Shared media record for HTML, gallery-dl, and yt-dlp results."""

from __future__ import annotations

from dataclasses import dataclass, field


def display_unknown(value: object, *, suffix: str = "") -> str:
    """Show missing metadata as 미확인. Zero and empty text are missing too."""

    if value is None or value == "" or value == 0:
        return "미확인"
    return f"{value}{suffix}"


@dataclass
class MediaRecord:
    media_type: str
    extractor_id: str
    extractor_version: str
    source_page_url: str
    media_reference: str
    thumbnail_url: str
    original_url: str
    title: str
    width: int | None
    height: int | None
    duration: float | None
    format: str
    filesize: int | None
    classification: str
    classification_reason: str
    selected: bool
    download_state: str
    delivery: str = "http"
    format_id: str = ""
    formats: list[dict] = field(default_factory=list)
    subtitles: str = ""
    filesize_note: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        reasons = [self.classification_reason] if self.classification_reason else []
        return {
            "url": self.original_url or self.media_reference,
            "classification": self.classification,
            "reasons": reasons,
            "title": self.title or "media",
            "origin": self.extractor_id,
            "width": self.width,
            "height": self.height,
            "mediaType": self.media_type,
            "extractorId": self.extractor_id,
            "extractorVersion": self.extractor_version,
            "mediaReference": self.media_reference,
            "thumbnailUrl": self.thumbnail_url,
            "originalUrl": self.original_url,
            "duration": self.duration,
            "format": self.format,
            "filesize": self.filesize,
            "filesizeNote": self.filesize_note,
            "delivery": self.delivery,
            "formatId": self.format_id,
            "formats": list(self.formats),
            "subtitles": self.subtitles,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict, *, source_page_url: str = "") -> MediaRecord:
        reasons = data.get("reasons") or []
        return cls(
            media_type=str(data.get("mediaType") or "image"),
            extractor_id=str(data.get("extractorId") or data.get("origin") or ""),
            extractor_version=str(data.get("extractorVersion") or ""),
            source_page_url=source_page_url,
            media_reference=str(data.get("mediaReference") or ""),
            thumbnail_url=str(data.get("thumbnailUrl") or ""),
            original_url=str(data.get("originalUrl") or data.get("url") or ""),
            title=str(data.get("title") or ""),
            width=data.get("width"),
            height=data.get("height"),
            duration=data.get("duration"),
            format=str(data.get("format") or ""),
            filesize=data.get("filesize"),
            classification=str(data.get("classification") or "uncertain"),
            classification_reason=str(reasons[0]) if reasons else "",
            selected=str(data.get("classification") or "") == "content",
            download_state="대기",
            delivery=str(data.get("delivery") or "http"),
            format_id=str(data.get("formatId") or ""),
            formats=list(data.get("formats") or []),
            subtitles=str(data.get("subtitles") or ""),
            filesize_note=str(data.get("filesizeNote") or ""),
            error=str(data.get("error") or ""),
        )


def result_from_payload(payload: dict) -> ExtractResult:
    page = str(payload.get("pageUrl") or "")
    return ExtractResult(
        page,
        str(payload.get("extractorId") or ""),
        [MediaRecord.from_dict(item, source_page_url=page) for item in payload.get("items") or []],
        kind=str(payload.get("failureKind") or ""),
    )


@dataclass
class ExtractResult:
    page_url: str
    extractor_id: str
    records: list[MediaRecord]
    error: str = ""
    kind: str = ""

    def payload(self) -> dict:
        return {
            "pageUrl": self.page_url,
            "extractorId": self.extractor_id,
            "failureKind": self.kind,
            "items": [record.as_dict() for record in self.records],
        }
