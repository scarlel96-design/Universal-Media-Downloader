"""WO-REUSE-01-S2. Sweep progress is a filename cursor, not the first 64 entries."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

from umd.secrets import SecretUnavailable, SecretVault, is_reparse

TOKEN = "sig-" + uuid4().hex
COOKIE = "cookie-" + uuid4().hex
AUTH = "Bearer auth-" + uuid4().hex
SIGNED = f"https://cdn.example/media/a.png?sig={TOKEN}"
START = 10_000_000.0


def _clock() -> float:
    return START


def _outbound(root: Path, ref: str, *, expires: float, url: str = "https://cdn.example/keep") -> None:
    (root / f"{ref}.json").write_text(
        json.dumps(
            {"job_id": "outbound", "item_id": ref, "urls": {"value": url}, "expires_at": expires}
        ),
        encoding="utf-8",
    )


def _vault(root: Path) -> SecretVault:
    root.mkdir(parents=True, exist_ok=True)
    return SecretVault(root, clock=_clock)


def test_sweep_progresses_beyond_first_64_entries(tmp_path: Path) -> None:
    """Names sort non-expired refs first. The expired ref is lexicographically last."""

    root = tmp_path / "vault"
    vault = _vault(root)
    for index in range(70):
        _outbound(root, f"{index:032x}", expires=START + 100_000)
    expired = "f" * 32
    _outbound(root, expired, expires=START - 10, url=SIGNED)
    first = vault.sweep_expired_outbound()
    assert first == 0
    assert vault.sweep_stats["opened"] == 64
    assert (root / f"{expired}.json").is_file()
    cursor = (root / ".umd-sweep-cursor").read_text(encoding="utf-8").strip()
    assert cursor != f"{expired}.json"
    second = vault.sweep_expired_outbound()
    assert second == 1
    assert vault.sweep_stats["opened"] <= 64
    assert not (root / f"{expired}.json").exists()
    assert cursor != (root / ".umd-sweep-cursor").read_text(encoding="utf-8").strip()


def test_sweep_visits_all_expired_refs_across_batches(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    vault = _vault(root)
    refs = [f"{index:032x}" for index in range(200)]
    for ref in refs:
        _outbound(root, ref, expires=START - 5)
    removed = 0
    calls = 0
    cursor = ""
    while removed < 200 and calls < 8:
        removed += vault.sweep_expired_outbound()
        assert vault.sweep_stats["opened"] <= 64
        advanced = (root / ".umd-sweep-cursor").read_text(encoding="utf-8").strip()
        assert advanced != cursor
        cursor = advanced
        calls += 1
    assert removed == 200
    assert calls == 4
    assert not any((root / f"{ref}.json").exists() for ref in refs)


def test_sweep_preserves_nonexpired_and_durable_refs(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    vault = _vault(root)
    live = "1" * 32
    expired = "e" * 32
    job_ref = "a" * 32
    item_ref = "b" * 32
    _outbound(root, live, expires=START + 3600)
    _outbound(root, expired, expires=START - 1)
    (root / f"{job_ref}.json").write_text(
        json.dumps({"job_id": "job", "item_id": "", "urls": {"page": SIGNED}, "expires_at": None}),
        encoding="utf-8",
    )
    (root / f"{item_ref}.json").write_text(
        json.dumps(
            {"job_id": "job", "item_id": "item", "urls": {"media": SIGNED}, "expires_at": None}
        ),
        encoding="utf-8",
    )
    (root / "notes.json").write_text("user-file", encoding="utf-8")
    assert vault.sweep_expired_outbound() == 1
    assert not (root / f"{expired}.json").exists()
    assert (root / f"{live}.json").is_file()
    assert (root / f"{job_ref}.json").is_file()
    assert (root / f"{item_ref}.json").is_file()
    assert (root / "notes.json").read_text(encoding="utf-8") == "user-file"


def test_sweep_progress_survives_restart(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    first = _vault(root)
    for index in range(70):
        _outbound(root, f"{index:032x}", expires=START + 100_000)
    expired = "f" * 32
    _outbound(root, expired, expires=START - 10)
    assert first.sweep_expired_outbound() == 0
    saved = (root / ".umd-sweep-cursor").read_text(encoding="utf-8").strip()
    assert (root / f"{expired}.json").is_file()
    second = SecretVault(root, clock=_clock)
    assert not (root / f"{expired}.json").exists()
    assert (root / ".umd-sweep-cursor").read_text(encoding="utf-8").strip() != saved


def test_sweep_recovers_from_missing_cursor_target(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    vault = _vault(root)
    for index in range(70):
        _outbound(root, f"{index:032x}", expires=START + 100_000)
    expired = "f" * 32
    _outbound(root, expired, expires=START - 10)
    assert vault.sweep_expired_outbound() == 0
    cursor_name = (root / ".umd-sweep-cursor").read_text(encoding="utf-8").strip()
    (root / cursor_name).unlink()
    assert vault.sweep_expired_outbound() == 1
    assert not (root / f"{expired}.json").exists()


def test_sweep_concurrent_calls_preserve_refs(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    vault = _vault(root)
    active = vault.put_outbound("https://cdn.example/active")
    body = json.loads((root / f"{active}.json").read_text(encoding="utf-8"))
    body["expires_at"] = START - 5
    (root / f"{active}.json").write_text(json.dumps(body), encoding="utf-8")
    job_ref = vault.put("job", "", {"page": SIGNED})
    for index in range(30):
        _outbound(root, f"{index:032x}", expires=START - 5)
    (root / "notes.json").write_text("user-file", encoding="utf-8")
    errors: list[BaseException] = []

    def run() -> None:
        try:
            vault.sweep_expired_outbound()
        except BaseException as exc:  # noqa: BLE001 — concurrency must surface here
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert (root / f"{active}.json").is_file()
    assert (root / f"{job_ref}.json").is_file()
    assert (root / "notes.json").read_text(encoding="utf-8") == "user-file"
    leftover = [index for index in range(30) if (root / f"{index:032x}.json").exists()]
    for _ in range(8):
        if not leftover:
            break
        vault.sweep_expired_outbound()
        leftover = [index for index in range(30) if (root / f"{index:032x}.json").exists()]
    assert leftover == []
    assert (root / f"{active}.json").is_file()
    assert (root / f"{job_ref}.json").is_file()


def test_sweep_rejects_symlink_reparse_and_foreign_files(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    vault = _vault(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    foreign = outside / "foreign.json"
    foreign.write_text(SIGNED, encoding="utf-8")
    junction = root / "reparse-junction"
    subprocess.check_call(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], stdout=subprocess.DEVNULL)
    assert is_reparse(junction)
    link_error = ""
    link = root / f"{'c' * 32}.json"
    try:
        os.symlink(foreign, link)
    except OSError as exc:
        link_error = str(exc)
    broken = "d" * 32
    (root / f"{broken}.json").write_text(
        f'{{"url":"{SIGNED}","cookie":"{COOKIE}","authorization":"{AUTH}"',
        encoding="utf-8",
    )
    expired = "e" * 32
    _outbound(root, expired, expires=START - 5)
    assert vault.sweep_expired_outbound() == 1
    assert junction.exists()
    assert is_reparse(junction)
    assert foreign.read_text(encoding="utf-8") == SIGNED
    assert (root / f"{broken}.json").is_file()
    assert not (root / f"{expired}.json").exists()
    if not link_error:
        assert link.is_symlink()
        assert foreign.read_text(encoding="utf-8") == SIGNED
    else:
        assert "sig-" not in link_error or TOKEN not in link_error


def test_sweep_bounds_work_for_large_vault(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    vault = _vault(root)
    for index in range(4999):
        _outbound(root, f"{index:032x}", expires=START + 100_000)
    expired = "f" * 32
    _outbound(root, expired, expires=START - 5)
    samples = []
    elapsed_values: list[float] = []
    peak_values: list[int] = []
    removed = 0
    calls = 0
    while (root / f"{expired}.json").exists() and calls < 90:
        tracemalloc.start()
        started = time.perf_counter()
        removed += vault.sweep_expired_outbound()
        elapsed = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        stats = dict(vault.sweep_stats)
        assert stats["opened"] <= 64
        assert elapsed < 5
        elapsed_values.append(elapsed)
        peak_values.append(peak)
        if len(samples) < 3 or removed:
            samples.append({"elapsed_s": round(elapsed, 4), "peak_bytes": peak, **stats})
        calls += 1
    assert not (root / f"{expired}.json").exists()
    assert calls >= 79
    assert removed == 1
    assert samples[0]["opened"] == 64
    assert samples[0]["listed"] >= 5000
    assert samples[0]["peak_bytes"] < 20_000_000
    print(
        "S2_SWEEP_SAMPLES "
        + json.dumps(
            {
                "calls": calls,
                "min_elapsed_s": round(min(elapsed_values), 4),
                "max_elapsed_s": round(max(elapsed_values), 4),
                "max_peak_bytes": max(peak_values),
                "max_opened": max(item["opened"] for item in samples),
                "samples": samples,
            }
        )
    )


def test_sweep_logs_do_not_expose_secrets(tmp_path: Path, caplog) -> None:
    del caplog
    buffer_text: list[str] = []
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.emit = lambda record: buffer_text.append(record.getMessage())  # type: ignore[method-assign]
    logger = logging.getLogger("umd.secrets")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    captured = ""
    try:
        root = tmp_path / "vault"
        vault = _vault(root)
        (root / ".umd-sweep-cursor").write_text(SIGNED + "\n", encoding="utf-8")
        broken = "d" * 32
        (root / f"{broken}.json").write_text(
            f'{{"cookie":"{COOKIE}","authorization":"{AUTH}","url":"{SIGNED}"',
            encoding="utf-8",
        )
        _outbound(root, "e" * 32, expires=START - 5, url=SIGNED)
        try:
            vault.read(broken, job_id="outbound", item_id=broken)
        except SecretUnavailable as exc:
            captured = str(exc)
        vault.sweep_expired_outbound()
    finally:
        logger.removeHandler(handler)
    text = "\n".join(buffer_text) + captured
    assert TOKEN not in text
    assert COOKIE not in text
    assert AUTH not in text
    assert SIGNED not in text
