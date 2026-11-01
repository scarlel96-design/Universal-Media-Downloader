"""Local proxy that applies the access policy to every browser request.

Chromium is told to use this proxy, including loopback, so a page and its
subresources share one decision. The TCP connection uses the checked address.
A path that cannot reach this proxy stays disabled.
"""

from __future__ import annotations

import select
import socket
import threading
import time
from urllib.parse import urlsplit

from umd.netpolicy import PolicyError, assess_public_url


PROXY_TUNNEL_LIMIT = 16


class PolicyProxy:
    last_port = 0
    denied_all: list[str] = []

    def __init__(self, network_mode: str = "local", *, resolver=None, tunnel_limit: int = PROXY_TUNNEL_LIMIT) -> None:
        self.network_mode = network_mode
        self._resolver = resolver
        self._connect = socket.create_connection
        self.denied: list[str] = []
        self.targets: list[tuple[str, int]] = []
        self.hosts: list[str] = []
        self.refused = 0
        self._slots = threading.Semaphore(max(1, int(tunnel_limit)))
        self._stop = threading.Event()
        self._clients: list[threading.Thread] = []
        self._open: list[socket.socket] = []
        self._socket = socket.create_server(("127.0.0.1", 0), backlog=64)
        self.port = int(self._socket.getsockname()[1])
        self._thread = threading.Thread(target=self._accept, name="umd-policy-proxy", daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        PolicyProxy.last_port = self.port
        self._stop.set()
        try:
            self._socket.close()
        except OSError:
            pass
        for sock in list(self._open):
            try:
                sock.close()
            except OSError:
                pass
        self._thread.join(timeout=2)
        for thread in list(self._clients):
            thread.join(timeout=1)

    def pin_for(self, host: str, port: int) -> str:
        cleaned = host.strip("[]").lower().rstrip(".")
        if not cleaned:
            raise PolicyError("허용되지 않은 주소입니다")
        if self.network_mode != "public":
            if cleaned in {"127.0.0.1", "localhost"} and port != self.port:
                return "127.0.0.1"
            self.denied.append(cleaned)
            PolicyProxy.denied_all.append(cleaned)
            raise PolicyError("내부 네트워크 주소입니다")
        if ":" in cleaned:
            probe = f"http://[{cleaned}]:{port}/"
        else:
            probe = f"http://{cleaned}:{port}/"
        decision = assess_public_url(probe, resolver=self._resolver)
        if not decision.allowed or not decision.pin:
            self.denied.append(cleaned)
            PolicyProxy.denied_all.append(cleaned)
            raise PolicyError(decision.message or "허용되지 않은 주소입니다")
        return decision.pin

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                self._socket.settimeout(0.2)
                client, _address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            if not self._slots.acquire(blocking=False):
                self.refused += 1
                # Windows aborts the socket when close() runs with unread
                # bytes, which drops the 403. Read the request first.
                _drain(client)
                _reject(client, "연결 수가 한도를 넘었습니다")
                _close_socket(client)
                continue
            self._open.append(client)
            thread = threading.Thread(target=self._client, args=(client,), daemon=True)
            self._clients.append(thread)
            thread.start()

    def _client(self, client: socket.socket) -> None:
        remote: socket.socket | None = None
        try:
            client.settimeout(15)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 65536:
                chunk = client.recv(4096)
                if not chunk:
                    return
                data += chunk
            head, rest = data.split(b"\r\n\r\n", 1)
            lines = head.decode("iso-8859-1", errors="replace").split("\r\n")
            method, target, version = lines[0].split(" ", 2)
            if method.upper() == "CONNECT":
                host, port = _host_port(target, 443)
                pin = self.pin_for(host, port)
                self.hosts.append(host)
                self.targets.append((pin, port))
                remote = self._connect((pin, port), timeout=10)
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                if rest:
                    remote.sendall(rest)
                _tunnel(client, remote)
                return
            parts = urlsplit(target)
            host = parts.hostname or ""
            port = parts.port or (443 if parts.scheme == "https" else 80)
            pin = self.pin_for(host, port)
            self.hosts.append(host.lower())
            self.targets.append((pin, port))
            remote = self._connect((pin, port), timeout=10)
            path = parts.path or "/"
            if parts.query:
                path = f"{path}?{parts.query}"
            rebuilt = [f"{method} {path} {version}", *lines[1:], "", ""]
            remote.sendall("\r\n".join(rebuilt).encode("iso-8859-1", errors="replace") + rest)
            _tunnel(client, remote)
        except PolicyError as exc:
            _reject(client, str(exc))
        except Exception:
            _reject(client, "연결할 수 없습니다")
        finally:
            for sock in (remote, client):
                if sock is None:
                    continue
                _close_socket(sock)
            if client in self._open:
                self._open.remove(client)
            self._slots.release()


def _host_port(target: str, default: int) -> tuple[str, int]:
    if target.startswith("["):
        host, _, port = target[1:].partition("]")
        number = port[1:] if port.startswith(":") else ""
        return host, int(number or default)
    host, separator, port = target.rpartition(":")
    if separator and port.isdigit():
        return host, int(port)
    return target, default


def _drain(client: socket.socket) -> None:
    try:
        client.settimeout(0.5)
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
    except OSError:
        pass


def _close_socket(client: socket.socket) -> None:
    """Let the peer read the response, then close.

    Closing with unread bytes, or closing before the 403 is acknowledged,
    makes Windows reset the socket and drop the response.
    """

    try:
        client.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    # A blocking read here deadlocks Chromium: it waits for this socket
    # while this thread waits for Chromium to close it.
    time.sleep(0.05)
    try:
        client.close()
    except OSError:
        pass


def _reject(client: socket.socket, message: str) -> None:
    body = message.encode("utf-8", errors="replace")
    try:
        client.sendall(
            b"HTTP/1.1 403 Forbidden\r\nContent-Length: "
            + str(len(body)).encode("ascii")
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
    except OSError:
        pass


def _tunnel(left: socket.socket, right: socket.socket) -> None:
    left.settimeout(None)
    right.settimeout(None)
    sockets = [left, right]
    while sockets:
        readable, _, _ = select.select(sockets, [], [], 20)
        if not readable:
            return
        for sock in readable:
            try:
                chunk = sock.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            other = right if sock is left else left
            try:
                other.sendall(chunk)
            except OSError:
                return
