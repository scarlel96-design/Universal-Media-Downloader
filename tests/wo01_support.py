"""Local HTTP fixture server for the WO-01 image tests.

Python's http.server resets localhost clients on this Windows host, so the
fixture speaks a small HTTP/1.0 dialect on its own sockets.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "tests" / "fixtures" / "posts"
PHOTOS = POSTS / "photos"
EXPECTED = json.loads((POSTS / "expected.json").read_text(encoding="utf-8"))
_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".html": "text/html; charset=utf-8",
}


def ensure_photos() -> None:
    spec = importlib.util.spec_from_file_location("make_photos", POSTS / "make_photos.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.ensure()


class FixtureServer:
    def __init__(self) -> None:
        ensure_photos()
        self._socket = socket.create_server(("127.0.0.1", 0), backlog=64)
        self.server_address = self._socket.getsockname()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept, name="wo01-fixture", daemon=True)
        self._thread.start()

    def _accept(self) -> None:
        while not self._stop.is_set():
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
            connection.settimeout(5)
            raw = b""
            while b"\r\n\r\n" not in raw and len(raw) < 16384:
                chunk = connection.recv(4096)
                if not chunk:
                    return
                raw += chunk
            line = raw.split(b"\r\n", 1)[0].decode("latin1", errors="replace")
            parts = line.split(" ")
            path = unquote(urlsplit(parts[1]).path) if len(parts) > 1 else "/"
            status, content_type, body, delay, declared = _route(path)
            if delay:
                time.sleep(delay)
            length = len(body) if declared is None else declared
            reason = "OK" if status == 200 else "ERROR"
            head = (
                f"HTTP/1.0 {status} {reason}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {length}\r\n"
                "Connection: close\r\n\r\n"
            )
            connection.sendall(head.encode("ascii") + body)
            try:
                connection.shutdown(socket.SHUT_WR)
            except OSError:
                return
            while connection.recv(1024):
                pass
        except OSError:
            return
        finally:
            try:
                connection.close()
            except OSError:
                return

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self._socket.close()
        except OSError:
            return

    def server_close(self) -> None:
        self.shutdown()


def _file_under_posts(path: str) -> Path | None:
    candidate = (POSTS / path.lstrip("/")).resolve()
    posts = POSTS.resolve()
    if candidate == posts or posts not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def _route(path: str) -> tuple[int, str, bytes, float, int | None]:
    if path == "/alias/coast.png":
        return 200, "image/png", (PHOTOS / "twin.png").read_bytes(), 0, None
    if path == "/slow/hold.png":
        return 200, "image/png", (PHOTOS / "panel.png").read_bytes(), 0.8, None
    if path == "/slow/cancel.png":
        return 200, "image/png", (PHOTOS / "dot.png").read_bytes(), 0.7, None
    if path == "/corrupt.png":
        body = b"<html>not an image</html>"
        return 200, "text/html", body, 0, None
    if path == "/short.png":
        body = (PHOTOS / "dot.png").read_bytes()
        return 200, "image/png", body, 0, len(body) + 40
    if path == "/missing.png":
        return 404, "text/plain", b"missing", 0, None
    if path == "/boom.png":
        return 500, "text/plain", b"boom", 0, None
    file = _file_under_posts(path)
    if file is None:
        return 404, "text/plain", b"missing", 0, None
    return 200, _TYPES.get(file.suffix.lower(), "application/octet-stream"), file.read_bytes(), 0, None


def serve() -> FixtureServer:
    return FixtureServer()


def base_url(httpd: FixtureServer) -> str:
    port = httpd.server_address[1]
    return f"http://127.0.0.1:{port}"
