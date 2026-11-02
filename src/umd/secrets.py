"""Protected references for signed URLs.

SQLite stores a URL with its userinfo, query, and fragment removed. The
original stays in a directory that is restricted to the current user before
any secret file is created. A reference id is opaque: it is not the URL, a
cookie, or an authorization value.
"""

from __future__ import annotations

import heapq
import json
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

_URL = re.compile(r"https?://[^\s\"'<>]+", re.I)
_HEADER = re.compile(r"(?i)\b(authorization|cookie)\b\s*[:=]\s*\S+")
_REF = re.compile(r"umdref://([0-9a-f]{32})\b")
_REF_NAME = re.compile(r"^[0-9a-f]{32}$")
_OUTBOUND_TTL = 3600
_SWEEP_LIMIT = 64
_CURSOR_NAME = ".umd-sweep-cursor"
_CURSOR_TEXT = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_ACTIVE: "SecretVault | None" = None
_DEFAULT: "SecretVault | None" = None
_log = logging.getLogger("umd.secrets")


class ProtectError(RuntimeError):
    """Raised when a secret directory cannot be limited to the current user."""


class SecretUnavailable(RuntimeError):
    """Raised when a protected reference cannot be read."""


def activate(vault: "SecretVault | None") -> None:
    global _ACTIVE
    _ACTIVE = vault


def active_vault() -> "SecretVault | None":
    return _ACTIVE


def default_vault() -> "SecretVault":
    global _DEFAULT
    if _DEFAULT is None:
        root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "umd-secret-vault"
        _DEFAULT = SecretVault(root)
    return _DEFAULT


def has_secret_url(value: str) -> bool:
    text = value.strip()
    if not text.lower().startswith(("http://", "https://")):
        return False
    parts = urlsplit(text)
    return bool(parts.username or parts.password or parts.query or parts.fragment)


def redact_url(value: str) -> str:
    """Drop userinfo, query, and fragment. The path stays so the row is recognizable."""

    text = value.strip()
    if not text.lower().startswith(("http://", "https://")):
        return value
    parts = urlsplit(text)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme.lower(), host, parts.path, "", ""))


def scrub_text(value: str, secrets: list[str] | None = None) -> str:
    """Remove signed URLs and known secret strings. Failure returns a fixed message."""

    if not value:
        return value
    try:
        text = value
        for secret in sorted({item for item in (secrets or []) if item}, key=len, reverse=True):
            if secret.lower().startswith(("http://", "https://")):
                text = text.replace(secret, redact_url(secret))
            else:
                text = text.replace(secret, "")
        text = _HEADER.sub(r"\1", text)
        text = _URL.sub(lambda match: redact_url(match.group(0)), text)
    except Exception:
        return "내용을 보호하지 못했습니다"
    for secret in secrets or []:
        if secret and secret in text:
            return "내용을 보호하지 못했습니다"
    return text


def collect_secrets(value: object) -> list[str]:
    found: list[str] = []

    def walk(item: object, key: str = "") -> None:
        if isinstance(item, str):
            if has_secret_url(item):
                found.append(item)
                parts = urlsplit(item.strip())
                if parts.password:
                    found.append(parts.password)
                if parts.username:
                    found.append(parts.username)
                if parts.query:
                    found.append(parts.query)
            if key.lower() in {"cookie", "authorization", "proxy-authorization"} and item:
                found.append(item)
            return
        if isinstance(item, dict):
            for name, child in item.items():
                walk(child, str(name))
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found


def is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    if os.name != "nt" or not path.exists():
        return False
    import ctypes

    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == -1 or attrs == 0xFFFFFFFF:
        return False
    return bool(attrs & 0x400)


def assert_no_reparse(path: Path) -> None:
    current = path
    while True:
        if current.exists() and is_reparse(current):
            raise ProtectError("세션을 보호하지 못해 저장하지 않았습니다")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _directory_is_empty(directory: Path) -> bool:
    try:
        next(directory.iterdir())
    except StopIteration:
        return True
    except OSError:
        return False
    return False


def protect_directory(directory: Path) -> None:
    """Create ``directory`` and verify its ACL before the caller writes a secret.

    A failed check removes only a directory this call created and left empty.
    An existing vault is not deleted, and no secret file is written.
    """

    assert_no_reparse(directory.parent)
    if directory.exists() and is_reparse(directory):
        raise ProtectError("세션을 보호하지 못해 저장하지 않았습니다")
    created = not directory.exists()
    directory.mkdir(parents=True, exist_ok=True)
    if is_reparse(directory):
        if created or _directory_is_empty(directory):
            shutil.rmtree(directory, ignore_errors=True)
        raise ProtectError("세션을 보호하지 못해 저장하지 않았습니다")
    from umd.auth.session import _restrict

    if _restrict(directory):
        return
    if created or _directory_is_empty(directory):
        shutil.rmtree(directory, ignore_errors=True)
    raise ProtectError("세션을 보호하지 못해 저장하지 않았습니다")


def write_private(directory: Path, name: str, text: str) -> None:
    """Write inside an already protected directory. ``.partial`` is not a live record."""

    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name) or name.startswith("."):
        raise ProtectError("세션을 보호하지 못해 저장하지 않았습니다")
    partial = directory / f".{name}.partial"
    final = directory / name
    try:
        partial.write_text(text, encoding="utf-8")
        os.replace(partial, final)
    except OSError:
        partial.unlink(missing_ok=True)
        raise
    finally:
        partial.unlink(missing_ok=True)


class _NameRank:
    __slots__ = ("name", "path")

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path

    def __lt__(self, other: "_NameRank") -> bool:
        return self.name > other.name


def _keep_smallest(heap: list[_NameRank], name: str, path: Path, limit: int) -> None:
    item = _NameRank(name, path)
    if len(heap) < limit:
        heapq.heappush(heap, item)
        return
    if name < heap[0].name:
        heapq.heapreplace(heap, item)


def _ascending(heap: list[_NameRank]) -> list[_NameRank]:
    return sorted(heap, key=lambda item: item.name)


def _dirent_skipped(entry: os.DirEntry) -> bool:
    """Skip symlinks, reparse points, and non-files without a second attribute lookup."""

    try:
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            return True
        if os.name == "nt":
            attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
            if int(attrs) & 0x400:
                return True
    except OSError:
        _log.info("outbound sweep skipped entry")
        return True
    return False


class SecretVault:
    def __init__(self, root: Path, *, clock=None) -> None:
        self.root = Path(root)
        self._clock = clock or time.time
        self._active: set[str] = set()
        self._sweep_lock = threading.Lock()
        self.sweep_stats = {"listed": 0, "opened": 0, "removed": 0}
        self.sweep_expired_outbound()

    def _now(self) -> float:
        return float(self._clock())

    def put(self, job_id: str, item_id: str, urls: dict[str, str]) -> str:
        secret = {key: value for key, value in urls.items() if value and has_secret_url(value)}
        if not secret:
            return ""
        protect_directory(self.root)
        ref = uuid4().hex
        payload = {
            "job_id": job_id,
            "item_id": item_id,
            "urls": secret,
            "expires_at": None,
        }
        write_private(self.root, f"{ref}.json", json.dumps(payload, ensure_ascii=False))
        return ref

    def put_outbound(self, url: str) -> str:
        self.sweep_expired_outbound()
        ref = uuid4().hex
        self._active.add(ref)
        protect_directory(self.root)
        payload = {
            "job_id": "outbound",
            "item_id": ref,
            "urls": {"value": url},
            "expires_at": self._now() + _OUTBOUND_TTL,
        }
        try:
            write_private(self.root, f"{ref}.json", json.dumps(payload, ensure_ascii=False))
        except Exception:
            self._active.discard(ref)
            raise
        self.sweep_expired_outbound()
        return ref

    def read(self, ref: str, *, job_id: str, item_id: str) -> dict[str, str]:
        path = self._path(ref)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SecretUnavailable("보호된 참조를 읽지 못했습니다") from exc
        except json.JSONDecodeError:
            raise SecretUnavailable("보호된 참조를 읽지 못했습니다") from None
        if data.get("job_id") != job_id or data.get("item_id") != item_id:
            raise SecretUnavailable("보호된 참조를 읽지 못했습니다")
        expires = data.get("expires_at")
        if expires is not None and float(expires) <= self._now():
            raise SecretUnavailable("보호된 참조가 만료되었습니다")
        urls = data.get("urls")
        if not isinstance(urls, dict):
            raise SecretUnavailable("보호된 참조를 읽지 못했습니다")
        return {str(key): str(value) for key, value in urls.items()}

    def drop(self, ref: str) -> None:
        if not ref or not _REF_NAME.fullmatch(ref):
            return
        try:
            path = self._path(ref)
        except SecretUnavailable:
            self._active.discard(ref)
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise
        self._active.discard(ref)

    def drop_many(self, refs: list[str]) -> None:
        for ref in refs:
            self.drop(ref)

    def sweep_expired_outbound(self) -> int:
        """Remove one bounded batch of expired outbound refs.

        Each call opens at most 64 files. The batch is the next 64 names in
        lexicographic order after the stored cursor, then wraps to the start.
        The cursor is only a filename. It is not a URL or a credential.
        """

        with self._sweep_lock:
            return self._sweep_expired_outbound()

    def _sweep_expired_outbound(self) -> int:
        self.sweep_stats = {"listed": 0, "opened": 0, "removed": 0}
        if not self.root.is_dir() or is_reparse(self.root):
            return 0
        cursor = self._read_cursor()
        try:
            batch = self._next_batch(cursor)
        except OSError:
            _log.info("outbound sweep skipped")
            return 0
        removed = 0
        for path in batch:
            self.sweep_stats["opened"] += 1
            try:
                if self._release_expired_outbound(path):
                    removed += 1
            except OSError:
                ref = path.stem if _REF_NAME.fullmatch(path.stem) else ""
                _log.info("outbound sweep kept %s", ref or "entry")
        self.sweep_stats["removed"] = removed
        if batch:
            if not self._write_cursor(batch[-1].name):
                _log.info("sweep cursor update failed")
        if removed:
            _log.info("outbound sweep removed %s", removed)
        return removed

    def _next_batch(self, cursor: str) -> list[Path]:
        after: list[_NameRank] = []
        before: list[_NameRank] = []
        with os.scandir(self.root) as entries:
            for entry in entries:
                self.sweep_stats["listed"] += 1
                name = entry.name
                if not name or name[0] == ".":
                    continue
                if _dirent_skipped(entry):
                    continue
                path = Path(entry.path)
                if cursor and name <= cursor:
                    _keep_smallest(before, name, path, _SWEEP_LIMIT)
                else:
                    _keep_smallest(after, name, path, _SWEEP_LIMIT)
        chosen = _ascending(after)
        if len(chosen) < _SWEEP_LIMIT:
            seen = {item.name for item in chosen}
            for item in _ascending(before):
                if item.name in seen:
                    continue
                chosen.append(item)
                if len(chosen) >= _SWEEP_LIMIT:
                    break
        return [item.path for item in chosen]

    def _read_cursor(self) -> str:
        path = self.root / _CURSOR_NAME
        try:
            if not path.is_file() or path.is_symlink() or is_reparse(path):
                return ""
            text = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            _log.info("sweep cursor reset")
            return ""
        if not _CURSOR_TEXT.fullmatch(text):
            _log.info("sweep cursor reset")
            return ""
        return text

    def _write_cursor(self, name: str) -> bool:
        if not _CURSOR_TEXT.fullmatch(name):
            _log.info("sweep cursor reset")
            return False
        path = self.root / _CURSOR_NAME
        partial = self.root / ".umd-sweep-cursor.partial"
        try:
            partial.write_text(name + "\n", encoding="utf-8")
            os.replace(partial, path)
        except OSError:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True

    def _release_expired_outbound(self, path: Path) -> bool:
        try:
            if not path.is_file() or path.is_symlink() or is_reparse(path):
                return False
            name = path.name
            if not name.endswith(".json"):
                return False
            ref = name[:-5]
            if not _REF_NAME.fullmatch(ref) or ref in self._active:
                return False
            root = self.root.resolve()
            resolved = path.resolve()
            if resolved.parent != root:
                return False
            data = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("job_id") != "outbound":
                return False
            expires = data.get("expires_at")
            if expires is None:
                return False
            deadline = float(expires)
        except (OSError, json.JSONDecodeError, UnicodeError, TypeError, ValueError):
            return False
        if self._now() < deadline:
            return False
        try:
            resolved.unlink()
        except FileNotFoundError:
            return False
        except OSError:
            _log.info("outbound sweep kept %s", ref)
            return False
        return True

    def _path(self, ref: str) -> Path:
        if not _REF_NAME.fullmatch(ref or ""):
            raise SecretUnavailable("보호된 참조를 읽지 못했습니다")
        root = self.root.resolve()
        path = (root / f"{ref}.json").resolve()
        if path.parent != root or is_reparse(path):
            raise SecretUnavailable("보호된 참조를 읽지 못했습니다")
        if not path.is_file():
            raise SecretUnavailable("보호된 참조를 읽지 못했습니다")
        return path


def seal_payload(payload: dict) -> tuple[dict, list[str], list[str]]:
    """Replace secret URLs with references. The returned strings are scrubbed from output."""

    vault = active_vault() or default_vault()
    secrets = collect_secrets(payload)
    outbound_refs: list[str] = []

    def walk(value: object, key: str = "") -> object:
        if isinstance(value, str):
            if has_secret_url(value):
                ref = vault.put_outbound(value)
                outbound_refs.append(ref)
                return f"umdref://{ref}"
            if key.lower() in {"cookie", "authorization", "proxy-authorization"}:
                return ""
            return value
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            sealed = {str(name): walk(item, str(name)) for name, item in value.items()}
            return sealed
        return value

    sealed = walk(payload)
    if not isinstance(sealed, dict):
        sealed = {}
    sealed["vaultRoot"] = str(vault.root)
    return sealed, secrets, outbound_refs


def text_contains_secret(text: str, secrets: list[str] | None) -> bool:
    """True when ``text`` still holds a known secret, including JSON escaping."""

    for secret in secrets or []:
        if not secret:
            continue
        if secret in text:
            return True
        escaped = json.dumps(secret, ensure_ascii=False)[1:-1]
        if escaped and escaped != secret and escaped in text:
            return True
    return False


def signed_urls_in(text: str) -> list[str]:
    return [match for match in _URL.findall(text) if has_secret_url(match)]


def seal_tree(value: object, vault: "SecretVault | None", secrets: list[str] | None = None) -> object:
    """Replace secret URLs with references. Other text is scrubbed in place."""

    if isinstance(value, str):
        if has_secret_url(value):
            if vault is None:
                redacted = redact_url(value)
                if text_contains_secret(redacted, [value, *(secrets or [])]):
                    return ""
                return redacted
            return f"umdref://{vault.put_outbound(value)}"
        return scrub_text(value, secrets)
    if isinstance(value, list):
        return [seal_tree(item, vault, secrets) for item in value]
    if isinstance(value, dict):
        sealed: dict[str, object] = {}
        for key, item in value.items():
            name = str(key)
            if name.lower() in {"cookie", "authorization", "proxy-authorization"}:
                sealed[name] = ""
            else:
                sealed[name] = seal_tree(item, vault, secrets)
        return sealed
    return value


def materialize_payload(payload: dict) -> dict:
    root = str(payload.get("vaultRoot") or "")
    if not root:
        return payload
    vault = SecretVault(Path(root))

    def walk(value: object) -> object:
        if isinstance(value, str):
            match = _REF.fullmatch(value.strip())
            if match is None:
                return value
            ref = match.group(1)
            urls = vault.read(ref, job_id="outbound", item_id=ref)
            return urls.get("value") or ""
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {str(key): walk(item) for key, item in value.items() if key != "vaultRoot"}
        return value

    walked = walk(payload)
    return walked if isinstance(walked, dict) else {}
