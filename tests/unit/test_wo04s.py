"""WO-04-S. Cookie scope, proxy cap, and the Windows socket-close guard."""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from umd.auth.session import SessionStore, persistent_sessions_enabled
from umd.download.engine import (
    _is_proactor_shutdown_10022,
    install_windows_socket_close,
    shutdown_10022_events,
)
from umd.net.policy_proxy import PolicyProxy


def test_cookie_scope_expiry_and_leftover_files(tmp_path: Path):
    root = tmp_path / "sessions"
    orphan = root / "left.example"
    orphan.mkdir(parents=True)
    (orphan / "state.json").write_text("{}", encoding="utf-8")
    store = SessionStore(root)
    assert persistent_sessions_enabled() is False
    assert not orphan.exists()
    store.save(
        "files.example",
        {
            "cookies": [
                {
                    "name": "a",
                    "value": "1",
                    "domain": "files.example",
                    "path": "/media",
                    "secure": True,
                    "expires": time.time() + 60,
                },
                {
                    "name": "b",
                    "value": "2",
                    "domain": "files.example",
                    "path": "/media",
                    "secure": False,
                    "expires": time.time() - 5,
                },
                {
                    "name": "z",
                    "value": "9",
                    "domain": "files.example",
                    "path": "/",
                    "secure": False,
                    "expires": 0,
                },
                {
                    "name": "c",
                    "value": "3",
                    "domain": "other.example",
                    "path": "/",
                    "secure": False,
                },
            ]
        },
        expires_at=time.time() + 60,
    )
    assert store.cookie_header("http://files.example/media/a.png") == ""
    assert store.cookie_header("https://files.example/media/a.png") == "a=1"
    assert "z=9" not in store.cookie_header("https://files.example/")
    assert store.cookie_header("https://files.example/other.png") == ""
    assert store.cookie_header("https://other.example/") == ""
    listing = subprocess.check_output(["icacls", str(root / "files.example")])
    assert os.environ["USERNAME"].encode("mbcs") in listing
    assert b"(OI)(CI)(F)" in listing
    saved = (root / "files.example" / "state.json").read_text(encoding="utf-8")
    assert "other.example" not in saved
    store.delete("files.example")
    assert not (root / "files.example").exists()
    library = tmp_path / "library.sqlite"
    library.write_bytes(b"")
    assert b"a=1" not in library.read_bytes()


def test_expired_store_is_removed_on_the_next_open(tmp_path: Path):
    root = tmp_path / "sessions"
    store = SessionStore(root)
    store.save("gone.example", {"cookies": []}, expires_at=time.time() - 1)
    (root / "gone.example").mkdir(exist_ok=True)
    (root / "gone.example" / "state.json").write_text('{"cookies":[]}', encoding="utf-8")
    (root / "gone.example" / "expires").write_text(str(time.time() - 1), encoding="ascii")
    again = SessionStore(root)
    assert not (root / "gone.example").exists()
    assert again.cookie_header("https://gone.example/") == ""


def test_proxy_cap_and_rebinding_do_not_open_extra_targets():
    held = threading.Event()
    release = threading.Event()

    def blocking(address, timeout=None):
        held.set()
        release.wait(2)
        raise TimeoutError("stop")

    proxy = PolicyProxy("public", resolver=lambda _host, _port: ["93.184.216.34"], tunnel_limit=1)
    proxy._connect = blocking
    first = socket.create_connection(("127.0.0.1", proxy.port), timeout=2)
    first.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
    assert held.wait(2)
    second = socket.create_connection(("127.0.0.1", proxy.port), timeout=2)
    second.settimeout(2)
    try:
        second.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
    except OSError:
        pass
    try:
        refused = second.recv(300)
    except OSError:
        refused = b""
    release.set()
    first.close()
    second.close()
    proxy.close()
    assert b"403" in refused
    assert proxy.refused >= 1
    probe = socket.socket()
    try:
        probe.connect(("127.0.0.1", proxy.port))
        opened = True
    except OSError:
        opened = False
    finally:
        probe.close()
    assert opened is False

    def fail_connect(address, timeout=None):
        raise AssertionError(address)

    rebound = PolicyProxy("public", resolver=lambda _host, _port: ["93.184.216.34", "10.1.2.3"])
    rebound._connect = fail_connect
    client = socket.create_connection(("127.0.0.1", rebound.port), timeout=2)
    client.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
    body = client.recv(300)
    client.close()
    rebound.close()
    assert b"403" in body
    assert rebound.targets == []


def test_unrelated_winerror_10022_is_not_treated_as_shutdown():
    install_windows_socket_close()

    class Protocol:
        def connection_lost(self, exc):
            return None

    class _ShutdownSocket(socket.socket):
        def shutdown(self, how):
            raise OSError(22, "An invalid argument was supplied", None, 10022)

    class Transport:
        _called_connection_lost = False
        _server = None

        def __init__(self, sock) -> None:
            self._sock = sock
            self._protocol = Protocol()

    from asyncio.proactor_events import _ProactorBasePipeTransport

    invalid = _ShutdownSocket(socket.AF_INET, socket.SOCK_STREAM)
    invalid.bind(("127.0.0.1", 0))
    before = len(shutdown_10022_events)
    _ProactorBasePipeTransport._call_connection_lost(Transport(invalid), None)
    assert invalid.fileno() == -1
    assert len(shutdown_10022_events) == before + 1

    other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    other.bind(("127.0.0.1", 0))
    try:
        _ProactorBasePipeTransport._call_connection_lost(Transport(other), None)
        raised = False
    except OSError as exc:
        raised = getattr(exc, "winerror", None) == 10057
    assert raised is True
    assert other.fileno() == -1
    assert len(shutdown_10022_events) == before + 1

    try:
        raise OSError(0, "not a shutdown")
    except OSError as exc:
        exc.winerror = 10022
        assert _is_proactor_shutdown_10022(exc) is False
