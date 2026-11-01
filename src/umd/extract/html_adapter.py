"""HTML body images as MediaRecord values. The WO-01 parser is unchanged."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlsplit

from umd.extract.html_images import extract_images
from umd.extract.model import ExtractResult, MediaRecord

EXTRACTOR_ID = "html"
EXTRACTOR_VERSION = "wo01"


def records_from_html(html: str, page_url: str) -> list[MediaRecord]:
    records: list[MediaRecord] = []
    for candidate in extract_images(html, page_url):
        suffix = PurePosixPath(urlsplit(candidate.url).path).suffix.lower()
        records.append(
            MediaRecord(
                media_type="image",
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                source_page_url=page_url,
                media_reference=candidate.url,
                thumbnail_url="",
                original_url=candidate.url,
                title=candidate.title or "image",
                width=candidate.width,
                height=candidate.height,
                duration=None,
                format=suffix.lstrip("."),
                filesize=None,
                classification=candidate.classification,
                classification_reason=" · ".join(candidate.reasons),
                selected=candidate.classification == "content",
                download_state="대기",
                delivery="http",
            )
        )
    return records


def extract_html(html: str, page_url: str) -> ExtractResult:
    return ExtractResult(page_url, EXTRACTOR_ID, records_from_html(html, page_url))
