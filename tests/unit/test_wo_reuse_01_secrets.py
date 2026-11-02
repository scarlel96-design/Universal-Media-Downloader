"""WO-REUSE-01. Signed URLs stay out of SQLite, logs, and child process output."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from umd.auth.session import SessionProtectError, SessionStore
from umd.secrets import ProtectError, SecretUnavailable, SecretVault, scrub_text
from umd.storage.database import SCHEMA_VERSION, Library

TOKEN = "sig-" + uuid4().hex
COOKIE = "cookie-" + uuid4().hex
AUTH = "Bearer auth-" + uuid4().hex
SIGNED = f"https://cdn.example/media/a.png?sig={TOKEN}"
OTHER = f"https://cdn.example/media/a.png?sig=other-{uuid4().hex}"
PLAIN = "https://cdn.example/media/plain.png"


def _row(url: str, **extra) -> dict:
    row = {
        "title": extra.get("title", "사진"),
        "mediaUrl": url,
        "classification": extra.get("classification", "content"),
        "reasons": extra.get("reasons", "본문"),
        "selected": True,
        "override": extra.get("override", ""),
        "status": extra.get("status", "대기"),
        "originalUrl": extra.get("originalUrl", url),
        "mediaReference": extra.get("mediaReference", url),
        "thumbnailUrl": extra.get("thumbnailUrl", ""),
        "format": extra.get("format", ""),
        "subtitles": extra.get("subtitles", ""),
    }
    return row


def _text_dump(database: Path) -> str:
    connection = sqlite3.connect(database)
    try:
        chunks: list[str] = []
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        for table in tables:
            columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
            names = [str(column[1]) for column in columns]
            for record in connection.execute(f"SELECT * FROM {table}"):
                for name, value in zip(names, record):
                    if isinstance(value, str):
                        chunks.append(f"{table}.{name}={value}")
        return "\n".join(chunks)
    finally:
        connection.close()


def test_secret_is_not_written_when_acl_check_fails(tmp_path: Path, monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        class Result:
            returncode = 1
            stdout = b""
            stderr = b"denied"

        return Result()

    monkeypatch.setattr("umd.auth.session.subprocess.run", refuse)
    store = SessionStore(tmp_path / "sessions")
    with pytest.raises(SessionProtectError):
        store.save(
            "files.example",
            {"cookies": [{"name": "a", "value": TOKEN, "domain": "files.example"}]},
            expires_at=time.time() + 60,
        )
    tree = tmp_path / "sessions"
    blob = b""
    if tree.exists():
        for path in tree.rglob("*"):
            if path.is_file():
                blob += path.read_bytes()
    assert TOKEN.encode() not in blob
    assert not (tree / "files.example").exists()

    vault = SecretVault(tmp_path / "vault")
    with pytest.raises((SessionProtectError, ProtectError)):
        vault.put("job", "item", {"media": SIGNED})
    assert not (tmp_path / "vault").exists() or TOKEN.encode() not in b"".join(
        path.read_bytes() for path in (tmp_path / "vault").rglob("*") if path.is_file()
    )

    monkeypatch.undo()
    if os.name != "nt":
        raise AssertionError("Windows icacls was not exercised")
    live = SessionStore(tmp_path / "live-sessions")
    live.save("files.example", {"cookies": [{"name": "a", "value": "1", "domain": "files.example"}]}, expires_at=time.time() + 60)
    listing = subprocess.check_output(["icacls", str(tmp_path / "live-sessions" / "files.example")])
    assert os.environ["USERNAME"].encode("mbcs") in listing
    assert b"(OI)(CI)(F)" in listing
    assert b"SYSTEM" in listing or b"S-1-5-18" in listing
    saved = (tmp_path / "live-sessions" / "files.example" / "state.json").read_text(encoding="utf-8")
    assert "value" in saved


def test_signed_query_is_absent_from_sqlite_and_other_stores(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite"
    library = Library(str(database))
    job_id = library.create_job(
        SIGNED,
        [
            _row(
                SIGNED,
                title=f"이름 {SIGNED}",
                reasons=f"이유 {SIGNED}",
                classification=f"content {SIGNED}",
                thumbnailUrl=SIGNED,
                format=SIGNED,
                subtitles=f"자막 {SIGNED}",
                override=SIGNED,
            )
        ],
    )
    item_id = library.items(job_id)[0]["id"]
    library.update_selection(item_id, True, SIGNED)
    library.apply_transfer(item_id, {"error": SIGNED, "note": f"메모 {SIGNED}", "part_path": str(tmp_path / "file.part")})
    library.note_host(SIGNED, http_status=200, error_streak=0, concurrency_limit=1, in_flight=0)
    library.close()

    dump = _text_dump(database)
    assert TOKEN not in dump
    assert TOKEN.encode() not in database.read_bytes()
    assert "cdn.example" in dump
    progress = tmp_path / ".umd-progress-test"
    progress.write_text(json.dumps({"downloaded": 1, "total": 2}), encoding="utf-8")
    assert TOKEN not in progress.read_text(encoding="utf-8")
    assert TOKEN not in scrub_text(f"로그 {SIGNED} Cookie: {COOKIE} Authorization: {AUTH}")
    assert COOKIE not in scrub_text(f"Cookie: {COOKIE}")
    outside = [path for path in tmp_path.rglob("*") if path.is_file() and TOKEN.encode() in path.read_bytes()]
    assert outside == [path for path in outside if path.parent.name.endswith(".secrets") or ".secrets" in str(path.parent)]
    restored = Library(str(database))
    urls = restored.transfer_urls(item_id)
    assert urls is not None
    assert TOKEN in urls["media"]
    restored.close()


def test_distinct_signed_items_keep_separate_ids(tmp_path: Path) -> None:
    library = Library(str(tmp_path / "library.sqlite"))
    job_id = library.create_job(PLAIN, [_row(SIGNED), _row(OTHER)])
    items = library.items(job_id)
    assert len(items) == 2
    assert items[0]["id"] != items[1]["id"]
    assert {item["job_id"] for item in items} == {job_id}
    assert items[0]["media_url"] == items[1]["media_url"] == "https://cdn.example/media/a.png"
    assert TOKEN not in items[0]["media_url"]
    assert TOKEN not in items[1]["media_url"]
    library.close()
    again = Library(str(tmp_path / "library.sqlite"))
    kept = again.items(job_id)
    assert [item["id"] for item in kept] == [item["id"] for item in items]
    assert [item["job_id"] for item in kept] == [job_id, job_id]
    again.close()


def test_restart_reauth_when_signed_url_cannot_be_restored(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite"
    library = Library(str(database))
    job_id = library.create_job(PLAIN, [_row(SIGNED), _row(PLAIN)])
    secret, plain = library.items(job_id)
    library.apply_transfer(secret["id"], {"status": "일시정지"})
    library.apply_transfer(plain["id"], {"status": "일시정지"})
    library.close()

    restored = Library(str(database))
    rows = {row["id"]: row for row in restored.items(job_id)}
    assert rows[secret["id"]]["download_status"] == "일시정지"
    assert rows[plain["id"]]["download_status"] == "일시정지"
    live = restored.transfer_urls(secret["id"])
    assert live is not None and TOKEN in live["media"]
    plain_live = restored.transfer_urls(plain["id"])
    assert plain_live is not None and plain_live["media"] == PLAIN
    ref = rows[secret["id"]]["secret_ref"]
    with pytest.raises(SecretUnavailable):
        restored.vault.read("../" + ref, job_id=job_id, item_id=secret["id"])
    expired = SecretVault(restored.vault.root)
    expired_ref = uuid4().hex
    expired_path = restored.vault.root / f"{expired_ref}.json"
    expired_path.write_text(
        json.dumps({"job_id": job_id, "item_id": secret["id"], "urls": {"media": SIGNED}, "expires_at": time.time() - 5}),
        encoding="utf-8",
    )
    with pytest.raises(SecretUnavailable):
        expired.read(expired_ref, job_id=job_id, item_id=secret["id"])
    (restored.vault.root / f"{ref}.json").unlink()
    restored.close()

    lost = Library(str(database))
    final = {row["id"]: row for row in lost.items(job_id)}
    assert final[secret["id"]]["download_status"] == "재인증 필요"
    assert final[secret["id"]]["download_status"] not in {"완료", "실패", "취소", "일시정지", "다운로드 중"}
    assert final[plain["id"]]["download_status"] == "일시정지"
    assert lost.transfer_urls(secret["id"]) is not None
    assert TOKEN not in (lost.transfer_urls(secret["id"]) or {})["media"]
    assert TOKEN.encode() not in database.read_bytes()
    lost.close()


def test_child_stdio_and_exceptions_omit_secrets(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("UMD_IN_WORKER", None)
    payload = {
        "op": "video-extract",
        "payload": {"url": f"http://127.0.0.1/watch?sig={TOKEN}", "cookie": COOKIE, "authorization": AUTH},
    }
    proc = subprocess.run(
        [sys.executable, "-m", "umd.net.child"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=repo,
        env=env,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert TOKEN.encode() not in combined
    assert COOKIE.encode() not in combined
    assert AUTH.encode() not in combined
    body = json.loads(proc.stdout.decode("utf-8").strip().splitlines()[-1])
    assert body["ok"] is False
    assert TOKEN not in body["error"]
    assert COOKIE not in body["error"]
    assert AUTH not in body["error"]
    assert TOKEN not in body.get("trace", "")
    assert COOKIE not in body.get("trace", "")
    assert AUTH not in body.get("trace", "")


def test_child_success_stdout_omits_signed_url(tmp_path: Path) -> None:
    """A finished child keeps the request secret out of both stdout and stderr."""

    repo = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("UMD_IN_WORKER", None)
    payload = {
        "op": "gallery-download",
        "payload": {
            "url": SIGNED,
            "directory": str(tmp_path / "gallery"),
            "only": [],
            "cancelFlag": str(tmp_path / "cancel"),
            "cookie": COOKIE,
            "authorization": AUTH,
        },
    }
    proc = subprocess.run(
        [sys.executable, "-m", "umd.net.child"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=repo,
        env=env,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert TOKEN.encode() not in combined
    assert COOKIE.encode() not in combined
    assert AUTH.encode() not in combined
    body = json.loads(proc.stdout.decode("utf-8").strip().splitlines()[-1])
    assert body["ok"] is True
    assert body["result"]["files"] == []
    assert body["result"]["cancelled"] is False


def test_signed_result_is_a_ref_on_stdout_and_restored_in_memory(tmp_path: Path) -> None:
    """Success JSON carries a reference. The caller restores the URL in memory."""

    from umd.net.child import _write_json
    from umd.secrets import materialize_payload

    vault = SecretVault(tmp_path / "vault")
    stream = io.BytesIO()

    class _Stream:
        def __init__(self) -> None:
            self.buffer = stream

    _write_json(
        _Stream(),
        {"ok": True, "result": {"pageUrl": SIGNED, "plain": PLAIN, "cookie": COOKIE}},
        [SIGNED, COOKIE, TOKEN],
        vault,
    )
    text = stream.getvalue().decode("utf-8")
    assert TOKEN not in text
    assert COOKIE not in text
    assert "umdref://" in text
    assert PLAIN in text
    body = json.loads(text)
    body["result"]["vaultRoot"] = str(vault.root)
    restored = materialize_payload(body["result"])
    assert restored["pageUrl"] == SIGNED
    assert restored["plain"] == PLAIN
    assert "vaultRoot" not in restored


def _legacy(database: Path, version: int, token: str) -> tuple[str, str]:
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_meta (version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_meta(version) VALUES (?)", (version,))
    connection.execute(
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            page_url TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE media_items (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
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
            completed_at TEXT
        )
        """
    )
    if version >= 2:
        connection.execute("ALTER TABLE media_items ADD COLUMN note TEXT NOT NULL DEFAULT ''")
    job_id = f"job-{version}"
    item_id = f"item-{version}"
    connection.execute(
        "INSERT INTO jobs(id, page_url, status, created_at, completed_at) VALUES (?, ?, '다운로드 중', 't', NULL)",
        (job_id, f"https://cdn.example/page?sig={token}"),
    )
    connection.execute(
        """
        INSERT INTO media_items (
            id, job_id, page_url, media_url, title, classification, reasons, selected,
            user_override, download_status, error, created_at
        ) VALUES (?, ?, ?, ?, '제목', 'content', ?, 1, '', '다운로드 중', ?, 't')
        """,
        (
            item_id,
            job_id,
            f"https://cdn.example/page?sig={token}",
            f"https://cdn.example/file?sig={token}",
            f"이유 https://cdn.example/note?sig={token}",
            f"오류 https://cdn.example/err?sig={token}",
        ),
    )
    connection.execute(f"PRAGMA user_version = {version}")
    connection.commit()
    connection.close()
    return job_id, item_id


def test_migration_keeps_job_item_links_while_removing_secrets(tmp_path: Path) -> None:
    for version in (1, 2, 3):
        token = f"mig-{version}-{uuid4().hex}"
        database = tmp_path / f"v{version}.sqlite"
        if version < 3:
            job_id, item_id = _legacy(database, version, token)
        else:
            connection = sqlite3.connect(database)
            from umd.storage.database import _HOSTS, _ITEMS, _JOBS

            connection.executescript(
                "CREATE TABLE schema_meta (version INTEGER NOT NULL); INSERT INTO schema_meta(version) VALUES (3);"
                + _JOBS
                + ";"
                + _ITEMS
                + ";"
                + _HOSTS
            )
            job_id, item_id = "job-3", "item-3"
            connection.execute(
                "INSERT INTO jobs(id, page_url, status, created_at, completed_at) VALUES (?, ?, '다운로드 중', 't', NULL)",
                (job_id, f"https://cdn.example/page?sig={token}"),
            )
            connection.execute(
                """
                INSERT INTO media_items (
                    id, job_id, page_url, media_url, title, classification, reasons, selected,
                    user_override, download_status, error, created_at
                ) VALUES (?, ?, ?, ?, '제목', 'content', ?, 1, '', '다운로드 중', ?, 't')
                """,
                (
                    item_id,
                    job_id,
                    f"https://cdn.example/page?sig={token}",
                    f"https://cdn.example/file?sig={token}",
                    f"이유 https://cdn.example/note?sig={token}",
                    f"오류 https://cdn.example/err?sig={token}",
                ),
            )
            connection.commit()
            connection.close()
        before = sqlite3.connect(database)
        before_count = before.execute("SELECT COUNT(*) FROM media_items").fetchone()[0]
        before.close()
        library = Library(str(database))
        assert library.schema_version == SCHEMA_VERSION == 3
        items = library.items(job_id)
        assert before_count == 1
        assert len(items) == 1
        assert items[0]["id"] == item_id
        assert items[0]["job_id"] == job_id
        assert token not in _text_dump(database)
        assert items[0]["download_status"] == "재인증 필요"
        library.close()


def test_wal_and_backup_scope_is_reported(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_meta (version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_meta(version) VALUES (3)")
    from umd.storage.database import _HOSTS, _ITEMS, _JOBS

    connection.executescript(_JOBS + ";" + _ITEMS + ";" + _HOSTS)
    connection.execute(
        "INSERT INTO jobs(id, page_url, status, created_at, completed_at) VALUES ('job', ?, '완료', 't', 't2')",
        (SIGNED,),
    )
    connection.execute(
        """
        INSERT INTO media_items (
            id, job_id, page_url, media_url, title, classification, reasons, selected,
            user_override, download_status, error, created_at
        ) VALUES ('item', 'job', ?, ?, '제목', 'content', '본문', 1, '', '완료', ?, 't')
        """,
        (SIGNED, SIGNED, SIGNED),
    )
    connection.commit()
    connection.close()
    backup = tmp_path / "library-backup.sqlite"
    backup.write_bytes(database.read_bytes())
    library = Library(str(database))
    scope = library.durability_scope()
    library.close()
    assert scope["journal_mode"]
    assert scope["physical_delete"] is False
    assert isinstance(scope["wal"], bool)
    assert isinstance(scope["shm"], bool)
    logical = _text_dump(database)
    assert TOKEN not in logical
    assert TOKEN.encode() in backup.read_bytes()
    # UPDATE removes the logical value. SQLite does not promise the old bytes are gone.
    assert TOKEN.encode() in database.read_bytes()
