"""Extractor records, gallery metadata, and yt-dlp format selection."""

from pathlib import Path

import pytest

from gallery_dl.extractor.message import Message

from umd.extract.gallery import installed_version as gallery_version
from umd.extract.gallery import records_from_messages, supported_site_count as gallery_sites
from umd.extract.html_adapter import records_from_html
from umd.extract.model import display_unknown
from umd.extract.router import extract_page
from umd.extract.video import installed_version as video_version
from umd.extract.video import record_from_info, supported_site_count as video_sites

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "posts" / "article.html"


def test_html_adapter_keeps_body_images_and_excludes_ads():
    records = records_from_html(FIXTURE.read_text(encoding="utf-8"), FIXTURE.as_uri())
    by_class = {record.classification for record in records}
    assert "content" in by_class
    assert "excluded" in by_class
    content = [record for record in records if record.classification == "content"]
    assert content
    assert all(record.extractor_id == "html" for record in content)
    assert all(record.delivery == "http" for record in content)
    small = [record for record in content if record.width == 1 or record.height == 1]
    assert small, "a small body image must stay selectable"


def test_local_router_stays_on_the_html_extractor():
    result = extract_page(FIXTURE.as_uri(), network_mode="local")
    assert result.extractor_id == "html"
    assert result.records


def test_gallery_messages_keep_the_original_and_skip_the_thumbnail():
    messages = [
        (
            Message.Url,
            "https://cdn.example/a.jpg",
            {
                "filename": "a",
                "extension": "jpg",
                "width": 8,
                "height": 8,
                "thumbnail": "https://cdn.example/a-thumb.jpg",
            },
        ),
        (Message.Url, "https://cdn.example/a-thumb.jpg", {"type": "thumbnail", "extension": "jpg"}),
        (Message.Url, "https://cdn.example/a.jpg", {"extension": "jpg"}),
    ]
    records = records_from_messages(messages, "https://gallery.example/post", gallery_version())
    assert len(records) == 1
    assert records[0].original_url == "https://cdn.example/a.jpg"
    assert records[0].thumbnail_url == "https://cdn.example/a-thumb.jpg"
    assert records[0].delivery == "http"
    assert records[0].media_reference == "https://gallery.example/post"
    assert gallery_sites() > 50


def test_video_info_hides_unknowns_and_drops_drm():
    page = "https://commons.wikimedia.org/wiki/File:Short.ogv"
    record = record_from_info(
        {
            "id": "abc",
            "title": "Short",
            "duration": 5.8,
            "thumbnail": "https://example.com/t.jpg",
            "webpage_url": page,
            "subtitles": {"en": [{"url": "https://example.com/secret-caption.vtt"}]},
            "formats": [
                {
                    "format_id": "video-only",
                    "ext": "webm",
                    "vcodec": "vp9",
                    "acodec": "none",
                    "height": 480,
                    "width": 640,
                    "protocol": "https",
                    "filesize": 1000,
                    "url": "https://cdn.example/signed?token=s3cret-token",
                },
                {
                    "format_id": "drm",
                    "ext": "mp4",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "has_drm": True,
                    "height": 720,
                    "protocol": "https",
                    "url": "https://cdn.example/drm",
                },
                {
                    "format_id": "best",
                    "ext": "ogv",
                    "vcodec": "theora",
                    "acodec": "vorbis",
                    "height": 240,
                    "width": 320,
                    "protocol": "https",
                    "filesize": 500,
                },
            ],
        },
        page_url=page,
        version="test",
    )
    assert record.format_id == "best"
    assert record.filesize == 500
    assert record.original_url == page
    assert "s3cret-token" not in str(record.as_dict())
    assert "drm" not in {item["id"] for item in record.formats}
    assert record.subtitles == "자막 en"
    assert record.duration == 5.8
    unknown = record_from_info({"id": "x"}, page_url=page, version="test")
    assert unknown.title == display_unknown(None)
    assert unknown.duration is None
    assert display_unknown(unknown.duration) == "미확인"
    assert video_sites() > 100
    assert video_version()


def test_video_download_refuses_a_loopback_page(tmp_path):
    from umd.download.video_job import download_video
    from umd.netpolicy import PolicyError

    with pytest.raises(PolicyError, match="내부 네트워크"):
        download_video(
            "http://127.0.0.1/clip.ogv",
            tmp_path,
            format_id="b",
            should_stop=lambda: "",
            on_progress=lambda _downloaded, _total: None,
        )
