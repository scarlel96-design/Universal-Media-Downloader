"""WO-04A. The parent process does not swap its resolver for a child tool."""

from __future__ import annotations

import socket
import threading
import time

import httpcore
import pytest

from umd.download.pin import PinnedSyncBackend, empty_pins
from umd.net.isolated import call
from umd.netpolicy import ExtractError, assess_public_url


class _RecordingBackend(httpcore.NetworkBackend):
    def __init__(self) -> None:
        self.targets: list[str] = []

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.targets.append(host)
        return object()

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise AssertionError(path)

    def sleep(self, seconds: float) -> None:
        return None


def test_parent_resolves_loopback_while_the_child_guard_is_active():
    seen: list[list] = []
    errors: list[BaseException] = []

    def child() -> None:
        try:
            call("hold", {"seconds": 0.6, "host": "127.0.0.1", "port": 9})
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=child)
    thread.start()
    time.sleep(0.15)
    seen.append(socket.getaddrinfo("127.0.0.1", 9))
    thread.join(timeout=5)
    assert thread.is_alive() is False
    assert seen[0]
    assert errors
    assert "내부 네트워크" in str(errors[0])
    assert isinstance(errors[0], ExtractError)
    assert socket.getaddrinfo("127.0.0.1", 9)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://10.1.2.3/a",
        "http://169.254.169.254/latest",
        "http://[::1]/a",
        "http://192.168.0.8/a",
    ],
)
def test_internal_addresses_stay_blocked(url: str):
    decision = assess_public_url(url)
    assert decision.allowed is False
    assert decision.pin == ""
    assert decision.message == "내부 네트워크 주소입니다"


def test_a_private_answer_on_re_resolution_drops_the_pin():
    first = assess_public_url("https://example.com/a", resolver=lambda _host, _port: ["93.184.216.34"])
    assert first.allowed is True
    assert first.pin == "93.184.216.34"
    second = assess_public_url(
        "https://example.com/a",
        resolver=lambda _host, _port: ["93.184.216.34", "10.0.0.8"],
    )
    assert second.allowed is False
    assert second.pin == ""
    assert second.message == "내부 네트워크 주소입니다"


def test_tcp_connects_to_the_pinned_address_for_v4_and_v6():
    table = empty_pins()
    table.remember("example.com", 443, "93.184.216.34")
    table.remember("v6.example.com", 443, "2606:4700:4700::1111")
    inner = _RecordingBackend()
    backend = PinnedSyncBackend(inner, table)
    backend.connect_tcp("example.com", 443, timeout=1)
    backend.connect_tcp("v6.example.com", 443, timeout=1)
    assert inner.targets == ["93.184.216.34", "2606:4700:4700::1111"]
    with pytest.raises(httpcore.ConnectError, match="확인되지 않았습니다"):
        backend.connect_tcp("unknown.example", 443, timeout=1)
