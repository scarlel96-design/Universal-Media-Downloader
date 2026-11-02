"""Temporary, site-separated browser sessions.

The default store is a temp directory. Cookies are not written to SQLite.
Windows credential storage stays off until that store has been verified.
A cookie is sent only when its domain, path, Secure flag, and expiry all
match the request. One site's jar is never attached to another host.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

_ACTIVE: "SessionStore | None" = None


def persistent_sessions_enabled() -> bool:
    """The Windows credential store has not been verified."""

    return False


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


class SessionProtectError(RuntimeError):
    """Raised when a session jar cannot be limited to the current user."""


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.reauth: list[str] = []
        self.sweep()

    def save(self, host: str, state: dict, *, expires_at: float) -> None:
        directory = self._dir(host)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
        safe = _state_for_host(host, state)
        (directory / "state.json").write_text(json.dumps(safe), encoding="utf-8")
        (directory / "expires").write_text(str(expires_at), encoding="ascii")
        if _restrict(directory):
            return
        shutil.rmtree(directory, ignore_errors=True)
        raise SessionProtectError("세션을 보호하지 못해 저장하지 않았습니다")

    def load(self, host: str) -> dict | None:
        directory = self._dir(host)
        expires = directory / "expires"
        state = directory / "state.json"
        if not expires.is_file() or not state.is_file():
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
            return None
        try:
            deadline = float(expires.read_text(encoding="ascii"))
        except ValueError:
            self.reauth.append(host)
            shutil.rmtree(directory, ignore_errors=True)
            return None
        if deadline <= time.time():
            self.reauth.append(host)
            shutil.rmtree(directory, ignore_errors=True)
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
            if not _cookie_matches(cookie, parts):
                continue
            name = str(cookie.get("name") or "")
            value = str(cookie.get("value") or "")
            if name:
                pairs.append(f"{name}={value}")
        return "; ".join(pairs)

    def sweep(self) -> None:
        """Remove jars left behind after a crash or an expired session."""

        if not self.root.is_dir():
            return
        now = time.time()
        for child in list(self.root.iterdir()):
            if not child.is_dir():
                continue
            expires = child / "expires"
            state = child / "state.json"
            if not expires.is_file() or not state.is_file():
                shutil.rmtree(child, ignore_errors=True)
                continue
            try:
                deadline = float(expires.read_text(encoding="ascii"))
            except ValueError:
                shutil.rmtree(child, ignore_errors=True)
                continue
            if deadline <= now:
                shutil.rmtree(child, ignore_errors=True)

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
        domain = str(cookie.get("domain") or host).lstrip(".").lower().rstrip(".")
        if domain != host.lower().rstrip("."):
            continue
        path = str(cookie.get("path") or "/")
        if not path.startswith("/"):
            path = "/"
        expires = cookie.get("expires")
        try:
            expires_value = float(expires) if expires is not None else -1.0
        except (TypeError, ValueError):
            expires_value = -1.0
        kept.append(
            {
                "name": str(cookie.get("name") or ""),
                "value": str(cookie.get("value") or ""),
                "domain": domain,
                "path": path,
                "secure": bool(cookie.get("secure")),
                "expires": expires_value,
            }
        )
    return {"cookies": kept}


def _cookie_matches(cookie: dict, parts) -> bool:
    host = (parts.hostname or "").lower().rstrip(".")
    domain = str(cookie.get("domain") or "").lstrip(".").lower().rstrip(".")
    if not host or domain != host:
        return False
    if bool(cookie.get("secure")) and parts.scheme != "https":
        return False
    if not _path_matches(str(cookie.get("path") or "/"), parts.path or "/"):
        return False
    try:
        expires = float(cookie.get("expires") if cookie.get("expires") is not None else -1)
    except (TypeError, ValueError):
        return False
    # -1 is the session-cookie sentinel. Zero and any past timestamp are expired.
    if expires != -1 and expires <= time.time():
        return False
    return True


def _path_matches(cookie_path: str, request_path: str) -> bool:
    if not cookie_path.startswith("/"):
        cookie_path = "/"
    if not request_path.startswith("/"):
        request_path = "/" + request_path
    if request_path == cookie_path:
        return True
    if not request_path.startswith(cookie_path):
        return False
    if cookie_path.endswith("/"):
        return True
    return len(request_path) > len(cookie_path) and request_path[len(cookie_path)] == "/"


def _restrict(directory: Path) -> bool:
    """Limit the jar to the current user. False means the caller must delete it."""

    if os.name != "nt":
        try:
            os.chmod(directory, 0o700)
        except OSError:
            return False
        return True
    user = os.environ.get("USERNAME")
    if not user:
        return False
    grant = subprocess.run(
        ["icacls", str(directory), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    if grant.returncode != 0:
        return False
    shown = subprocess.run(
        ["icacls", str(directory)],
        capture_output=True,
        timeout=10,
        check=False,
    )
    if shown.returncode != 0:
        return False
    try:
        encoded = user.encode("mbcs")
    except LookupError:
        encoded = user.encode()
    blob = shown.stdout or b""
    return encoded in blob and b"(OI)(CI)(F)" in blob
