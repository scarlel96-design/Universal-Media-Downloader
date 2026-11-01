"""Which URLs this stage is allowed to fetch.

WO-01 talks only to local fixtures. Public sites, proxies, and Tor are out of scope.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})


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
