"""Choose one extractor. Local mode stays on the WO-01 HTML path."""

from __future__ import annotations

from umd.extract.fetch import fetch_text
from umd.extract.gallery import can_handle as gallery_can_handle
from umd.extract.gallery import extract_gallery
from umd.extract.html_adapter import extract_html
from umd.extract.model import ExtractResult
from umd.extract.video import can_handle as video_can_handle
from umd.extract.video import extract_video
from umd.netpolicy import DnsError, ExtractError, PolicyError, assess_public_url


def extract_page(url: str, *, network_mode: str = "local") -> ExtractResult:
    if network_mode != "public":
        final, html = fetch_text(url)
        return _maybe_browser(final, html, extract_html(html, final), "local")
    decision = assess_public_url(url)
    if not decision.allowed:
        if decision.kind == "dns":
            raise DnsError(decision.message)
        raise PolicyError(decision.message or "허용되지 않은 주소입니다")
    return _public(decision.safe_url)


def _public(url: str) -> ExtractResult:
    gallery_hit = gallery_can_handle(url)
    video_hit = video_can_handle(url)
    if gallery_hit:
        try:
            gallery_result = extract_gallery(url)
        except (PolicyError, DnsError):
            raise
        except ExtractError:
            gallery_result = None
        except Exception as exc:
            if not video_hit:
                raise ExtractError(str(exc)[:300]) from exc
            gallery_result = None
        if gallery_result is not None:
            direct = [
                record
                for record in gallery_result.records
                if record.delivery == "http" and record.media_type == "image"
            ]
            if direct or (gallery_result.records and not video_hit):
                gallery_result.records = _prefer(gallery_result.records, direct)
                return gallery_result
    if video_hit:
        return extract_video(url)
    final, html = fetch_text(url, network_mode="public")
    return _maybe_browser(final, html, extract_html(html, final), "public")


def _prefer(records, direct):
    return direct or records


def _needs_browser(html: str, static: ExtractResult) -> bool:
    from urllib.parse import urlsplit

    if urlsplit(static.page_url).scheme not in {"http", "https"}:
        return False
    lowered = html.lower()
    if "data-umd-dynamic" in lowered:
        return True
    if static.records:
        return False
    return "<script" in lowered and ("<article" in lowered or 'id="app"' in lowered)


def _maybe_browser(url: str, html: str, static: ExtractResult, network_mode: str) -> ExtractResult:
    if not _needs_browser(html, static):
        return static
    from umd.extract.browser import browser_enabled, collapse_variants, extract_dynamic, extraction_succeeded

    if not browser_enabled():
        return static
    try:
        dynamic = extract_dynamic(url, network_mode=network_mode)
    except ExtractError:
        if static.records:
            return static
        raise
    if not extraction_succeeded(dynamic):
        return static if static.records else dynamic
    merged = collapse_variants([*static.records, *dynamic.records])
    return ExtractResult(url, dynamic.extractor_id, merged, kind="browser")
