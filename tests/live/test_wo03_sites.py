"""Real public pages. These are not part of the offline regression set."""

import json
from pathlib import Path

from umd.download.engine import DownloadItem, run_job
from umd.download.schedule import EngineConfig
from umd.download.video_job import download_video
from umd.extract.fetch import fetch_text
from umd.extract.gallery import extract_gallery, installed_version as gallery_version
from umd.extract.router import extract_page
from umd.extract.video import extract_video, installed_version as video_version

HTML_PAGE = "https://www.w3.org/Graphics/PNG/inline-alpha.html"
GALLERY_PAGE = "https://commons.wikimedia.org/wiki/File:PNG_transparency_demonstration_1.png"
IMAGE_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/PNG_transparency_demonstration_1.png"
VIDEO_PAGE = "https://commons.wikimedia.org/wiki/File:Short.ogv"
_CAP = 8 * 1024 * 1024


def _license_phrase(html: str) -> str:
    lowered = html.lower()
    for phrase in ("public domain", "cc0", "creative commons", "gfdl"):
        if phrase in lowered:
            return phrase
    return ""


def test_public_html_extracts_images():
    result = extract_page(HTML_PAGE, network_mode="public")
    assert result.extractor_id == "html"
    assert result.records
    content = [record for record in result.records if record.classification == "content"]
    print(
        "WO03_LIVE",
        json.dumps(
            {
                "kind": "html",
                "url": HTML_PAGE,
                "date": "2026-11-01",
                "count": len(result.records),
                "content": len(content),
                "uncertain": sum(record.classification == "uncertain" for record in result.records),
                "excluded": sum(record.classification == "excluded" for record in result.records),
            },
            ensure_ascii=False,
        ),
    )


def test_gallery_lists_a_commons_image_and_the_engine_saves_it(tmp_path: Path):
    _page, html = fetch_text(GALLERY_PAGE, network_mode="public")
    phrase = _license_phrase(html)
    assert phrase, "the Commons file page did not show a reuse license"
    listed = extract_gallery(GALLERY_PAGE)
    direct = [record for record in listed.records if record.delivery == "http"]
    assert direct
    engine = run_job(
        tmp_path,
        [DownloadItem("commons", IMAGE_URL)],
        EngineConfig(network_mode="public", per_file_cap=_CAP, timeout=40, max_retries=1),
    )
    done = [event for event in engine.events if event.status == "완료"]
    assert done, [event.error for event in engine.events if event.terminal]
    saved = Path(done[-1].path)
    assert saved.is_file()
    assert saved.stat().st_size > 0
    assert saved.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    print(
        "WO03_LIVE",
        json.dumps(
            {
                "kind": "gallery-image",
                "date": "2026-11-01",
                "url": GALLERY_PAGE,
                "download": IMAGE_URL,
                "license": phrase,
                "gallery": gallery_version(),
                "listed": len(listed.records),
                "bytes": saved.stat().st_size,
            },
            ensure_ascii=False,
        ),
    )


def test_ytdlp_probes_and_downloads_a_public_domain_clip(tmp_path: Path):
    _page, html = fetch_text(VIDEO_PAGE, network_mode="public")
    phrase = _license_phrase(html)
    assert phrase, "the video file page did not show a reuse license"
    probed = extract_video(VIDEO_PAGE)
    record = probed.records[0]
    exact = [item for item in record.formats if item.get("filesize") and item["filesize"] <= _CAP]
    estimated = [
        item
        for item in record.formats
        if not item.get("filesize") and item.get("filesizeApprox") and item["filesizeApprox"] <= _CAP
    ]
    assert exact or estimated, "no format was small enough to download"
    if exact:
        chosen = min(exact, key=lambda item: item["filesize"])
        size_basis = "exact"
    else:
        chosen = min(estimated, key=lambda item: item["filesizeApprox"])
        size_basis = "approx"
    path, size = download_video(
        VIDEO_PAGE,
        tmp_path,
        format_id=str(chosen["id"]),
        should_stop=lambda: "",
        on_progress=lambda _downloaded, _total: None,
    )
    assert path.is_file()
    assert size == path.stat().st_size
    assert 0 < size <= _CAP
    print(
        "WO03_LIVE",
        json.dumps(
            {
                "kind": "video",
                "date": "2026-11-01",
                "url": VIDEO_PAGE,
                "license": phrase,
                "yt_dlp": video_version(),
                "title": record.title,
                "duration": record.duration,
                "format": chosen["id"],
                "sizeBasis": size_basis,
                "filesize": chosen.get("filesize"),
                "filesizeApprox": chosen.get("filesizeApprox"),
                "saved": size,
                "subtitles": record.subtitles or "미확인",
            },
            ensure_ascii=False,
        ),
    )
