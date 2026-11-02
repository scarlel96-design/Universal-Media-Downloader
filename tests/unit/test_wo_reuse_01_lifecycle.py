"""WO-REUSE-01-S1. Job secrets end with the job. Expired outbound refs do not."""

from __future__ import annotations

import io
import json
import logging
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from umd.secrets import SecretUnavailable, SecretVault
from umd.storage.database import Library

TOKEN = "sig-" + uuid4().hex
COOKIE = "cookie-" + uuid4().hex
AUTH = "Bearer auth-" + uuid4().hex
SIGNED = f"https://cdn.example/page?sig={TOKEN}"
MEDIA = f"https://cdn.example/media/a.png?sig={TOKEN}"
OTHER = f"https://cdn.example/media/b.png?sig=other-{uuid4().hex}"
PLAIN = "https://cdn.example/media/plain.png"


def _row(url: str, status: str) -> dict:
    return {
        "title": "사진",
        "mediaUrl": url,
        "classification": "content",
        "reasons": "본문",
        "selected": True,
        "status": status,
    }


def _job_row(library: Library, job_id: str) -> sqlite3.Row:
    return library._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def test_completed_job_releases_page_secret(tmp_path: Path) -> None:
    library = Library(str(tmp_path / "library.sqlite"))
    job_id = library.create_job(SIGNED, [_row(PLAIN, "완료")])
    ref = str(_job_row(library, job_id)["secret_ref"])
    secret = library.vault.root / f"{ref}.json"
    assert ref
    assert TOKEN in secret.read_text(encoding="utf-8")
    library.set_job_status(job_id, "완료")
    assert _job_row(library, job_id)["id"] == job_id
    assert _job_row(library, job_id)["secret_ref"] == ""
    assert not secret.exists()
    library.close()


def test_cancelled_job_releases_page_secret(tmp_path: Path) -> None:
    library = Library(str(tmp_path / "library.sqlite"))
    paused_id = library.create_job(OTHER, [_row(OTHER, "일시정지")])
    paused_ref = str(_job_row(library, paused_id)["secret_ref"])
    job_id = library.create_job(SIGNED, [_row(MEDIA, "취소"), _row(PLAIN, "취소")])
    item_ids = [row["id"] for row in library.items(job_id)]
    item_ref = str(library.items(job_id)[0]["secret_ref"])
    page_ref = str(_job_row(library, job_id)["secret_ref"])
    library.set_job_status(job_id, "취소")
    assert _job_row(library, job_id)["secret_ref"] == ""
    assert not (library.vault.root / f"{page_ref}.json").exists()
    assert not (library.vault.root / f"{item_ref}.json").exists()
    kept = library.items(job_id)
    assert [row["id"] for row in kept] == item_ids
    assert all(row["job_id"] == job_id for row in kept)
    assert (library.vault.root / f"{paused_ref}.json").is_file()
    assert _job_row(library, paused_id)["secret_ref"] == paused_ref
    library.close()


def test_paused_job_retains_required_secret(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite"
    library = Library(str(database))
    job_id = library.create_job(SIGNED, [_row(MEDIA, "일시정지")])
    item_id = library.items(job_id)[0]["id"]
    ref = str(_job_row(library, job_id)["secret_ref"])
    library.set_job_status(job_id, "일시정지")
    library.close()

    restored = Library(str(database))
    assert _job_row(restored, job_id)["status"] == "일시정지"
    assert _job_row(restored, job_id)["secret_ref"] == ref
    assert (restored.vault.root / f"{ref}.json").is_file()
    live = restored.transfer_urls(item_id)
    assert live is not None
    assert live["media"] == MEDIA
    page = restored.vault.read(ref, job_id=job_id, item_id="")
    assert page["page"] == SIGNED
    restored.close()


def test_expired_outbound_refs_are_removed(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    start = 10_000_000.0
    state = {"now": start}
    vault = SecretVault(root, clock=lambda: state["now"])
    ref = vault.put_outbound(SIGNED)
    durable = vault.put("job", "", {"page": OTHER})
    (root / "notes.json").write_text("user-file", encoding="utf-8")
    future = uuid4().hex
    (root / f"{future}.json").write_text(
        json.dumps(
            {
                "job_id": "outbound",
                "item_id": future,
                "urls": {"value": PLAIN},
                "expires_at": start + 7200,
            }
        ),
        encoding="utf-8",
    )
    state["now"] = start + 3599
    follower = SecretVault(root, clock=lambda: state["now"])
    assert (root / f"{ref}.json").is_file()
    assert follower.sweep_expired_outbound() == 0
    state["now"] = start + 3600
    assert follower.sweep_expired_outbound() >= 1
    assert not (root / f"{ref}.json").exists()
    assert (root / f"{durable}.json").is_file()
    assert (root / f"{future}.json").is_file()
    assert (root / "notes.json").read_text(encoding="utf-8") == "user-file"


def test_cleanup_preserves_active_refs(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    state = {"now": 8_000_000.0}
    vault = SecretVault(root, clock=lambda: state["now"])
    active = vault.put_outbound(SIGNED)
    body = json.loads((root / f"{active}.json").read_text(encoding="utf-8"))
    body["expires_at"] = state["now"] - 5
    (root / f"{active}.json").write_text(json.dumps(body), encoding="utf-8")
    idle = uuid4().hex
    (root / f"{idle}.json").write_text(
        json.dumps(
            {
                "job_id": "outbound",
                "item_id": idle,
                "urls": {"value": OTHER},
                "expires_at": state["now"] - 5,
            }
        ),
        encoding="utf-8",
    )
    job_ref = vault.put("job", "", {"page": SIGNED})
    item_ref = vault.put("job", "item", {"media": MEDIA})
    (root / "keep.txt").write_text("keep", encoding="utf-8")
    assert vault.sweep_expired_outbound() >= 1
    assert (root / f"{active}.json").is_file()
    assert not (root / f"{idle}.json").exists()
    assert (root / f"{job_ref}.json").is_file()
    assert (root / f"{item_ref}.json").is_file()
    assert (root / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_orphan_refs_recovered_after_restart(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    expired = uuid4().hex
    (root / f"{expired}.json").write_text(
        json.dumps(
            {
                "job_id": "outbound",
                "item_id": expired,
                "urls": {"value": SIGNED},
                "expires_at": 1,
            }
        ),
        encoding="utf-8",
    )
    durable = uuid4().hex
    (root / f"{durable}.json").write_text(
        json.dumps(
            {"job_id": "job", "item_id": "", "urls": {"page": SIGNED}, "expires_at": None}
        ),
        encoding="utf-8",
    )
    (root / "notes.json").write_text("user-file", encoding="utf-8")
    SecretVault(root)
    assert not (root / f"{expired}.json").exists()
    assert TOKEN in (root / f"{durable}.json").read_text(encoding="utf-8")
    assert (root / "notes.json").is_file()


def test_cleanup_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = Library(str(tmp_path / "library.sqlite"))
    job_id = library.create_job(SIGNED, [_row(PLAIN, "완료")])
    other_id = library.create_job(OTHER, [_row(OTHER, "일시정지")])
    other_ref = str(_job_row(library, other_id)["secret_ref"])
    (library.vault.root / "notes.json").write_text("user-file", encoding="utf-8")
    ref = str(_job_row(library, job_id)["secret_ref"])
    original = Path.unlink
    blocked = {"used": False}

    def guarded(self: Path, *args, **kwargs):
        if self.name == f"{ref}.json" and not blocked["used"]:
            blocked["used"] = True
            raise OSError("denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", guarded)
    with pytest.raises(RuntimeError, match="작업 참조를 지우지 못했습니다"):
        library.set_job_status(job_id, "완료")
    assert _job_row(library, job_id)["status"] == "완료"
    assert _job_row(library, job_id)["secret_ref"] == ref
    assert (library.vault.root / f"{ref}.json").is_file()
    monkeypatch.undo()
    library.set_job_status(job_id, "완료")
    library.set_job_status(job_id, "완료")
    assert _job_row(library, job_id)["secret_ref"] == ""
    assert not (library.vault.root / f"{ref}.json").exists()
    assert (library.vault.root / f"{other_ref}.json").is_file()
    assert (library.vault.root / "notes.json").read_text(encoding="utf-8") == "user-file"

    errors: list[BaseException] = []

    def sweep() -> None:
        try:
            library.vault.sweep_expired_outbound()
            library.vault.sweep_expired_outbound()
        except BaseException as exc:  # noqa: BLE001 — the race must surface here
            errors.append(exc)

    threads = [threading.Thread(target=sweep) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert (library.vault.root / f"{other_ref}.json").is_file()
    library.close()


def test_job_ref_recovery_after_interrupted_cleanup(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite"
    library = Library(str(database))
    paused_id = library.create_job(SIGNED, [_row(PLAIN, "일시정지")])
    paused_item = library.items(paused_id)[0]["id"]
    paused_ref = str(_job_row(library, paused_id)["secret_ref"])
    (library.vault.root / f"{paused_ref}.json").unlink()
    done_id = library.create_job(OTHER, [_row(PLAIN, "완료")])
    done_item = library.items(done_id)[0]["id"]
    done_ref = str(_job_row(library, done_id)["secret_ref"])
    library.set_job_status(done_id, "완료")
    (library.vault.root / f"{done_ref}.json").write_text(
        json.dumps(
            {"job_id": done_id, "item_id": "", "urls": {"page": OTHER}, "expires_at": None}
        ),
        encoding="utf-8",
    )
    (library.vault.root / "notes.json").write_text("user-file", encoding="utf-8")
    library.close()

    restored = Library(str(database))
    paused = _job_row(restored, paused_id)
    done = _job_row(restored, done_id)
    assert paused["id"] == paused_id
    assert paused["status"] == "재인증 필요"
    assert paused["secret_ref"] == ""
    assert restored.items(paused_id)[0]["id"] == paused_item
    assert restored.items(paused_id)[0]["download_status"] == "일시정지"
    assert done["id"] == done_id
    assert done["status"] == "완료"
    assert done["secret_ref"] == ""
    assert restored.items(done_id)[0]["id"] == done_item
    assert not (restored.vault.root / f"{done_ref}.json").exists()
    assert (restored.vault.root / "notes.json").read_text(encoding="utf-8") == "user-file"
    assert f"job-reauth:{paused_id}" in restored.recovery
    restored.close()


def test_cleanup_logs_contain_no_secrets(tmp_path: Path) -> None:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.DEBUG)
    loggers = [logging.getLogger("umd.secrets"), logging.getLogger("umd.storage")]
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    captured = ""
    try:
        root = tmp_path / "vault"
        root.mkdir()
        broken = uuid4().hex
        (root / f"{broken}.json").write_text(
            f'{{"url":"{SIGNED}","cookie":"{COOKIE}","authorization":"{AUTH}"',
            encoding="utf-8",
        )
        expired = uuid4().hex
        (root / f"{expired}.json").write_text(
            json.dumps(
                {
                    "job_id": "outbound",
                    "item_id": expired,
                    "urls": {"value": SIGNED},
                    "expires_at": 1,
                }
            ),
            encoding="utf-8",
        )
        vault = SecretVault(root)
        try:
            vault.read(broken, job_id="outbound", item_id=broken)
        except SecretUnavailable as exc:
            captured = str(exc)
        vault.sweep_expired_outbound()
        library = Library(str(tmp_path / "library.sqlite"))
        job_id = library.create_job(SIGNED, [_row(PLAIN, "완료")])
        library.set_job_status(job_id, "완료")
        library.close()
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
    text = buffer.getvalue() + captured
    assert TOKEN not in text
    assert COOKIE not in text
    assert AUTH not in text
    assert SIGNED not in text
