"""SQLite library for local media jobs.

Schema version 3. Version 1 and version 2 databases gain columns and keep
every row. Writes take one lock so the download thread and the UI thread
can share the connection. The UI model is still updated only on the UI thread.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zlib import crc32

from umd.download.images import sniff_image

SCHEMA_VERSION = 3

_JOBS = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    page_url TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
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
    subtitles TEXT NOT NULL DEFAULT ''
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
        self.recovery = self._recover()

    def _column_names(self, table: str) -> set[str]:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

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
        self._conn.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()

    def create_job(self, page_url: str, rows: list[dict]) -> str:
        with self._lock:
            job_id = uuid4().hex
            created = _now()
            self._conn.execute(
                "INSERT INTO jobs(id, page_url, status, created_at, completed_at) VALUES (?, ?, ?, ?, NULL)",
                (job_id, page_url, "추출 완료", created),
            )
            for row in rows:
                item_id = uuid4().hex
                row["itemId"] = item_id
                width = _optional_int(row.get("width"))
                height = _optional_int(row.get("height"))
                duration = row.get("duration")
                duration_value = float(duration) if isinstance(duration, (int, float)) and duration else None
                filesize = _optional_int(row.get("filesize"))
                self._conn.execute(
                    """
                    INSERT INTO media_items (
                        id, job_id, page_url, media_url, title, classification, reasons,
                        selected, user_override, download_status, saved_path, byte_size,
                        error, created_at, completed_at, priority, total_size,
                        media_type, extractor_id, extractor_version, media_reference,
                        thumbnail_url, original_url, width, height, duration, format, subtitles
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, '', ?, NULL, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        item_id,
                        job_id,
                        page_url,
                        row["mediaUrl"],
                        row["title"],
                        row["classification"],
                        row["reasons"],
                        1 if row["selected"] else 0,
                        row.get("override") or "",
                        row.get("status") or "대기",
                        created,
                        int(row.get("priority") or 0),
                        int(filesize or 0),
                        str(row.get("mediaType") or row.get("kind") or "image"),
                        str(row.get("extractorId") or ""),
                        str(row.get("extractorVersion") or ""),
                        str(row.get("mediaReference") or row.get("mediaUrl") or ""),
                        str(row.get("thumbnailUrl") or ""),
                        str(row.get("originalUrl") or row.get("mediaUrl") or ""),
                        width,
                        height,
                        duration_value,
                        str(row.get("format") or ""),
                        str(row.get("subtitles") or ""),
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
                (1 if selected else 0, override or "", item_id),
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
                assignments.append("download_status = ?")
                params.append(status)
                if status in {"완료", "실패", "취소"}:
                    assignments.append("completed_at = ?")
                    params.append(_now())
                elif status in {"다운로드 중", "일시정지", "대기"}:
                    assignments.append("completed_at = NULL")
            for key, column in _TRANSFER.items():
                if key not in values:
                    continue
                assignments.append(f"{column} = ?")
                params.append(values[key])
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
            self._conn.execute(
                "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed, job_id),
            )
            self._conn.commit()

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
            if statuses and all(status == "완료" for status in statuses):
                self._conn.execute(
                    "UPDATE jobs SET status = '완료', completed_at = ? WHERE id = ?",
                    (_now(), job_id),
                )
