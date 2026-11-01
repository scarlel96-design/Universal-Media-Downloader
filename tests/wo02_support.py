"""Local HTTP lab for parallel download tests.

The server speaks HTTP/1.1, closes the socket after one response, and drains
the unread tail. That is the pattern that stayed stable on this Windows host.
"""

from __future__ import annotations

import base64
import socket
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def unique_png(index: int) -> bytes:
    return PNG + index.to_bytes(4, "big")


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    hold: float = 0.0
    trickle: float = 0.0
    truncate_to: int | None = None
    reason: str = ""


class LabServer:
    def __init__(self) -> None:
        self._socket = socket.create_server(("127.0.0.1", 0), backlog=256)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._handlers: dict[str, object] = {}
        self._prefixes: list[tuple[str, object]] = []
        self.active = 0
        self.peak_active = 0
        self.connections = 0
        self.spans: list[tuple[float, float]] = []
        self.hits: dict[str, int] = {}
        self.requests: list[dict[str, str]] = []
        self._thread = threading.Thread(target=self._accept, name="wo02-lab", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._socket.getsockname()[1])

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"http://127.0.0.1:{self.port}{path}"

    def mount(self, path: str, handler) -> None:
        self._handlers[path] = handler

    def mount_prefix(self, prefix: str, handler) -> None:
        self._prefixes.append((prefix, handler))

    def wait_idle(self, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self.active == 0:
                    return
            time.sleep(0.02)

    def reset_stats(self) -> None:
        with self._lock:
            self.active = 0
            self.peak_active = 0
            self.connections = 0
            self.spans.clear()
            self.hits.clear()
            self.requests.clear()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "peak_active": self.peak_active,
                "connections": self.connections,
                "spans": list(self.spans),
                "hits": dict(self.hits),
            }

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                self._socket.settimeout(0.2)
                connection, _address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._client, args=(connection,), daemon=True).start()

    def _client(self, connection: socket.socket) -> None:
        with self._lock:
            self.connections += 1
        try:
            connection.settimeout(120)
            parsed = _read_request(connection)
            if parsed is None:
                return
            method, target, headers = parsed
            path = unquote(urlsplit(target).path)
            query = urlsplit(target).query
            with self._lock:
                self.hits[path] = self.hits.get(path, 0) + 1
                self.requests.append({"path": path, "query": query, **headers})
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
                start = time.perf_counter()
            reply: Reply | None = None
            try:
                reply = self._dispatch(path, query, headers)
                if reply.hold:
                    time.sleep(reply.hold)
                _send(connection, reply)
            finally:
                with self._lock:
                    self.active -= 1
                    self.spans.append((start, time.perf_counter()))
            if reply is not None and reply.truncate_to is not None:
                # The declared length is longer than the bytes sent. Half-close
                # so the client sees a short body instead of waiting.
                time.sleep(0.05)
                try:
                    connection.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
            elif reply is not None:
                # Wait until the client finishes the Content-Length read and
                # closes. Closing first resets the unread tail on Windows.
                connection.settimeout(30)
                try:
                    while connection.recv(65536):
                        pass
                except OSError:
                    pass
        except OSError:
            return
        finally:
            try:
                connection.close()
            except OSError:
                return

    def _dispatch(self, path: str, query: str, headers: dict[str, str]) -> Reply:
        handler = self._handlers.get(path)
        if handler is None:
            for prefix, candidate in self._prefixes:
                if path.startswith(prefix):
                    handler = candidate
                    break
        if handler is None:
            return Reply(404, b"missing", {"Content-Type": "text/plain"}, reason="Not Found")
        reply = handler(path, query, headers)
        if not isinstance(reply, Reply):
            raise TypeError("lab handler must return Reply")
        return reply

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self._socket.close()
        except OSError:
            return


def _read_request(connection: socket.socket) -> tuple[str, str, dict[str, str]] | None:
    raw = b""
    while b"\r\n\r\n" not in raw and len(raw) < 65536:
        chunk = connection.recv(4096)
        if not chunk:
            return None
        raw += chunk
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin1", errors="replace")
    lines = head.split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return parts[0], parts[1], headers


def _send(connection: socket.socket, reply: Reply) -> None:
    body = reply.body if reply.truncate_to is None else reply.body[: reply.truncate_to]
    declared = len(reply.body) if reply.truncate_to is not None else len(body)
    reason = reply.reason or _reason(reply.status)
    extra = "".join(f"{key}: {value}\r\n" for key, value in reply.headers.items() if key.lower() != "content-length")
    head = (
        f"HTTP/1.1 {reply.status} {reason}\r\n"
        f"Content-Length: {declared}\r\n"
        "Connection: close\r\n"
        f"{extra}\r\n"
    )
    connection.sendall(head.encode("latin1"))
    if reply.trickle <= 0 or not body:
        connection.sendall(body)
        return
    step = max(1, min(1024, len(body) // 8 or 1))
    for offset in range(0, len(body), step):
        time.sleep(reply.trickle)
        connection.sendall(body[offset : offset + step])


def _reason(status: int) -> str:
    return {
        200: "OK",
        206: "Partial Content",
        302: "Found",
        400: "Bad Request",
        401: "Unauthorized",
        404: "Not Found",
        429: "Too Many Requests",
        500: "Error",
        503: "Unavailable",
    }.get(status, "OK")


def overlaps(spans: list[tuple[float, float]]) -> bool:
    ordered = sorted(spans)
    for index, (start, end) in enumerate(ordered):
        for other_start, other_end in ordered[index + 1 :]:
            if other_start < end and start < other_end:
                return True
    return False
