"""SQLite library for local media jobs.

Schema version 3. Version 1 and version 2 databases gain columns and keep
every row. Writes take one lock so the download thread and the UI thread
can share the connection. The UI model is still updated only on the UI thread.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zlib import crc32

from umd.download.images import sniff_image
from umd.secrets import SecretUnavailable, SecretVault, activate, has_secret_url, scrub_text

SCHEMA_VERSION = 3
_log = logging.getLogger("umd.storage")
_RESUME_ITEMS = {"일시정지", "다운로드 중", "대기", "재인증 필요"}
_RESUME_JOBS = {"일시정지", "다운로드 중", "대기", "재인증 필요", "추출 완료", "추출 중"}
_TERMINAL_JOBS = {"완료", "취소", "실패"}

_JOBS = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    page_url TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    secret_ref TEXT NOT NULL DEFAULT ''
)
"""

_ITEMS = """
CREATE TABLE media_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    page_url TEXT NOT NULL,
    media_url TEXT NOT NULL,
    title TEXT NOT NULL,
    classification TEXT NOT NULL,
    reasons TEXT NOT NULL,
    selected INTEGER NOT NULL,
    user_override TEXT NOT NULL DEFAULT '',
    download_status TEXT NOT NULL,
    saved_path TEXT NOT NULL DEFAULT '',
    byte_size INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    total_size INTEGER NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_http_status INTEGER,
    etag TEXT NOT NULL DEFAULT '',
    last_modified TEXT NOT NULL DEFAULT '',
    resume_capable INTEGER,
    priority INTEGER NOT NULL DEFAULT 0,
    part_path TEXT NOT NULL DEFAULT '',
    last_progress_at TEXT,
    note TEXT NOT NULL DEFAULT '',
    media_type TEXT NOT NULL DEFAULT 'image',
    extractor_id TEXT NOT NULL DEFAULT '',
    extractor_version TEXT NOT NULL DEFAULT '',
    media_reference TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT NOT NULL DEFAULT '',
    original_url TEXT NOT NULL DEFAULT '',
    width INTEGER,
    height INTEGER,
    duration REAL,
    format TEXT NOT NULL DEFAULT '',
    subtitles TEXT NOT NULL DEFAULT '',
    secret_ref TEXT NOT NULL DEFAULT ''
)
"""

_HOSTS = """
CREATE TABLE IF NOT EXISTS host_status (
    host TEXT PRIMARY KEY,
    last_http_status INTEGER,
    error_streak INTEGER NOT NULL DEFAULT 0,
    concurrency_limit INTEGER NOT NULL DEFAULT 0,
    in_flight INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)
"""

_V2_COLUMNS = (
    ("total_size", "INTEGER NOT NULL DEFAULT 0"),
    ("downloaded_bytes", "INTEGER NOT NULL DEFAULT 0"),
    ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_http_status", "INTEGER"),
    ("etag", "TEXT NOT NULL DEFAULT ''"),
    ("last_modified", "TEXT NOT NULL DEFAULT ''"),
    ("resume_capable", "INTEGER"),
    ("priority", "INTEGER NOT NULL DEFAULT 0"),
    ("part_path", "TEXT NOT NULL DEFAULT ''"),
    ("last_progress_at", "TEXT"),
    ("note", "TEXT NOT NULL DEFAULT ''"),
)

_V3_COLUMNS = (
    ("media_type", "TEXT NOT NULL DEFAULT 'image'"),
    ("extractor_id", "TEXT NOT NULL DEFAULT ''"),
    ("extractor_version", "TEXT NOT NULL DEFAULT ''"),
    ("media_reference", "TEXT NOT NULL DEFAULT ''"),
    ("thumbnail_url", "TEXT NOT NULL DEFAULT ''"),
    ("original_url", "TEXT NOT NULL DEFAULT ''"),
    ("width", "INTEGER"),
    ("height", "INTEGER"),
    ("duration", "REAL"),
    ("format", "TEXT NOT NULL DEFAULT ''"),
    ("subtitles", "TEXT NOT NULL DEFAULT ''"),
)

_TRANSFER = {
    "path": "saved_path",
    "size": "byte_size",
    "error": "error",
    "total_size": "total_size",
    "downloaded_bytes": "downloaded_bytes",
    "retry_count": "retry_count",
    "http_status": "last_http_status",
    "etag": "etag",
    "last_modified": "last_modified",
    "resume_capable": "resume_capable",
    "priority": "priority",
    "part_path": "part_path",
    "note": "note",
    "format": "format",
    "media_type": "media_type",
    "extractor_id": "extractor_id",
    "extractor_version": "extractor_version",
    "media_reference": "media_reference",
    "thumbnail_url": "thumbnail_url",
    "original_url": "original_url",
    "width": "width",
    "height": "height",
    "duration": "duration",
    "subtitles": "subtitles",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def media_hue(url: str) -> int:
    return crc32(url.encode("utf-8")) % 360


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class Library:
    def __init__(self, path: str) -> None:
        self.path = path
        self.recovery: list[str] = []
        self._lock = threading.RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.vault = SecretVault(Path(str(path) + ".secrets"))
        else:
            import tempfile

            self.vault = SecretVault(Path(tempfile.mkdtemp(prefix="umd-secrets-")))
        activate(self.vault)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._ensure()

    @property
    def schema_version(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT version FROM schema_meta").fetchone()
            return int(row["version"])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _ensure(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)"
        )
        row = self._conn.execute("SELECT version FROM schema_meta").fetchone()
        if row is None:
            self._conn.execute(_JOBS)
            self._conn.execute(_ITEMS)
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_job ON media_items(job_id)"
            )
            self._conn.execute(_HOSTS)
            self._conn.execute(
                "INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,)
            )
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()
        else:
            version = int(row["version"])
            if version < SCHEMA_VERSION:
                self._migrate(version)
            elif version > SCHEMA_VERSION:
                raise RuntimeError(f"지원하지 않는 데이터베이스 버전입니다: {version}")
            else:
                self._conn.execute(_HOSTS)
                self._conn.commit()
        try:
            self._ensure_secret_columns()
            self._strip_persisted_secrets()
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        self.recovery = (
            self._expire_lost_secrets() + self._reconcile_job_secrets() + self._recover()
        )

    def _column_names(self, table: str) -> set[str]:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def _text_columns(self, table: str) -> list[str]:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        names: list[str] = []
        for row in rows:
            declared = str(row["type"] or "")
            if declared == "" or "TEXT" in declared.upper() or "CHAR" in declared.upper():
                names.append(str(row["name"]))
        return names

    def _ensure_secret_columns(self) -> None:
        tables = {
            "jobs": "secret_ref TEXT NOT NULL DEFAULT ''",
            "media_items": "secret_ref TEXT NOT NULL DEFAULT ''",
        }
        for table, declaration in tables.items():
            names = self._column_names(table)
            if names and "secret_ref" not in names:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {declaration}")

    def _strip_persisted_secrets(self) -> None:
        url_columns = {"page_url", "media_url", "original_url", "thumbnail_url", "media_reference"}
        skip = {"id", "job_id", "secret_ref"}
        for table in ("jobs", "media_items", "host_status"):
            columns = [name for name in self._text_columns(table) if name not in skip]
            if not columns:
                continue
            rows = self._conn.execute(f"SELECT * FROM {table}").fetchall()
            for row in rows:
                assignments: list[str] = []
                params: list[object] = []
                url_changed = False
                keys = set(row.keys())
                for name in columns:
                    if name not in keys:
                        continue
                    current = row[name]
                    if not isinstance(current, str) or current == "":
                        continue
                    cleaned = scrub_text(current)
                    if cleaned == current:
                        continue
                    assignments.append(f"{name} = ?")
                    params.append(cleaned)
                    if name in url_columns:
                        url_changed = True
                status = str(row["download_status"]) if "download_status" in keys else ""
                if table == "media_items" and url_changed and status not in {"완료", "취소"}:
                    assignments.append("download_status = ?")
                    params.append("재인증 필요")
                if not assignments:
                    continue
                if table == "host_status":
                    params.append(row["host"])
                    target = "host"
                else:
                    params.append(row["id"])
                    target = "id"
                self._conn.execute(
                    f"UPDATE {table} SET {', '.join(assignments)} WHERE {target} = ?",
                    params,
                )

    def durability_scope(self) -> dict:
        row = self._conn.execute("PRAGMA journal_mode").fetchone()
        mode = str(row[0] if row is not None else "")
        path = None if self.path == ":memory:" else Path(self.path)
        return {
            "journal_mode": mode,
            "wal": bool(path and Path(str(path) + "-wal").is_file()),
            "shm": bool(path and Path(str(path) + "-shm").is_file()),
            "physical_delete": False,
        }

    def transfer_urls(self, item_id: str) -> dict | None:
        """Live URLs for one item. None means the protected reference is gone."""

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM media_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                return {}
            base = {
                "page": str(row["page_url"] or ""),
                "media": str(row["media_url"] or ""),
                "original": str(row["original_url"] or row["media_url"] or ""),
                "thumbnail": str(row["thumbnail_url"] or ""),
                "reference": str(row["media_reference"] or ""),
            }
            ref = str(row["secret_ref"] or "")
            if not ref:
                return base
            try:
                secret = self.vault.read(ref, job_id=str(row["job_id"]), item_id=item_id)
            except SecretUnavailable:
                return None
            base.update(secret)
            return base

    def _expire_lost_secrets(self) -> list[str]:
        notes: list[str] = []
        if "secret_ref" not in self._column_names("media_items"):
            return notes
        rows = self._conn.execute(
            "SELECT id, job_id, secret_ref, download_status FROM media_items WHERE secret_ref != ''"
        ).fetchall()
        for row in rows:
            ref = str(row["secret_ref"] or "")
            status = str(row["download_status"] or "")
            if status in {"완료", "취소"}:
                self.vault.drop(ref)
                self._conn.execute("UPDATE media_items SET secret_ref = '' WHERE id = ?", (row["id"],))
                continue
            try:
                self.vault.read(ref, job_id=str(row["job_id"]), item_id=str(row["id"]))
            except SecretUnavailable:
                self._conn.execute(
                    """
                    UPDATE media_items
                       SET download_status = '재인증 필요', secret_ref = '', note = ?
                     WHERE id = ?
                    """,
                    ("보호된 주소를 다시 열지 못했습니다", row["id"]),
                )
                notes.append(f"reauth:{row['id']}")
        self._conn.commit()
        return notes

    def _job_may_drop_page_secret(self, job_id: str, status: str) -> bool:
        if status in _RESUME_JOBS or status not in _TERMINAL_JOBS:
            return False
        rows = self._conn.execute(
            "SELECT download_status FROM media_items WHERE job_id = ?",
            (job_id,),
        ).fetchall()
        return not any(str(row["download_status"] or "") in _RESUME_ITEMS for row in rows)

    def _drop_ref_file(self, ref: str, *, strict: bool) -> bool:
        try:
            self.vault.drop(ref)
        except OSError:
            _log.info("secret release failed %s", ref)
            if strict:
                raise RuntimeError("작업 참조를 지우지 못했습니다") from None
            return False
        if (self.vault.root / f"{ref}.json").exists():
            _log.info("secret release failed %s", ref)
            if strict:
                raise RuntimeError("작업 참조를 지우지 못했습니다")
            return False
        return True

    def _release_job_secret_if_allowed(self, job_id: str, *, strict: bool) -> bool:
        row = self._conn.execute(
            "SELECT status, secret_ref FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        ref = str(row["secret_ref"] or "")
        status = str(row["status"] or "")
        if not self._job_may_drop_page_secret(job_id, status):
            return False
        items = self._conn.execute(
            "SELECT id, download_status, secret_ref FROM media_items WHERE job_id = ?",
            (job_id,),
        ).fetchall()
        item_ids: list[str] = []
        for item in items:
            if str(item["download_status"] or "") not in {"완료", "취소"}:
                continue
            item_ref = str(item["secret_ref"] or "")
            if not item_ref:
                continue
            if not self._drop_ref_file(item_ref, strict=strict):
                self._conn.rollback()
                return False
            item_ids.append(str(item["id"]))
        if ref and not self._drop_ref_file(ref, strict=strict):
            self._conn.rollback()
            return False
        if not ref and not item_ids:
            return False
        for item_id in item_ids:
            self._conn.execute(
                "UPDATE media_items SET secret_ref = '' WHERE id = ?",
                (item_id,),
            )
        if ref:
            self._conn.execute("UPDATE jobs SET secret_ref = '' WHERE id = ?", (job_id,))
        self._conn.commit()
        _log.info("job secret release %s", job_id)
        return True

    def _reconcile_job_secrets(self) -> list[str]:
        notes: list[str] = []
        if "secret_ref" not in self._column_names("jobs"):
            return notes
        rows = self._conn.execute(
            "SELECT id, status, secret_ref FROM jobs WHERE secret_ref != ''"
        ).fetchall()
        for row in rows:
            job_id = str(row["id"])
            ref = str(row["secret_ref"] or "")
            status = str(row["status"] or "")
            try:
                self.vault.read(ref, job_id=job_id, item_id="")
                readable = True
            except SecretUnavailable:
                readable = False
            if self._job_may_drop_page_secret(job_id, status):
                if self._release_job_secret_if_allowed(job_id, strict=False):
                    notes.append(f"job-release:{job_id}")
                elif ref:
                    notes.append(f"job-release-failed:{job_id}")
                continue
            if readable:
                continue
            if status in {"완료", "취소"}:
                self._conn.execute("UPDATE jobs SET secret_ref = '' WHERE id = ?", (job_id,))
                notes.append(f"job-clear:{job_id}")
                _log.info("job secret clear %s", job_id)
                continue
            self._conn.execute(
                """
                UPDATE jobs
                   SET status = '재인증 필요', completed_at = NULL, secret_ref = ''
                 WHERE id = ?
                """,
                (job_id,),
            )
            notes.append(f"job-reauth:{job_id}")
            _log.info("job secret reauth %s", job_id)
        self._drop_unreferenced_terminal_files(notes)
        self._conn.commit()
        return notes

    def _drop_unreferenced_terminal_files(self, notes: list[str]) -> None:
        if not self.vault.root.is_dir():
            return
        linked = {
            str(row["secret_ref"])
            for row in self._conn.execute(
                "SELECT secret_ref FROM jobs WHERE secret_ref != ''"
            ).fetchall()
        }
        linked.update(
            str(row["secret_ref"])
            for row in self._conn.execute(
                "SELECT secret_ref FROM media_items WHERE secret_ref != ''"
            ).fetchall()
        )
        inspected = 0
        try:
            entries = self.vault.root.iterdir()
        except OSError:
            _log.info("orphan sweep skipped")
            return
        for path in entries:
            if inspected >= 64:
                break
            inspected += 1
            name = path.name
            if not name.endswith(".json") or path.is_symlink():
                continue
            ref = name[:-5]
            if len(ref) != 32 or ref in linked:
                continue
            try:
                if path.resolve().parent != self.vault.root.resolve():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError, ValueError):
                continue
            if not isinstance(data, dict) or data.get("expires_at") is not None:
                continue
            job_id = str(data.get("job_id") or "")
            item_id = str(data.get("item_id") or "")
            if not job_id or job_id == "outbound":
                continue
            if not self._orphan_is_terminal(job_id, item_id):
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                notes.append(f"orphan-kept:{ref}")
                _log.info("orphan kept %s", ref)
                continue
            notes.append(f"orphan-removed:{ref}")
            _log.info("orphan removed %s", ref)

    def _orphan_is_terminal(self, job_id: str, item_id: str) -> bool:
        job = self._conn.execute(
            "SELECT status, secret_ref FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if job is None or str(job["secret_ref"] or ""):
            return False
        if item_id == "":
            return self._job_may_drop_page_secret(job_id, str(job["status"] or ""))
        item = self._conn.execute(
            """
            SELECT secret_ref, download_status FROM media_items
             WHERE id = ? AND job_id = ?
            """,
            (item_id, job_id),
        ).fetchone()
        if item is None or str(item["secret_ref"] or ""):
            return False
        return str(item["download_status"] or "") in {"완료", "취소"}

    def _migrate(self, version: int) -> None:
        existing = self._column_names("media_items")
        if version < 2:
            for name, declaration in _V2_COLUMNS:
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE media_items ADD COLUMN {name} {declaration}")
            self._conn.execute(_HOSTS)
            existing = self._column_names("media_items")
        if version < 3:
            for name, declaration in _V3_COLUMNS:
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE media_items ADD COLUMN {name} {declaration}")
            self._conn.execute(
                "UPDATE media_items SET original_url = media_url WHERE original_url = ''"
            )
            self._conn.execute(
                "UPDATE media_items SET media_reference = media_url WHERE media_reference = ''"
            )
            self._conn.execute(
                "UPDATE media_items SET media_type = 'image' WHERE media_type = ''"
            )
        self._ensure_secret_columns()
        self._strip_persisted_secrets()
        self._conn.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()

    def create_job(self, page_url: str, rows: list[dict]) -> str:
        with self._lock:
            job_id = uuid4().hex
            created = _now()
            page_stored = scrub_text(page_url)
            job_ref = ""
            if has_secret_url(page_url):
                job_ref = self.vault.put(job_id, "", {"page": page_url})
            self._conn.execute(
                """
                INSERT INTO jobs(id, page_url, status, created_at, completed_at, secret_ref)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (job_id, page_stored, "추출 완료", created, job_ref),
            )
            for row in rows:
                item_id = uuid4().hex
                row["itemId"] = item_id
                width = _optional_int(row.get("width"))
                height = _optional_int(row.get("height"))
                duration = row.get("duration")
                duration_value = float(duration) if isinstance(duration, (int, float)) and duration else None
                filesize = _optional_int(row.get("filesize"))
                media = str(row.get("mediaUrl") or "")
                original = str(row.get("originalUrl") or media)
                reference = str(row.get("mediaReference") or media)
                thumbnail = str(row.get("thumbnailUrl") or "")
                secret_fields = {
                    "page": page_url,
                    "media": media,
                    "original": original,
                    "thumbnail": thumbnail,
                    "reference": reference,
                }
                secret_fields = {key: value for key, value in secret_fields.items() if has_secret_url(value)}
                ref = self.vault.put(job_id, item_id, secret_fields) if secret_fields else ""
                row["secretRef"] = ref
                self._conn.execute(
                    """
                    INSERT INTO media_items (
                        id, job_id, page_url, media_url, title, classification, reasons,
                        selected, user_override, download_status, saved_path, byte_size,
                        error, created_at, completed_at, priority, total_size,
                        media_type, extractor_id, extractor_version, media_reference,
                        thumbnail_url, original_url, width, height, duration, format, subtitles,
                        secret_ref
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, '', ?, NULL, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        item_id,
                        job_id,
                        page_stored,
                        scrub_text(media),
                        scrub_text(str(row.get("title") or "")),
                        scrub_text(str(row.get("classification") or "")),
                        scrub_text(str(row.get("reasons") or "")),
                        1 if row["selected"] else 0,
                        scrub_text(str(row.get("override") or "")),
                        scrub_text(str(row.get("status") or "대기")),
                        created,
                        int(row.get("priority") or 0),
                        int(filesize or 0),
                        scrub_text(str(row.get("mediaType") or row.get("kind") or "image")),
                        scrub_text(str(row.get("extractorId") or "")),
                        scrub_text(str(row.get("extractorVersion") or "")),
                        scrub_text(reference),
                        scrub_text(thumbnail),
                        scrub_text(original),
                        width,
                        height,
                        duration_value,
                        scrub_text(str(row.get("format") or "")),
                        scrub_text(str(row.get("subtitles") or "")),
                        ref,
                    ),
                )
            self._conn.commit()
            return job_id

    def update_selection(self, item_id: str, selected: bool, override: str) -> None:
        if not item_id:
            return
        with self._lock:
            self._conn.execute(
                "UPDATE media_items SET selected = ?, user_override = ? WHERE id = ?",
                (1 if selected else 0, scrub_text(override or ""), item_id),
            )
            self._conn.commit()

    def update_download(
        self,
        item_id: str,
        *,
        status: str,
        path: str,
        size: int,
        error: str,
    ) -> None:
        self.apply_transfer(
            item_id,
            {
                "status": status,
                "path": path or "",
                "size": int(size or 0),
                "error": error or "",
            },
        )

    def apply_transfer(self, item_id: str, values: dict) -> None:
        if not item_id or not values:
            return
        with self._lock:
            assignments: list[str] = []
            params: list[object] = []
            if "status" in values:
                status = str(values["status"])
                if status == "실패" and self._has_secret(item_id):
                    status = "재인증 필요"
                assignments.append("download_status = ?")
                params.append(status)
                if status in {"완료", "실패", "취소"}:
                    assignments.append("completed_at = ?")
                    params.append(_now())
                    self._release_secret(item_id)
                elif status == "재인증 필요":
                    self._release_secret(item_id)
                elif status in {"다운로드 중", "일시정지", "대기"}:
                    assignments.append("completed_at = NULL")
            for key, column in _TRANSFER.items():
                if key not in values:
                    continue
                stored = values[key]
                if isinstance(stored, str):
                    stored = scrub_text(stored)
                assignments.append(f"{column} = ?")
                params.append(stored)
            if "downloaded_bytes" in values or "status" in values:
                assignments.append("last_progress_at = ?")
                params.append(_now())
            if not assignments:
                return
            params.append(item_id)
            self._conn.execute(
                f"UPDATE media_items SET {', '.join(assignments)} WHERE id = ?",
                params,
            )
            self._conn.commit()

    def note_host(
        self,
        host: str,
        *,
        http_status: int | None,
        error_streak: int,
        concurrency_limit: int,
        in_flight: int,
    ) -> None:
        if not host:
            return
        host = scrub_text(host)
        if "://" in host:
            from urllib.parse import urlsplit

            host = urlsplit(host).hostname or ""
        host = host.split("@")[-1].split("/")[0]
        if not host:
            return
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO host_status (
                    host, last_http_status, error_streak, concurrency_limit, in_flight, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(host) DO UPDATE SET
                    last_http_status = excluded.last_http_status,
                    error_streak = excluded.error_streak,
                    concurrency_limit = excluded.concurrency_limit,
                    in_flight = excluded.in_flight,
                    updated_at = excluded.updated_at
                """,
                (host, http_status, int(error_streak), int(concurrency_limit), int(in_flight), _now()),
            )
            self._conn.commit()

    def set_priority(self, item_id: str, priority: int) -> None:
        self.apply_transfer(item_id, {"priority": int(priority)})

    def set_job_status(self, job_id: str, status: str) -> None:
        with self._lock:
            completed = _now() if status in {"완료", "실패", "취소"} else None
            status = scrub_text(status)
            self._conn.execute(
                "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed, job_id),
            )
            self._conn.commit()
            self._release_job_secret_if_allowed(job_id, strict=True)

    def latest_job(self) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def items(self, job_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM media_items WHERE job_id = ? ORDER BY rowid",
                (job_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def hosts(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM host_status ORDER BY host"
            ).fetchall()
            return [dict(row) for row in rows]

    def rows_for(self, job_id: str) -> list[dict]:
        rebuilt: list[dict] = []
        for item in self.items(job_id):
            total = int(item.get("total_size") or 0)
            downloaded = int(item.get("downloaded_bytes") or 0)
            if item["download_status"] == "완료" and int(item.get("byte_size") or 0) > 0:
                progress = 1.0
            elif total > 0:
                progress = downloaded / total
            else:
                progress = -1.0
            capable = item.get("resume_capable")
            kind = str(item.get("media_type") or "image")
            if kind not in {"image", "video"}:
                kind = "image"
            original = str(item.get("original_url") or item["media_url"])
            delivery = "yt-dlp" if kind == "video" else "http"
            if delivery == "http" and str(item.get("extractor_id") or "") == "gallery-dl":
                suffix = original.lower().split("?", 1)[0]
                if not suffix.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    delivery = "gallery-dl"
            thumb = str(item.get("thumbnail_url") or "")
            filesize = int(item.get("total_size") or 0) or None
            rebuilt.append(
                {
                    "title": item["title"],
                    "kind": kind,
                    "selected": bool(item["selected"]),
                    "hue": media_hue(original or item["media_url"]),
                    "previewUrl": thumb or original,
                    "classification": item["classification"],
                    "reasons": item["reasons"],
                    "status": item["download_status"],
                    "fetchUrl": original,
                    "mediaUrl": original,
                    "pageUrl": item["page_url"],
                    "override": item["user_override"] or "",
                    "itemId": item["id"],
                    "error": item["error"] or "",
                    "savedPath": item["saved_path"] or "",
                    "byteSize": int(item["byte_size"] or 0),
                    "downloaded": downloaded,
                    "totalSize": total,
                    "progress": progress,
                    "partPath": item.get("part_path") or "",
                    "etag": item.get("etag") or "",
                    "lastModified": item.get("last_modified") or "",
                    "resumeCapable": -1 if capable is None else int(capable),
                    "retryCount": int(item.get("retry_count") or 0),
                    "priority": int(item.get("priority") or 0),
                    "note": item.get("note") or "",
                    "mediaType": kind,
                    "extractorId": item.get("extractor_id") or "",
                    "extractorVersion": item.get("extractor_version") or "",
                    "mediaReference": item.get("media_reference") or original,
                    "thumbnailUrl": thumb,
                    "originalUrl": original,
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "duration": item.get("duration"),
                    "format": item.get("format") or "",
                    "formatId": "",
                    "formats": [],
                    "filesize": filesize,
                    "delivery": delivery,
                    "subtitles": item.get("subtitles") or "",
                    "secretRef": item.get("secret_ref") or "",
                }
            )
        return rebuilt

    def incomplete_items(self, job_id: str | None = None) -> list[dict]:
        with self._lock:
            if job_id:
                rows = self._conn.execute(
                    """
                    SELECT * FROM media_items
                     WHERE job_id = ? AND download_status IN ('다운로드 중', '일시정지')
                     ORDER BY rowid
                    """,
                    (job_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM media_items
                     WHERE download_status IN ('다운로드 중', '일시정지')
                     ORDER BY rowid
                    """
                ).fetchall()
            return [dict(row) for row in rows]

    def integrity_issues(self) -> list[str]:
        """Completed rows must point at a finished file of the recorded size."""
        with self._lock:
            issues: list[str] = []
            rows = self._conn.execute(
                """
                SELECT id, download_status, saved_path, byte_size
                  FROM media_items
                 WHERE download_status = '완료'
                """
            ).fetchall()
            for row in rows:
                item_id = row["id"]
                path = Path(row["saved_path"] or "")
                if path.name.endswith(".part") or ".part" in path.name:
                    issues.append(f"partial:{item_id}")
                    continue
                if not path.is_file():
                    issues.append(f"missing:{item_id}")
                    continue
                size = path.stat().st_size
                if size != int(row["byte_size"] or 0):
                    issues.append(f"size:{item_id}")
            return issues

    def _recover(self) -> list[str]:
        notes: list[str] = []
        rows = self._conn.execute(
            """
            SELECT * FROM media_items
             WHERE download_status IN ('다운로드 중', '일시정지')
             ORDER BY rowid
            """
        ).fetchall()
        touched: set[str] = set()
        for row in rows:
            item_id = str(row["id"])
            touched.add(str(row["job_id"]))
            saved = Path(row["saved_path"]) if row["saved_path"] else None
            part = Path(row["part_path"]) if row["part_path"] else None
            recorded = int(row["byte_size"] or 0)
            if saved is not None and saved.is_file() and ".part" not in saved.name:
                try:
                    with saved.open("rb") as handle:
                        kind = sniff_image(handle.read(16))
                except OSError:
                    kind = None
                size = saved.stat().st_size
                if kind and recorded == size and size > 0:
                    self._conn.execute(
                        """
                        UPDATE media_items
                           SET download_status = '완료', byte_size = ?, downloaded_bytes = ?,
                               part_path = '', completed_at = ?, note = ?
                         WHERE id = ?
                        """,
                        (size, size, _now(), row["note"] or "저장 후 기록을 복구했습니다", item_id),
                    )
                    notes.append(f"reconciled:{item_id}")
                    continue
            if part is not None and part.is_file():
                size = part.stat().st_size
                self._conn.execute(
                    """
                    UPDATE media_items
                       SET downloaded_bytes = ?, note = ?
                     WHERE id = ?
                    """,
                    (size, row["note"] or "이어서 받을 수 있습니다", item_id),
                )
                notes.append(f"incomplete:{item_id}")
                continue
            self._conn.execute(
                """
                UPDATE media_items
                   SET note = ?
                 WHERE id = ?
                """,
                ("부분 파일이 없어 처음부터 받아야 합니다", item_id),
            )
            notes.append(f"restart:{item_id}")
        if touched:
            self._settle_jobs(touched)
        self._conn.commit()
        return notes

    def _has_secret(self, item_id: str) -> bool:
        row = self._conn.execute(
            "SELECT secret_ref FROM media_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        return bool(row and str(row["secret_ref"] or ""))

    def _release_secret(self, item_id: str) -> None:
        row = self._conn.execute(
            "SELECT secret_ref FROM media_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            return
        self.vault.drop(str(row["secret_ref"] or ""))
        self._conn.execute("UPDATE media_items SET secret_ref = '' WHERE id = ?", (item_id,))

    def _settle_jobs(self, job_ids: set[str]) -> None:
        for job_id in job_ids:
            job = self._conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None or job["status"] not in {"다운로드 중", "일시정지"}:
                continue
            rows = self._conn.execute(
                "SELECT download_status FROM media_items WHERE job_id = ?",
                (job_id,),
            ).fetchall()
            statuses = [row["download_status"] for row in rows]
            if any(status in {"다운로드 중", "일시정지", "대기"} for status in statuses):
                continue
            if any(status == "재인증 필요" for status in statuses):
                self._conn.execute(
                    "UPDATE jobs SET status = '재인증 필요', completed_at = NULL WHERE id = ?",
                    (job_id,),
                )
                continue
            if statuses and all(status == "완료" for status in statuses):
                self._conn.execute(
                    "UPDATE jobs SET status = '완료', completed_at = ? WHERE id = ?",
                    (_now(), job_id),
                )
                self._conn.commit()
                self._release_job_secret_if_allowed(job_id, strict=False)
