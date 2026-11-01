"""Temporary, site-separated browser sessions.

The default store is a temp directory that disappears with the process.
Cookies are not written to SQLite and there is no Windows credential store
until one has been verified. A header is attached only when the URL host is
the site that owns the session.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit

_ACTIVE: "SessionStore | None" = None


def set_active(store: "SessionStore | None") -> None:
    global _ACTIVE
    _ACTIVE = store


def active() -> "SessionStore | None":
    return _ACTIVE


def cookie_header(url: str, store: "SessionStore | None" = None) -> str:
    chosen = active() if store is None else store
    if chosen is None:
        return ""
    return chosen.cookie_header(url)


def request_headers(url: str, store: "SessionStore | None" = None) -> dict[str, str]:
    """Headers shared by a thumbnail fetch and the file save."""

    from umd.netpolicy import USER_AGENT

    headers = {"User-Agent": USER_AGENT}
    cookie = cookie_header(url, store)
    if cookie:
        headers["Cookie"] = cookie
    return headers


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.reauth: list[str] = []

    def save(self, host: str, state: dict, *, expires_at: float) -> None:
        directory = self._dir(host)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
        safe = _state_for_host(host, state)
        (directory / "state.json").write_text(json.dumps(safe), encoding="utf-8")
        (directory / "expires").write_text(str(expires_at), encoding="ascii")

    def load(self, host: str) -> dict | None:
        directory = self._dir(host)
        expires = directory / "expires"
        state = directory / "state.json"
        if not expires.is_file() or not state.is_file():
            return None
        try:
            deadline = float(expires.read_text(encoding="ascii"))
        except ValueError:
            self.reauth.append(host)
            return None
        if deadline <= time.time():
            self.reauth.append(host)
            return None
        return json.loads(state.read_text(encoding="utf-8"))

    def cookie_header(self, url: str) -> str:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        if not host:
            return ""
        state = self.load(host)
        if not state:
            return ""
        pairs = []
        for cookie in state.get("cookies") or []:
            domain = str(cookie.get("domain") or "").lstrip(".").lower()
            if domain != host:
                continue
            name = str(cookie.get("name") or "")
            value = str(cookie.get("value") or "")
            if name:
                pairs.append(f"{name}={value}")
        return "; ".join(pairs)

    def delete(self, host: str) -> None:
        directory = self._dir(host)
        if directory.exists():
            shutil.rmtree(directory)

    def _dir(self, host: str) -> Path:
        cleaned = (host or "").strip().lower().rstrip(".")
        safe = "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in cleaned) or "site"
        return self.root / safe


def _state_for_host(host: str, state: dict) -> dict:
    kept = []
    for cookie in state.get("cookies") or []:
        domain = str(cookie.get("domain") or host).lstrip(".").lower()
        if domain != host.lower().rstrip("."):
            continue
        kept.append(
            {
                "name": str(cookie.get("name") or ""),
                "value": str(cookie.get("value") or ""),
                "domain": domain,
                "path": str(cookie.get("path") or "/"),
            }
        )
    return {"cookies": kept}
