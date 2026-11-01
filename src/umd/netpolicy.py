"""Which URLs this stage is allowed to fetch.

Local mode talks only to local fixtures. Public mode is a separate HTTP/HTTPS
check: non-HTTP schemes and internal addresses are refused, and every resolved
address must be public before a connection is pinned to one of those addresses.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

USER_AGENT = (
    "UniversalMediaDownloader/0.1 "
    "(https://github.com/scarlel96-design/Universal-Media-Downloader)"
)
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.internal",
    }
)
_BLOCKED_SUFFIXES = (
    ".local",
    ".localhost",
    ".internal",
    ".lan",
    ".home",
    ".localdomain",
    ".intranet",
)
_CGNAT = ipaddress.ip_network("100.64.0.0/10")

Resolver = Callable[[str, int], list[str]]


class AccessError(Exception):
    kind = "policy"


class PolicyError(AccessError):
    kind = "policy"


class DnsError(AccessError):
    kind = "dns"


class AuthError(AccessError):
    kind = "auth"


class HttpAccessError(AccessError):
    kind = "http"


class ExtractError(AccessError):
    kind = "extract"


def is_allowed_url(url: str) -> bool:
    parts = urlsplit(url.strip())
    if parts.scheme == "file":
        return bool(parts.path)
    if parts.scheme in {"http", "https"}:
        return (parts.hostname or "").lower() in _LOCAL_HOSTS
    return False


def strip_userinfo(url: str) -> str:
    """Drop userinfo and fragments so requests and errors cannot carry secrets."""
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    if parts.scheme == "file":
        return urlunsplit((parts.scheme, "", parts.path, "", ""))
    return urlunsplit((parts.scheme, host, parts.path, parts.query, ""))


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.version == 4 and ip in _CGNAT:
        return False
    return bool(getattr(ip, "is_global", False))


@dataclass(frozen=True)
class UrlDecision:
    allowed: bool
    message: str
    kind: str
    safe_url: str
    host: str
    port: int
    addresses: tuple[str, ...]
    pin: str


def assess_public_url(url: str, *, resolver: Resolver | None = None) -> UrlDecision:
    """Decide whether a public-mode URL may be opened.

    A name is refused when any DNS answer is not a public address. The caller
    connects only to ``pin``, which is one of those checked addresses.
    """

    raw = url.strip()
    parts = urlsplit(raw)
    safe = strip_userinfo(raw)
    if parts.scheme not in {"http", "https"}:
        return _deny("지원하지 않는 프로토콜입니다", safe)
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or _blocked_name(host) or _obfuscated_ip(host):
        message = "내부 네트워크 주소입니다" if host else "허용되지 않은 주소입니다"
        return _deny(message, safe)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    literal = _literal_ip(host)
    try:
        if literal is not None:
            addresses = [str(literal)]
        else:
            addresses = [str(item) for item in (resolver or _default_resolver)(host, port)]
    except OSError:
        return _deny("주소를 찾지 못했습니다", safe, kind="dns")
    if not addresses:
        return _deny("주소를 찾지 못했습니다", safe, kind="dns")
    normalized: list[str] = []
    for item in addresses:
        text = item.split("%", 1)[0]
        if not is_public_ip(text):
            return _deny("내부 네트워크 주소입니다", safe)
        normalized.append(text)
    normalized.sort(key=lambda item: ipaddress.ip_address(item).version)
    return UrlDecision(True, "", "ok", safe, host, port, tuple(normalized), normalized[0])


def require_public(url: str) -> UrlDecision:
    """Raise when a public-mode URL is not an HTTP(S) address on the public internet."""

    decision = assess_public_url(url)
    if not decision.allowed:
        if decision.kind == "dns":
            raise DnsError(decision.message)
        raise PolicyError(decision.message or "허용되지 않은 주소입니다")
    return decision


def pin_keys(host: str, port: int) -> tuple[tuple[str, int], ...]:
    cleaned = host.lower().rstrip(".")
    keys = [(cleaned, int(port))]
    try:
        puny = cleaned.encode("idna").decode("ascii")
    except UnicodeError:
        puny = cleaned
    if puny != cleaned:
        keys.append((puny, int(port)))
    return tuple(keys)


def _deny(message: str, safe: str, *, kind: str = "policy") -> UrlDecision:
    return UrlDecision(False, message, kind, safe, "", 0, (), "")


def _blocked_name(host: str) -> bool:
    if host in _BLOCKED_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES)


def _obfuscated_ip(host: str) -> bool:
    if host.isdigit() or host.lower().startswith("0x"):
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return any(len(part) > 1 and part.startswith("0") for part in parts)
    return False


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


_real_getaddrinfo = socket.getaddrinfo


def _default_resolver(host: str, port: int) -> list[str]:
    infos = _real_getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    found: list[str] = []
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        if address not in found:
            found.append(address)
    return found


_guard_lock = threading.Lock()
_guard_depth = 0


def _guarded_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
    decision = _assess_host_raw(str(host), int(port or 0))
    if not decision.allowed:
        raise OSError(decision.message)
    results = []
    for ip in decision.addresses:
        parsed = ipaddress.ip_address(ip)
        fam = socket.AF_INET if parsed.version == 4 else socket.AF_INET6
        if family not in (0, socket.AF_UNSPEC) and family != fam:
            continue
        sockaddr = (ip, int(port or 0), 0, 0) if parsed.version == 6 else (ip, int(port or 0))
        results.append((fam, socket.SOCK_STREAM, proto or 0, "", sockaddr))
    return results


def _assess_host_raw(host: str, port: int) -> UrlDecision:
    """Resolve ``host`` without putting it back through URL parsing.

    IPv6 literals contain colons, so they cannot be re-encoded as a naive
    ``http://host/`` URL. Callers that already have a hostname use this path.
    """

    cleaned = host.strip().strip("[]").lower().rstrip(".")
    probe = "80" if port <= 0 else str(port)
    safe = f"{cleaned}:{probe}" if cleaned else ""
    if not cleaned or _blocked_name(cleaned) or _obfuscated_ip(cleaned):
        message = "내부 네트워크 주소입니다" if cleaned else "허용되지 않은 주소입니다"
        return _deny(message, safe)
    literal = _literal_ip(cleaned)
    try:
        if literal is not None:
            addresses = [str(literal)]
        else:
            addresses = _default_resolver(cleaned, port or 80)
    except OSError:
        return _deny("주소를 찾지 못했습니다", safe, kind="dns")
    if not addresses:
        return _deny("주소를 찾지 못했습니다", safe, kind="dns")
    normalized: list[str] = []
    for item in addresses:
        text = item.split("%", 1)[0]
        if not is_public_ip(text):
            return _deny("내부 네트워크 주소입니다", safe)
        normalized.append(text)
    normalized.sort(key=lambda item: ipaddress.ip_address(item).version)
    return UrlDecision(True, "", "ok", safe, cleaned, port or 80, tuple(normalized), normalized[0])


@contextmanager
def public_resolution():
    """Force later DNS lookups through the public-address check.

    yt-dlp and gallery-dl open their own sockets. While this context is
    active, those lookups return only addresses that passed the same check,
    and a private answer fails the lookup instead of being connected.
    """

    global _guard_depth
    with _guard_lock:
        if _guard_depth == 0:
            socket.getaddrinfo = _guarded_getaddrinfo
        _guard_depth += 1
    try:
        yield
    finally:
        with _guard_lock:
            _guard_depth -= 1
            if _guard_depth == 0:
                socket.getaddrinfo = _real_getaddrinfo
