"""WO-04B. Dynamic pages, sessions, and preview controls."""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from umd.auth.session import SessionStore, request_headers, set_active
from umd.extract.browser import collapse_variants, extraction_succeeded
from umd.extract.model import MediaRecord
from umd.net.policy_proxy import PolicyProxy
from umd.storage.database import SCHEMA_VERSION, Library
from tests.wo02_support import PNG, LabServer, Reply

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "dynamic"
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom"


def _record(url: str, **kwargs) -> MediaRecord:
    values = dict(
        media_type="image",
        extractor_id="html",
        extractor_version="test",
        source_page_url="http://127.0.0.1/",
        media_reference=url,
        thumbnail_url="",
        original_url=url,
        title="image",
        width=100,
        height=100,
        duration=None,
        format="png",
        filesize=None,
        classification="content",
        classification_reason="본문",
        selected=True,
        download_state="대기",
    )
    values.update(kwargs)
    return MediaRecord(**values)


class _Origin:
    """Local origin for the browser tests.

    Local extraction reads the body with urllib and then fulfills the route.
    urllib stops at Content-Length, then closes. This server waits for that
    close. shutdown(SHUT_WR) before the close reset some of those reads on
    this host, and the route abort surfaced as net::ERR_FAILED.
    """

    def __init__(self) -> None:
        self._socket = socket.create_server(("127.0.0.1", 0), backlog=64)
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def url(self, path: str) -> str:
        port = int(self._socket.getsockname()[1])
        return f"http://127.0.0.1:{port}{path}"

    def shutdown(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass

    def _accept(self) -> None:
        while True:
            try:
                self._socket.settimeout(0.2)
                connection, _address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(target=self._client, args=(connection,), daemon=True).start()

    def _client(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(10)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 65536:
                chunk = connection.recv(4096)
                if not chunk:
                    return
                data += chunk
            target = data.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="replace").split(" ")
            path = urlsplit(target[1] if len(target) > 1 else "/").path
            if path == "/redirect-internal":
                connection.sendall(
                    b"HTTP/1.1 302 Found\r\nLocation: http://10.1.2.3/secret\r\n"
                    b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                )
                time.sleep(0.05)
                return
            status, body, content_type = _route(path)
            head = (
                f"HTTP/1.1 {status} OK\r\nContent-Length: {len(body)}\r\n"
                f"Content-Type: {content_type}\r\nConnection: close\r\n\r\n"
            ).encode("ascii")
            connection.sendall(head + body)
            connection.settimeout(2)
            try:
                while connection.recv(4096):
                    pass
            except OSError:
                pass
        finally:
            try:
                connection.close()
            except OSError:
                pass


def _route(path: str) -> tuple[int, bytes, str]:
    name = path.rsplit("/", 1)[-1]
    page = ROOT / name
    if page.suffix == ".html" and page.is_file():
        return 200, page.read_bytes(), "text/html; charset=utf-8"
    if path.startswith("/media/") and path.endswith(".mp4"):
        return 200, MP4, "video/mp4"
    if path.startswith("/media/"):
        return 200, PNG, "image/png"
    return 404, b"missing", "text/plain"


@pytest.fixture()
def pages():
    server = _Origin()
    yield server
    server.shutdown()


def _chromium() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def chromium():
    if not _chromium():
        pytest.skip("Chromium is not installed")


def _names(result) -> list[str]:
    return sorted(urlsplit(record.original_url).path.rsplit("/", 1)[-1] for record in result.records)


def test_proxy_blocks_internal_targets_and_connects_to_the_pin():
    seen: list[tuple] = []

    def connect(address, timeout=None):
        seen.append(address)
        raise TimeoutError("stop")

    proxy = PolicyProxy("public", resolver=lambda _host, _port: ["93.184.216.34"])
    proxy._connect = connect
    client = socket.create_connection(("127.0.0.1", proxy.port), timeout=2)
    client.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
    denied = client.recv(400)
    client.close()
    blocked = PolicyProxy("local")
    other = socket.create_connection(("127.0.0.1", blocked.port), timeout=2)
    other.sendall(b"GET http://10.1.2.3/secret HTTP/1.1\r\nHost: 10.1.2.3\r\n\r\n")
    try:
        internal = other.recv(400)
    except OSError:
        internal = b""
    other.close()
    proxy.close()
    blocked.close()
    assert seen == [("93.184.216.34", 443)]
    assert b"example.com" not in b"".join(str(item).encode() for item in seen)
    assert denied
    assert b"403" in internal or "10.1.2.3" in blocked.denied
    assert "10.1.2.3" in blocked.denied


def test_variant_collapse_keeps_the_larger_image_and_the_thumbnail():
    records = collapse_variants(
        [
            _record("http://127.0.0.1/media/photo-150x150.png", width=150, height=150),
            _record("http://127.0.0.1/media/photo.png", width=800, height=600),
        ]
    )
    assert len(records) == 1
    assert records[0].original_url.endswith("/photo.png")
    assert records[0].thumbnail_url.endswith("/photo-150x150.png")


def test_sessions_stay_on_their_site_and_out_of_sqlite(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions")
    store.save(
        "127.0.0.1",
        {
            "cookies": [
                {"name": "umdtest", "value": "ok", "domain": "127.0.0.1"},
                {"name": "other", "value": "no", "domain": "example.com"},
            ]
        },
        expires_at=time.time() + 60,
    )
    same = request_headers("http://127.0.0.1/media/a.png", store)
    other = request_headers("https://example.com/a.png", store)
    assert same["Cookie"] == "umdtest=ok"
    assert "Cookie" not in other
    assert same["User-Agent"] == other["User-Agent"]
    store.save("127.0.0.1", {"cookies": [{"name": "umdtest", "value": "ok", "domain": "127.0.0.1"}]}, expires_at=time.time() - 5)
    assert store.load("127.0.0.1") is None
    assert "127.0.0.1" in store.reauth
    store.delete("127.0.0.1")
    assert store.cookie_header("http://127.0.0.1/a") == ""
    library = Library(str(tmp_path / "library.sqlite"))
    assert library.schema_version == SCHEMA_VERSION == 3
    assert b"umdtest" not in (tmp_path / "library.sqlite").read_bytes()
    library.close()
    set_active(None)


def test_preview_does_not_fetch_a_remote_video_and_can_play_a_local_file(tmp_path: Path):
    from PySide6.QtGui import QGuiApplication

    from umd.app.shell import MediaListModel, ShellBundle

    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None
    bundle = ShellBundle(db_path=str(tmp_path / "library.sqlite"))
    shell = bundle.shell
    shell._using_samples = False
    remote = {
        "kind": "video",
        "hue": 200,
        "title": "Remote",
        "fetchUrl": "https://example.com/clip.mp4",
        "mediaUrl": "https://example.com/clip.mp4",
        "previewUrl": "",
        "classification": "content",
        "status": "대기",
        "format": "mp4",
        "formats": [{"id": "0", "label": "mp4"}],
        "formatId": "0",
    }
    shell._show_detail(remote)
    shell.playPreview()
    assert shell.previewSource == ""
    assert "전체를 받지 않습니다" in shell.previewNote
    local = tmp_path / "clip.mp4"
    local.write_bytes(MP4)
    shell._show_detail({**remote, "fetchUrl": "http://127.0.0.1/media/clip.mp4", "savedPath": str(local)})
    shell.playPreview()
    assert shell.previewPlaying is True
    assert shell.previewSource.startswith("file:")
    shell.pausePreview()
    assert shell.previewPlaying is False
    assert shell.previewMuted is True
    shell.togglePreviewMute()
    assert shell.previewMuted is False
    bundle.library.close()


def test_analyze_returns_before_a_slow_page_finishes(tmp_path: Path):
    from PySide6.QtGui import QGuiApplication

    from umd.app.shell import ShellBundle

    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None
    server = LabServer()
    html = b"<article><img src='/slow.png' alt='slow' width='200' height='100'></article>"
    server.mount(
        "/page",
        lambda *_args: Reply(body=html, headers={"Content-Type": "text/html; charset=utf-8"}, hold=1.2),
    )
    server.mount("/slow.png", lambda *_args: Reply(body=PNG, headers={"Content-Type": "image/png"}))
    bundle = ShellBundle(db_path=str(tmp_path / "library.sqlite"))
    shell = bundle.shell
    shell.setUrl(server.url("/page"))
    from PySide6.QtCore import QCoreApplication

    started = time.perf_counter()
    shell.analyze()
    shell.toggleTheme()
    elapsed = time.perf_counter() - started
    deadline = time.time() + 5
    while time.time() < deadline and shell.jobPhase == "추출 중":
        QCoreApplication.processEvents()
        time.sleep(0.02)
    shell.joinWorkers()
    server.shutdown()
    bundle.library.close()
    assert elapsed < 0.5
    assert shell.theme == "dark"


def _trace_browser(log_path: Path) -> None:
    import umd.extract.browser as browser

    if getattr(browser, "_wo04s3_traced", False):
        return
    original = browser.arm_page

    def arm(page, network_mode: str) -> None:
        original(page, network_mode)

        def write(kind: str, url: str, detail: str = "") -> None:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{time.monotonic():.3f}\t{kind}\t{url}\t{detail}\n")
                handle.flush()

        page.on("request", lambda request: write("request", request.url))
        page.on("response", lambda response: write("response", response.url, str(response.status)))
        page.on("requestfailed", lambda request: write("requestfailed", request.url, str(request.failure or "")))
        page.on("requestfinished", lambda request: write("requestfinished", request.url))

    browser.arm_page = arm
    browser._wo04s3_traced = True


def test_javascript_images_spa_lazy_scroll_and_cleanup(pages, chromium):
    from umd.extract.browser import extract_dynamic
    from umd.extract.router import extract_page

    trace = os.environ.get("WO04S3_LAZY_LOG", "")
    if trace:
        path = Path(trace)
        path.parent.mkdir(parents=True, exist_ok=True)
        _trace_browser(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.monotonic():.3f}\tfixture\t{pages.url('/lazy.html')}\tready\n")
            handle.flush()
    PolicyProxy.denied_all.clear()
    added = extract_page(pages.url("/js-added.html"), network_mode="local")
    assert extraction_succeeded(added)
    assert _names(added) == ["added.png"]
    assert added.records[0].classification == "content"
    assert "169.254.169.254" in PolicyProxy.denied_all
    first = extract_dynamic(pages.url("/spa.html") + "#/post/1")
    second = extract_dynamic(pages.url("/spa.html") + "#/post/2")
    assert _names(first) == ["post-1.png"]
    assert _names(second) == ["post-2.png"]
    lazy_url = pages.url("/lazy.html")
    if trace:
        with Path(trace).open("a", encoding="utf-8") as handle:
            handle.write(f"{time.monotonic():.3f}\tgoto\t{lazy_url}\tcall\n")
            handle.flush()
    lazy = extract_dynamic(lazy_url)
    if trace:
        with Path(trace).open("a", encoding="utf-8") as handle:
            handle.write(f"{time.monotonic():.3f}\tgoto\t{lazy_url}\treturned\n")
            handle.flush()
    assert _names(lazy) == ["lazy.png"]
    scrolled = extract_dynamic(pages.url("/scroll.html"))
    assert _names(scrolled) == ["scroll-1.png", "scroll-2.png", "scroll-3.png"]
    assert len(scrolled.records) == 3
    port = PolicyProxy.last_port
    probe = socket.socket()
    with pytest.raises(OSError):
        probe.connect(("127.0.0.1", port))
    probe.close()


def test_browser_classifier_keeps_small_body_images_and_drops_chrome(pages, chromium):
    from umd.extract.browser import extract_dynamic

    result = extract_dynamic(pages.url("/classify.html"))
    by_name = {urlsplit(record.original_url).path.rsplit("/", 1)[-1]: record for record in result.records}
    assert by_name["body.png"].classification == "content"
    assert by_name["tiny.png"].classification == "content"
    assert "작지만" in by_name["tiny.png"].classification_reason
    assert by_name["related.png"].classification == "excluded"
    assert by_name["ad.png"].classification == "excluded"
    assert by_name["avatar.png"].classification == "excluded"
    assert by_name["logo.png"].classification == "excluded"
    assert by_name["maybe.png"].classification == "uncertain"
    assert by_name["maybe.png"].selected is False


def test_browser_dedupes_thumbnail_and_reads_video_metadata(pages, chromium):
    from umd.extract.browser import extract_dynamic

    images = extract_dynamic(pages.url("/dedupe.html"))
    assert len(images.records) == 1
    assert images.records[0].original_url.endswith("/photo.png")
    assert "150x150" in images.records[0].thumbnail_url
    video = extract_dynamic(pages.url("/video.html"))
    assert len(video.records) == 1
    assert video.records[0].media_type == "video"
    assert video.records[0].original_url.endswith("/clip.mp4")
    assert video.records[0].thumbnail_url.endswith("/poster.png")
    assert video.records[0].format
    empty = extract_dynamic(pages.url("/empty.html"))
    assert extraction_succeeded(empty) is False


def test_redirect_websocket_and_subresource_stay_on_policy(pages, chromium):
    from umd.extract.browser import _socket_allowed, context_options, extract_dynamic
    from umd.netpolicy import ExtractError

    assert context_options()["service_workers"] == "block"
    assert _socket_allowed("ws://10.9.8.7/socket", "local") is False
    assert _socket_allowed("ws://127.0.0.1/socket", "local") is True
    assert _socket_allowed("wss://10.1.2.3/socket", "public") is False
    PolicyProxy.denied_all.clear()
    try:
        redirected = extract_dynamic(pages.url("/redirect-internal"))
    except ExtractError:
        redirected = None
    assert redirected is None or extraction_succeeded(redirected) is False
    assert "10.1.2.3" in PolicyProxy.denied_all
    PolicyProxy.denied_all.clear()
    extract_dynamic(pages.url("/policy.html"))
    assert "10.9.8.7" in PolicyProxy.denied_all
    from playwright.sync_api import sync_playwright

    from umd.extract.browser import arm_page

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        page = browser.new_context(**context_options()).new_page()
        arm_page(page, "local")
        page.goto(pages.url("/ws.html"), wait_until="domcontentloaded", timeout=8000)
        assert page.evaluate("() => document.body.dataset.ws") == "blocked"
        browser.close()


def test_mock_login_is_site_local(pages, chromium, tmp_path: Path):
    from umd.auth.login import open_login_window

    store = SessionStore(tmp_path / "sessions")

    def click(page) -> None:
        page.click("#login")
        page.wait_for_timeout(100)

    open_login_window(pages.url("/login.html"), store, headless=True, interact=click)
    assert store.cookie_header(pages.url("/login.html")) == "umdtest=ok"
    assert store.cookie_header("http://example.com/login") == ""
    library = Library(str(tmp_path / "library.sqlite"))
    library.create_job(pages.url("/login.html"), [])
    assert b"umdtest" not in (tmp_path / "library.sqlite").read_bytes()
    library.close()
