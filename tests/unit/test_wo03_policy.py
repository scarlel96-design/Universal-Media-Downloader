"""Public URL checks. Local mode stays limited to loopback fixtures."""

import socket

import pytest

from umd.netpolicy import (
    assess_public_url,
    is_allowed_url,
    is_public_ip,
    public_resolution,
)


def _public(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


def test_local_mode_still_rejects_public_urls():
    assert is_allowed_url("http://127.0.0.1/a") is True
    assert is_allowed_url("http://localhost/a") is True
    assert is_allowed_url("https://example.com/a") is False
    assert is_allowed_url("file:///C:/fixture.html") is True


def test_public_mode_accepts_only_http_and_a_public_address():
    allowed = assess_public_url("https://example.com/a", resolver=_public)
    assert allowed.allowed is True
    assert allowed.pin == "93.184.216.34"
    assert allowed.safe_url == "https://example.com/a"
    blocked = assess_public_url("ftp://example.com/a", resolver=_public)
    assert blocked.allowed is False
    assert blocked.message == "지원하지 않는 프로토콜입니다"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "http://10.1.2.3/a",
        "http://172.16.0.1/a",
        "http://192.168.1.1/a",
        "http://169.254.169.254/latest",
        "http://100.64.0.1/a",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://[fe80::1]/",
        "http://localhost/a",
        "http://printer.local/a",
        "http://metadata.google.internal/",
        "http://0177.0.0.1/",
        "http://2130706433/",
    ],
)
def test_internal_and_obfuscated_addresses_are_blocked(url: str):
    decision = assess_public_url(url, resolver=_public)
    assert decision.allowed is False
    assert decision.message == "내부 네트워크 주소입니다"
    assert "s3cret" not in decision.message


def test_any_private_dns_answer_blocks_the_name():
    decision = assess_public_url(
        "https://example.com/a",
        resolver=lambda _host, _port: ["93.184.216.34", "10.0.0.8"],
    )
    assert decision.allowed is False
    assert decision.pin == ""
    assert decision.message == "내부 네트워크 주소입니다"


def test_dns_failure_is_not_an_internal_block():
    def explode(_host: str, _port: int) -> list[str]:
        raise OSError("no such host")

    decision = assess_public_url("https://example.com/a", resolver=explode)
    assert decision.kind == "dns"
    assert decision.message == "주소를 찾지 못했습니다"


def test_userinfo_is_removed_before_the_decision_is_shown():
    decision = assess_public_url(
        "http://user:s3cret-token@example.com/a",
        resolver=lambda _host, _port: ["10.0.0.1"],
    )
    assert decision.allowed is False
    assert "s3cret-token" not in decision.message
    assert "s3cret-token" not in decision.safe_url


def test_resolution_guard_blocks_loopback_and_restores_the_socket():
    with public_resolution():
        with pytest.raises(OSError):
            socket.getaddrinfo("127.0.0.1", 80)
    resolved = socket.getaddrinfo("127.0.0.1", 9)
    assert resolved


@pytest.mark.parametrize(
    "value",
    ["8.8.8.8", "1.1.1.1", "93.184.216.34"],
)
def test_known_public_addresses_pass(value: str):
    assert is_public_ip(value) is True
