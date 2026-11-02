"""Render a page with Playwright and classify the live DOM.

The browser runs on the caller thread, which is the extract worker, not the
UI thread. DOMContentLoaded is not treated as finished: the page must settle,
and scrolling stops after a stable height, an end marker, or eight passes.
Opening the browser is not a successful extract. A result needs a media URL.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from umd.extract.html_adapter import records_from_html
from umd.extract.model import ExtractResult, MediaRecord
from umd.net.policy_proxy import PolicyProxy
from umd.netpolicy import ExtractError

EXTRACTOR_ID = "playwright"
EXTRACTOR_VERSION = "wo04"
_MAX_SCROLLS = 8
_AD = {"ad", "ads", "advert", "sponsor", "advertisement", "sponsored"}
_RELATED = {"related", "recommend", "recommended", "suggestions", "related-posts", "more-posts", "aside"}
_AVATAR = {"avatar", "author-avatar", "profile-photo", "author-photo"}
_LOGO = {"logo", "site-logo"}

_DUMP = """
() => {
  function marks(el) {
    const found = [];
    let node = el;
    while (node && node.nodeType === 1) {
      found.push(node.tagName.toLowerCase());
      if (typeof node.className === "string" && node.className) {
        found.push(...node.className.split(/\\s+/).filter(Boolean));
      }
      if (node.id) found.push(node.id);
      node = node.parentElement;
    }
    return found;
  }
  const images = [...document.images].map((img) => {
    const rect = img.getBoundingClientRect();
    const attrW = parseInt(img.getAttribute("width") || "0", 10) || 0;
    const attrH = parseInt(img.getAttribute("height") || "0", 10) || 0;
    return {
    src: img.currentSrc || img.getAttribute("src") || "",
    srcset: img.getAttribute("srcset") || "",
    dataSrc: img.getAttribute("data-src") || "",
    dataOriginal: img.getAttribute("data-original") || "",
    alt: img.alt || "",
    width: attrW || Math.round(rect.width || 0),
    height: attrH || Math.round(rect.height || 0),
    href: img.closest("a") ? img.closest("a").href : "",
    marks: marks(img)
  };
  });
  const videos = [...document.querySelectorAll("video")].map((video) => {
    const source = video.querySelector("source");
    return {
      src: video.currentSrc || video.getAttribute("src") || (source ? source.src : ""),
      poster: video.poster || "",
      type: source ? (source.type || "") : "",
      width: Math.round(video.getBoundingClientRect().width || video.width || 0),
      height: Math.round(video.getBoundingClientRect().height || video.height || 0),
      marks: marks(video)
    };
  });
  return {
    images,
    videos,
    ended: !!(document.body && document.body.dataset.umdEnd === "1")
  };
}
"""


def browser_enabled() -> bool:
    import os

    if os.environ.get("UMD_BROWSER") == "0":
        return False
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def extraction_succeeded(result: ExtractResult) -> bool:
    return any(_http_url(record.original_url) for record in result.records)


def extract_dynamic(url: str, *, network_mode: str = "local", headless: bool = True) -> ExtractResult:
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ExtractError("브라우저는 http 주소만 분석합니다")
    if not browser_enabled():
        raise ExtractError("브라우저 분석은 이 환경에서 비활성화되어 있습니다")
    from playwright.sync_api import sync_playwright

    started = time.perf_counter()
    last: Exception | None = None
    for attempt in range(3):
        try:
            return _extract_once(url, network_mode, headless, playwright_factory=sync_playwright, started=started)
        except ExtractError as exc:
            last = exc
            if attempt == 2 or "ERR_CONNECTION_RESET" not in str(exc):
                raise
            time.sleep(0.25)
    if last is not None:
        raise last
    raise ExtractError("브라우저 분석에 실패했습니다")


def _extract_once(url: str, network_mode: str, headless: bool, *, playwright_factory, started: float) -> ExtractResult:
    # Local fixtures stay off the proxy. Routing loopback through it resets the
    # socket on this Windows host. Public mode still pins every connection.
    proxy = PolicyProxy(network_mode) if network_mode == "public" else None
    browser = None
    try:
        with playwright_factory() as playwright:
            launch = {
                "headless": headless,
                "args": [
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--renderer-process-limit=1",
                    "--js-flags=--max-old-space-size=256",
                ],
            }
            if proxy is not None:
                launch["proxy"] = {"server": proxy.url, "bypass": "<-loopback>"}
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context(**context_options())
            page = context.new_page()
            arm_page(page, network_mode)
            page.set_default_timeout(15000)
            _goto(page, url)
            _settle(page)
            dumped = page.evaluate(_DUMP)
            context.close()
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError(f"브라우저 분석에 실패했습니다: {exc}"[:300]) from exc
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if proxy is not None:
            proxy.close()
    records = records_from_dump(dumped if isinstance(dumped, dict) else {}, url)
    elapsed = time.perf_counter() - started
    kind = "browser" if extraction_succeeded(ExtractResult(url, EXTRACTOR_ID, records)) else "empty"
    result = ExtractResult(url, EXTRACTOR_ID, records, kind=kind)
    result.error = "" if records else "동적 페이지에서 미디어를 찾지 못했습니다"
    result.records = _note_time(records, elapsed)
    return result


def records_from_dump(dumped: dict, page_url: str) -> list[MediaRecord]:
    fragments: list[str] = []
    for image in dumped.get("images") or []:
        fragments.append(_image_html(image))
    html = "<html><body>" + "".join(fragments) + "</body></html>"
    records = records_from_html(html, page_url)
    records.extend(_videos(dumped.get("videos") or [], page_url))
    return collapse_variants(records)


def collapse_variants(records: list[MediaRecord]) -> list[MediaRecord]:
    chosen: dict[str, MediaRecord] = {}
    for record in records:
        key = _variant_key(record.original_url or record.media_reference)
        current = chosen.get(key)
        if current is None:
            chosen[key] = record
            continue
        if _better(record, current):
            if not record.thumbnail_url:
                record.thumbnail_url = current.thumbnail_url or current.original_url
            chosen[key] = record
        elif not current.thumbnail_url and current.original_url != record.original_url:
            current.thumbnail_url = record.original_url
    return list(chosen.values())


def context_options() -> dict:
    """Service workers stay off. Playwright does not route them through the gate."""

    return {
        "viewport": {"width": 1100, "height": 720},
        "ignore_https_errors": False,
        "service_workers": "block",
    }


_WS_GUARD = """
(() => {
  const Native = window.WebSocket;
  if (!Native || window.__umdWsGuard) return;
  window.__umdWsGuard = true;
  const allowed = new Set(["127.0.0.1", "localhost"]);
  function Guard(url, protocols) {
    let host = "";
    try { host = new URL(String(url), location.href).hostname.toLowerCase(); } catch (error) { host = ""; }
    if (!allowed.has(host)) throw new Error("blocked");
    return protocols === undefined ? new Native(url) : new Native(url, protocols);
  }
  Guard.prototype = Native.prototype;
  Guard.CONNECTING = Native.CONNECTING;
  Guard.OPEN = Native.OPEN;
  Guard.CLOSING = Native.CLOSING;
  Guard.CLOSED = Native.CLOSED;
  window.WebSocket = Guard;
})();
"""


def arm_page(page, network_mode: str) -> None:
    """Install the request gate. A page that cannot take the gate is not used.

    Playwright's sync WebSocket route stalls this host when a socket is opened,
    so local mode disables non-loopback sockets in the page instead. Public
    mode still sends those sockets through the pinning proxy.
    """

    try:
        page.route("**/*", lambda route: _gate(route, network_mode))
        if network_mode != "public":
            page.add_init_script(_WS_GUARD)
    except Exception as exc:
        raise ExtractError("브라우저 접근 정책을 적용할 수 없어 분석을 하지 않습니다") from exc


def _socket_allowed(url: str, network_mode: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"ws", "wss", "http", "https"}:
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if network_mode != "public":
        return host in {"127.0.0.1", "localhost"}
    from umd.netpolicy import assess_public_url

    probe = "https" if parts.scheme in {"wss", "https"} else "http"
    decision = assess_public_url(f"{probe}://{host}/")
    return bool(decision.allowed)


_REDIRECTS = {301, 302, 303, 307, 308}
_DROP_HEADERS = {"connection", "transfer-encoding", "content-encoding", "content-length", "keep-alive"}


def _local_host(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    return host in {"127.0.0.1", "localhost"}


def _read_without_redirect(url: str) -> tuple[int, dict[str, str], bytes]:
    """Read one response. A redirect is returned, not followed.

    Playwright on this host does not route the browser's next hop, and
    ``route.fetch`` inside the sync handler never returns. Reading here keeps
    that hop from leaving the policy.
    """

    import urllib.error
    import urllib.request

    class _Stop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_Stop)
    request = urllib.request.Request(url, method="GET")
    try:
        with opener.open(request, timeout=10) as response:
            headers = {key: value for key, value in response.headers.items()}
            return response.status, headers, response.read()
    except urllib.error.HTTPError as exc:
        headers = {key: value for key, value in exc.headers.items()}
        return exc.code, headers, exc.read()


def _fulfill_local(route) -> None:
    from urllib.parse import urljoin

    url = route.request.url
    try:
        status, headers, body = _read_without_redirect(url)
    except Exception:
        route.abort()
        return
    for _ in range(4):
        if status not in _REDIRECTS:
            break
        location = headers.get("Location") or headers.get("location") or ""
        target = urljoin(url, location) if location else ""
        if not _local_host(target):
            host = (urlsplit(target).hostname or "").lower().rstrip(".")
            PolicyProxy.denied_all.append(host)
            route.abort()
            return
        url = target
        try:
            status, headers, body = _read_without_redirect(url)
        except Exception:
            route.abort()
            return
    if status in _REDIRECTS:
        route.abort()
        return
    clean = {key: value for key, value in headers.items() if key.lower() not in _DROP_HEADERS}
    route.fulfill(status=status, headers=clean, body=body)


def _gate(route, network_mode: str) -> None:
    host = (urlsplit(route.request.url).hostname or "").lower().rstrip(".")
    if network_mode != "public":
        if not _local_host(route.request.url):
            PolicyProxy.denied_all.append(host)
            route.abort()
            return
        _fulfill_local(route)
        return
    from umd.netpolicy import assess_public_url

    decision = assess_public_url(route.request.url)
    if not decision.allowed:
        PolicyProxy.denied_all.append(host)
        route.abort()
        return
    route.continue_()


def _goto(page, url: str) -> None:
    last: Exception | None = None
    for attempt in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return
        except Exception as exc:
            last = exc
            if attempt == 1 or "ERR_CONNECTION_RESET" not in str(exc):
                raise
    if last is not None:
        raise last


def _settle(page) -> None:
    previous = None
    stable = 0
    for index in range(_MAX_SCROLLS + 1):
        state = page.evaluate(
            """() => ({
                images: document.images.length,
                ended: !!(document.body && document.body.dataset.umdEnd === '1'),
                height: document.body ? document.body.scrollHeight : 0
            })"""
        )
        if state.get("ended"):
            break
        if state == previous:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
            previous = state
        if index >= _MAX_SCROLLS:
            break
        page.evaluate("() => window.scrollBy(0, Math.max(window.innerHeight, 600))")
        page.wait_for_timeout(200)
    page.wait_for_timeout(200)


def _image_html(image: dict) -> str:
    marks = {str(item).lower() for item in image.get("marks") or []}
    src = _attr(image.get("src"))
    srcset = _attr(image.get("srcset"))
    data_src = _attr(image.get("dataSrc"))
    data_original = _attr(image.get("dataOriginal"))
    alt = _attr(image.get("alt") or "image")
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    href = _attr(image.get("href"))
    tag = (
        f'<img alt="{alt}" width="{width}" height="{height}" '
        f'src="{src}" srcset="{srcset}" data-src="{data_src}" data-original="{data_original}">'
    )
    if href:
        tag = f'<a href="{href}">{tag}</a>'
    if marks & _AD:
        return f'<div class="advertisement">{tag}</div>'
    if marks & _RELATED:
        return f'<aside class="related">{tag}</aside>'
    if marks & _LOGO or "nav" in marks:
        return f'<nav><span class="logo">{tag}</span></nav>'
    if marks & _AVATAR:
        return f'<div class="avatar">{tag}</div>'
    if "article" in marks or "main" in marks:
        return f"<article>{tag}</article>"
    return f"<div>{tag}</div>"


def _videos(videos: list, page_url: str) -> list[MediaRecord]:
    records = []
    for video in videos:
        src = str(video.get("src") or "")
        if not _http_url(src):
            continue
        marks = {str(item).lower() for item in video.get("marks") or []}
        excluded = bool(marks & _AD or marks & _RELATED)
        in_body = "article" in marks or "main" in marks
        classification = "excluded" if excluded else ("content" if in_body else "uncertain")
        reason = "본문 안의 영상" if classification == "content" else "영상 요소"
        if excluded:
            reason = "광고 또는 추천 영역의 영상"
        kind = str(video.get("type") or "")
        suffix = urlsplit(src).path.rsplit(".", 1)[-1].lower() if "." in urlsplit(src).path else ""
        records.append(
            MediaRecord(
                media_type="video",
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                source_page_url=page_url,
                media_reference=page_url,
                thumbnail_url=str(video.get("poster") or ""),
                original_url=src,
                title="video",
                width=int(video.get("width") or 0) or None,
                height=int(video.get("height") or 0) or None,
                duration=None,
                format=suffix or kind,
                filesize=None,
                classification=classification,
                classification_reason=reason,
                selected=classification == "content",
                download_state="대기",
                delivery="http",
            )
        )
    return records


def _note_time(records: list[MediaRecord], elapsed: float) -> list[MediaRecord]:
    note = f"브라우저 분석 {elapsed:.2f}s"
    for record in records:
        record.classification_reason = " · ".join(
            part for part in (record.classification_reason, note) if part
        )
    return records


def _better(incoming: MediaRecord, current: MediaRecord) -> bool:
    rank = {"content": 3, "uncertain": 2, "excluded": 1}
    if rank.get(incoming.classification, 0) != rank.get(current.classification, 0):
        return rank.get(incoming.classification, 0) > rank.get(current.classification, 0)
    return (incoming.width or 0) * (incoming.height or 0) > (current.width or 0) * (current.height or 0)


def _variant_key(url: str) -> str:
    import re

    parts = urlsplit(url)
    path = re.sub(
        r"[-_](?:\d{2,4}x\d{2,4}|\d{2,4}w|thumb|small|medium|large)(?=\.[A-Za-z0-9]{2,5}$)",
        "",
        parts.path,
        flags=re.IGNORECASE,
    )
    return f"{parts.netloc.lower()}{path.lower()}"


def _http_url(url: str) -> bool:
    return urlsplit(url or "").scheme in {"http", "https"}


def _attr(value: object) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )
