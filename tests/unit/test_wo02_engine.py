"""WO-02 scheduler, resume, and migration tests. Local sockets only."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from pathlib import Path

import pytest

from umd.download.engine import DownloadEngine, DownloadItem, run_job
from umd.download.schedule import PRESETS, EngineConfig, HostBook, SlotGate, parse_retry_after, retry_delay
from umd.storage.database import SCHEMA_VERSION, Library
from wo02_support import PNG, LabServer, Reply, overlaps, unique_png

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def lab() -> LabServer:
    server = LabServer()
    yield server
    server.shutdown()


def _png_reply(body: bytes = PNG, hold: float = 0.0, trickle: float = 0.0) -> Reply:
    return Reply(200, body, {"Content-Type": "image/png", "ETag": '"same"'}, hold=hold, trickle=trickle)


def _items(urls: list[str], **kwargs) -> list[DownloadItem]:
    return [DownloadItem(item_id=f"item-{index}", url=url, **kwargs) for index, url in enumerate(urls)]


def _terminals(engine: DownloadEngine) -> dict[str, object]:
    found = {}
    for event in engine.events:
        if event.terminal:
            found[event.item_id] = event
    return found


def _quiet(lab: LabServer) -> None:
    lab.wait_idle()
    lab.reset_stats()


def test_presets_and_retry_delay_cap():
    assert PRESETS["안정"] == (4, 2)
    assert PRESETS["균형"] == (12, 3)
    assert PRESETS["고속"] == (24, 4)
    assert EngineConfig().limits() == (12, 3)
    assert retry_delay(1, "120", cap=8, base=0.2) == 8
    assert retry_delay(1, "0.4", cap=8, base=0.2) == 0.4
    assert parse_retry_after("nope") is None
    bare = retry_delay(3, None, cap=8, base=0.2)
    assert 0.2 * 4 <= bare <= 8


def test_gate_shrink_does_not_cancel_holders():
    async def scenario() -> None:
        gate = SlotGate(4)
        for _ in range(4):
            await gate.acquire()
        await gate.set_limit(2)

        async def extra() -> None:
            await gate.acquire()

        task = asyncio.create_task(extra())
        await asyncio.sleep(0.05)
        assert not task.done()
        await gate.release()
        await asyncio.sleep(0.05)
        assert not task.done()
        await gate.release()
        await gate.release()
        await asyncio.wait_for(task, 1)
        assert gate.active == 2
        assert gate.peak == 4

    asyncio.run(scenario())


def test_host_errors_lower_only_that_host():
    async def scenario() -> None:
        book = HostBook(4)
        first = await book.acquire("a")
        second = await book.acquire("b")
        await first.release()
        await second.release()
        for _ in range(3):
            await book.penalize("a")
        assert book.stats("a")[1] == 3
        assert book.stats("b")[1] == 4

    asyncio.run(scenario())


@pytest.mark.parametrize("limit", [4, 12, 24])
def test_parallel_presets_overlap_and_respect_the_cap(lab: LabServer, tmp_path: Path, limit: int):
    _quiet(lab)
    hold = 0.45

    def handler(_path, _query, _headers):
        return _png_reply(hold=hold)

    for index in range(limit):
        lab.mount(f"/p{limit}-{index}.png", handler)
    urls = [lab.url(f"/p{limit}-{index}.png") for index in range(limit)]
    started = time.perf_counter()
    engine = run_job(
        tmp_path,
        _items(urls),
        EngineConfig(global_limit=limit, per_host=limit, timeout=8, max_retries=2, backoff_base=0.05),
    )
    elapsed = time.perf_counter() - started
    stats = lab.snapshot()
    failed = [(event.item_id, event.error) for event in _terminals(engine).values() if event.status != "완료"]
    assert not failed, failed
    assert engine.peak_connections <= limit
    assert stats["peak_active"] <= limit
    assert stats["peak_active"] >= limit - 1
    assert overlaps(stats["spans"])
    assert elapsed < hold * 4


def test_per_host_cap(lab: LabServer, tmp_path: Path):
    _quiet(lab)

    def handler(_path, _query, _headers):
        return _png_reply(hold=0.3)

    for index in range(8):
        lab.mount(f"/host-{index}.png", handler)
    urls = [lab.url(f"/host-{index}.png") for index in range(8)]
    engine = run_job(
        tmp_path,
        _items(urls),
        EngineConfig(preset="균형", global_limit=12, per_host=2, timeout=5),
    )
    assert all(event.status == "완료" for event in _terminals(engine).values())
    assert lab.snapshot()["peak_active"] <= 2
    assert lab.snapshot()["peak_active"] >= 2


def test_two_hosts_keep_independent_caps(lab: LabServer, tmp_path: Path):
    other = LabServer()
    try:
        _quiet(lab)

        def handler(_path, _query, _headers):
            return _png_reply(hold=0.3)

        for index in range(4):
            lab.mount(f"/h1-{index}.png", handler)
            other.mount(f"/h2-{index}.png", handler)
        urls = [lab.url(f"/h1-{index}.png") for index in range(4)]
        urls += [f"http://localhost:{other.port}/h2-{index}.png" for index in range(4)]
        engine = run_job(
            tmp_path,
            _items(urls),
            EngineConfig(preset="고속", global_limit=8, per_host=2, timeout=5),
        )
        terminals = _terminals(engine)
        assert all(event.status == "완료" for event in terminals.values()), [event.error for event in terminals.values()]
        assert lab.snapshot()["peak_active"] <= 2
        assert other.snapshot()["peak_active"] <= 2
    finally:
        other.shutdown()


def test_retry_after_429_and_503_and_no_retry_on_404(lab: LabServer, tmp_path: Path):
    _quiet(lab)
    state = {"busy": 0, "down": 0}

    def busy(_path, _query, _headers):
        state["busy"] += 1
        if state["busy"] == 1:
            return Reply(429, b"later", {"Retry-After": "0.4", "Content-Type": "text/plain"})
        return _png_reply()

    def down(_path, _query, _headers):
        state["down"] += 1
        if state["down"] == 1:
            return Reply(503, b"down", {"Retry-After": "0.3", "Content-Type": "text/plain"})
        return _png_reply()

    def missing(_path, _query, _headers):
        return Reply(404, b"no", {"Content-Type": "text/plain"}, reason="Not Found")

    lab.mount("/busy.png", busy)
    lab.mount("/down.png", down)
    lab.mount("/gone.png", missing)
    started = time.perf_counter()
    engine = run_job(
        tmp_path,
        [
            DownloadItem("busy", lab.url("/busy.png")),
            DownloadItem("down", lab.url("/down.png")),
            DownloadItem("gone", lab.url("/gone.png")),
        ],
        EngineConfig(global_limit=3, per_host=3, timeout=5, backoff_base=0.05),
    )
    elapsed = time.perf_counter() - started
    terminals = _terminals(engine)
    assert terminals["busy"].status == "완료"
    assert terminals["busy"].retry_count >= 1
    assert terminals["down"].status == "완료"
    assert terminals["down"].retry_count >= 1
    assert terminals["gone"].status == "실패"
    assert terminals["gone"].error.startswith("HTTP 404")
    assert terminals["gone"].retry_count == 0
    assert elapsed >= 0.35
    assert lab.snapshot()["hits"]["/gone.png"] == 1
    assert lab.snapshot()["hits"]["/busy.png"] == 2


def test_timeout_truncated_body_and_bad_type(lab: LabServer, tmp_path: Path):
    _quiet(lab)

    def stall(_path, _query, _headers):
        return _png_reply(hold=0.8)

    def short(_path, _query, _headers):
        return Reply(200, PNG + b"0123456789", {"Content-Type": "image/png"}, truncate_to=8)

    def html(_path, _query, _headers):
        return Reply(200, b"<html>not an image</html>", {"Content-Type": "text/html"})

    lab.mount("/stall.png", stall)
    lab.mount("/short.png", short)
    lab.mount("/html.png", html)
    engine = run_job(
        tmp_path,
        [
            DownloadItem("stall", lab.url("/stall.png")),
            DownloadItem("short", lab.url("/short.png")),
            DownloadItem("html", lab.url("/html.png")),
        ],
        EngineConfig(global_limit=3, per_host=3, timeout=0.25, max_retries=0, backoff_base=0.01),
    )
    terminals = _terminals(engine)
    assert terminals["stall"].status == "실패"
    assert "시간" in terminals["stall"].error
    assert terminals["short"].status == "실패"
    assert "잘렸" in terminals["short"].error
    assert terminals["html"].status == "실패"
    assert "형식" in terminals["html"].error
    assert [path for path in tmp_path.iterdir() if not path.name.startswith(".")] == []
    time.sleep(0.6)


def test_range_resume_etag_change_and_non_resumable(lab: LabServer, tmp_path: Path):
    body = unique_png(7)
    changed = unique_png(8)

    def ok_range(_path, _query, headers):
        requested = headers.get("range")
        if not requested:
            return Reply(200, body, {"Content-Type": "image/png", "ETag": '"v1"', "Last-Modified": "Tue, 01 Nov 2026 00:00:00 GMT"})
        start = int(requested.split("=")[1].split("-")[0])
        part = body[start:]
        end = len(body) - 1
        return Reply(
            206,
            part,
            {
                "Content-Type": "image/png",
                "Content-Range": f"bytes {start}-{end}/{len(body)}",
                "ETag": '"v1"',
            },
        )

    def bad_range(_path, _query, headers):
        return Reply(
            206,
            body,
            {"Content-Type": "image/png", "Content-Range": f"bytes 0-{len(body) - 1}/{len(body)}", "ETag": '"v1"'},
        )

    def ignore_range(_path, _query, _headers):
        return Reply(200, body, {"Content-Type": "image/png", "ETag": '"v1"'})

    def etag_changed(_path, _query, headers):
        if headers.get("range"):
            return Reply(200, changed, {"Content-Type": "image/png", "ETag": '"v2"'})
        return Reply(200, changed, {"Content-Type": "image/png", "ETag": '"v2"'})

    lab.mount("/range.png", ok_range)
    lab.mount("/bad-range.png", bad_range)
    lab.mount("/full.png", ignore_range)
    lab.mount("/moved.png", etag_changed)

    part = tmp_path / ".umd-resume.part"
    part.write_bytes(body[:20])
    resumed = DownloadItem(
        "resume",
        lab.url("/range.png"),
        part_path=str(part),
        downloaded=20,
        total=len(body),
        etag='"v1"',
        resume_capable=1,
    )
    bad_part = tmp_path / ".umd-bad.part"
    bad_part.write_bytes(body[:20])
    bad = DownloadItem("bad", lab.url("/bad-range.png"), part_path=str(bad_part), downloaded=20, etag='"v1"')
    plain_part = tmp_path / ".umd-plain.part"
    plain_part.write_bytes(body[:15])
    plain = DownloadItem("plain", lab.url("/full.png"), part_path=str(plain_part), downloaded=15, etag='"v1"')
    moved_part = tmp_path / ".umd-moved.part"
    moved_part.write_bytes(body[:12])
    moved = DownloadItem("moved", lab.url("/moved.png"), part_path=str(moved_part), downloaded=12, etag='"v1"')
    engine = run_job(tmp_path, [resumed, bad, plain, moved], EngineConfig(global_limit=4, per_host=4, timeout=5))
    terminals = _terminals(engine)
    saved = Path(terminals["resume"].path)
    assert terminals["resume"].status == "완료"
    assert saved.read_bytes() == body
    assert terminals["resume"].resume_capable == 1
    assert terminals["bad"].status == "실패"
    assert "206" in terminals["bad"].error
    assert saved.read_bytes() != body + body
    assert terminals["plain"].status == "완료"
    assert terminals["plain"].note == "재개 불가"
    assert terminals["plain"].resume_capable == 0
    assert Path(terminals["plain"].path).read_bytes() == body
    assert terminals["moved"].status == "완료"
    assert terminals["moved"].note == "원본 변경"
    assert Path(terminals["moved"].path).read_bytes() == changed


def test_filename_race_does_not_overwrite(lab: LabServer, tmp_path: Path):
    def handler(path, query, _headers):
        index = int(query.split("=")[1])
        return _png_reply(unique_png(1000 + index))

    lab.mount("/dup/coast.png", handler)
    urls = [lab.url(f"/dup/coast.png?n={index}") for index in range(12)]
    engine = run_job(tmp_path, _items(urls), EngineConfig(preset="균형", timeout=5))
    assert all(event.status == "완료" for event in _terminals(engine).values())
    files = [path for path in tmp_path.iterdir() if not path.name.startswith(".")]
    assert len(files) == 12
    assert len({path.name for path in files}) == 12
    assert {path.read_bytes() for path in files} == {unique_png(1000 + index) for index in range(12)}


def test_cancel_and_pause_resume(lab: LabServer, tmp_path: Path):
    blob = PNG + b"\x00" * 120_000

    def trickle(_path, _query, _headers):
        return _png_reply(blob, trickle=0.01)

    lab.mount("/trickle.png", trickle)

    async def cancel_case() -> None:
        seen: list = []
        engine = DownloadEngine(
            tmp_path / "cancel",
            [DownloadItem("one", lab.url("/trickle.png"))],
            EngineConfig(timeout=5, max_retries=0),
            on_event=seen.append,
        )
        (tmp_path / "cancel").mkdir()

        async def stop() -> None:
            await asyncio.sleep(0.12)
            engine.request_cancel_all()

        await asyncio.gather(engine.run(), stop())
        engine.events = seen

    asyncio.run(cancel_case())
    cancel_dir = tmp_path / "cancel"
    finals = [path for path in cancel_dir.iterdir() if not path.name.startswith(".")]
    assert finals == []

    async def pause_case() -> DownloadEngine:
        seen: list = []
        folder = tmp_path / "pause"
        folder.mkdir()
        engine = DownloadEngine(
            folder,
            [DownloadItem("one", lab.url("/trickle.png"))],
            EngineConfig(timeout=8, max_retries=1, backoff_base=0.05),
            on_event=seen.append,
        )

        async def control() -> None:
            for _ in range(40):
                if any(event.downloaded > 0 for event in seen):
                    break
                await asyncio.sleep(0.05)
            engine.request_pause()
            for _ in range(40):
                if any(event.status == "일시정지" for event in seen):
                    break
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.15)
            engine.request_resume()

        await asyncio.gather(engine.run(), control())
        engine.events = seen
        return engine

    engine = asyncio.run(pause_case())
    done = [event for event in engine.events if event.terminal]
    assert done and done[-1].status == "완료", [event.status for event in done]
    assert any(event.status == "일시정지" for event in engine.events)
    assert Path(done[-1].path).read_bytes() == blob


def test_redirects_are_checked_and_secrets_are_not_repeated(lab: LabServer, tmp_path: Path):
    def blocked(_path, _query, _headers):
        return Reply(302, b"", {"Location": "https://example.com/secret.png"})

    def allowed(_path, _query, _headers):
        return Reply(302, b"", {"Location": "/landed.png"})

    def landed(_path, _query, _headers):
        return _png_reply()

    def denied(_path, _query, _headers):
        return Reply(401, b"no", {"Content-Type": "text/plain"})

    lab.mount("/away.png", blocked)
    lab.mount("/hop.png", allowed)
    lab.mount("/landed.png", landed)
    lab.mount("/auth.png", denied)
    secret = "s3cret-token"
    engine = run_job(
        tmp_path,
        [
            DownloadItem("away", lab.url("/away.png")),
            DownloadItem("hop", lab.url("/hop.png")),
            DownloadItem("auth", f"http://user:{secret}@{lab.url('/auth.png').split('://', 1)[1]}"),
        ],
        EngineConfig(global_limit=3, per_host=3, timeout=5, max_retries=0),
    )
    terminals = _terminals(engine)
    assert terminals["away"].status == "실패"
    assert "리다이렉트" in terminals["away"].error
    assert "example.com" not in terminals["away"].path
    assert terminals["hop"].status == "완료"
    assert Path(terminals["hop"].path).read_bytes() == PNG
    assert terminals["auth"].status == "실패"
    assert secret not in terminals["auth"].error
    blob = " ".join(event.error for event in engine.events)
    assert secret not in blob


def test_size_caps_and_priority(lab: LabServer, tmp_path: Path):
    def handler(path, _query, _headers):
        order.append(path)
        return _png_reply(hold=0.05)

    order: list[str] = []
    lab.mount("/big.png", lambda *_args: _png_reply(PNG + b"\x00" * 5000))
    for name in ("low", "mid", "high"):
        lab.mount(f"/{name}.png", handler)
    (tmp_path / "cap").mkdir()
    (tmp_path / "rank").mkdir()
    capped = run_job(
        tmp_path / "cap",
        [DownloadItem("big", lab.url("/big.png"))],
        EngineConfig(per_file_cap=1000, timeout=5, max_retries=0),
    )
    assert _terminals(capped)["big"].status == "실패"
    assert "상한" in _terminals(capped)["big"].error
    order.clear()
    ranked = run_job(
        tmp_path / "rank",
        [
            DownloadItem("low", lab.url("/low.png"), priority=0),
            DownloadItem("high", lab.url("/high.png"), priority=5),
            DownloadItem("mid", lab.url("/mid.png"), priority=1),
        ],
        EngineConfig(global_limit=1, per_host=1, timeout=5),
    )
    assert [event.status for event in _terminals(ranked).values()]
    assert order[:3] == ["/high.png", "/mid.png", "/low.png"]


def test_proxy_environment_is_not_used(lab: LabServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:9")
    lab.mount("/direct.png", lambda *_args: _png_reply())
    engine = run_job(tmp_path, [DownloadItem("one", lab.url("/direct.png"))], EngineConfig(timeout=3, max_retries=0))
    assert _terminals(engine)["one"].status == "완료"
    assert os.environ["ALL_PROXY"].startswith("socks5")


def test_sqlite_v1_migrates_without_dropping_rows(tmp_path: Path):
    database = tmp_path / "v1.sqlite"
    photo = tmp_path / "dot.png"
    photo.write_bytes(PNG)
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_meta (version INTEGER NOT NULL);
        INSERT INTO schema_meta(version) VALUES (1);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            page_url TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
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
            completed_at TEXT
        );
        """
    )
    connection.execute("PRAGMA user_version = 1")
    connection.execute(
        "INSERT INTO jobs(id, page_url, status, created_at, completed_at) VALUES ('job', 'http://127.0.0.1/a', '완료', 't', 't2')"
    )
    connection.execute(
        """
        INSERT INTO media_items (
            id, job_id, page_url, media_url, title, classification, reasons, selected,
            user_override, download_status, saved_path, byte_size, error, created_at, completed_at
        ) VALUES ('item', 'job', 'http://127.0.0.1/a', 'http://127.0.0.1/dot.png', 'Dot', 'content', '본문', 1, '', '완료', ?, ?, '', 't', 't2')
        """,
        (str(photo), len(PNG)),
    )
    connection.commit()
    connection.close()

    library = Library(str(database))
    assert library.schema_version == SCHEMA_VERSION == 2
    assert library._conn.execute("PRAGMA user_version").fetchone()[0] == 2
    items = library.items("job")
    assert len(items) == 1
    assert items[0]["title"] == "Dot"
    assert items[0]["download_status"] == "완료"
    assert items[0]["byte_size"] == len(PNG)
    assert int(items[0]["downloaded_bytes"]) == 0
    assert items[0]["retry_count"] == 0
    assert items[0]["etag"] == ""
    assert library.integrity_issues() == []
    photo.unlink()
    assert library.integrity_issues() == ["missing:item"]
    library.close()


def test_restart_reconciles_a_finished_file_and_resumes_a_partial(lab: LabServer, tmp_path: Path):
    body = unique_png(3)
    finished = tmp_path / "done.png"
    finished.write_bytes(body)
    database = tmp_path / "library.sqlite"
    library = Library(str(database))
    row = {
        "title": "Done",
        "mediaUrl": lab.url("/resume-me.png"),
        "classification": "content",
        "reasons": "본문",
        "selected": True,
        "status": "대기",
    }
    job_id = library.create_job(lab.url("/page"), [row])
    library.apply_transfer(
        row["itemId"],
        {
            "status": "다운로드 중",
            "path": str(finished),
            "size": len(body),
            "downloaded_bytes": len(body),
            "total_size": len(body),
            "etag": '"v1"',
        },
    )
    library.set_job_status(job_id, "다운로드 중")
    partial_row = {
        "title": "Part",
        "mediaUrl": lab.url("/resume-me.png"),
        "classification": "content",
        "reasons": "본문",
        "selected": True,
        "status": "대기",
    }
    library.create_job(lab.url("/page-2"), [partial_row])
    part = tmp_path / ".umd-keep.part"
    part.write_bytes(body[:25])
    library.apply_transfer(
        partial_row["itemId"],
        {
            "status": "다운로드 중",
            "part_path": str(part),
            "downloaded_bytes": 25,
            "total_size": len(body),
            "etag": '"v1"',
            "resume_capable": 1,
        },
    )
    library.close()

    restored = Library(str(database))
    assert any(note.startswith("reconciled:") for note in restored.recovery)
    assert any(note.startswith("incomplete:") for note in restored.recovery)
    done = restored.items(job_id)[0]
    assert done["download_status"] == "완료"
    assert restored.integrity_issues() == []
    assert restored.latest_job()["status"] in {"다운로드 중", "추출 완료", "완료"}
    rows = restored.rows_for(restored.latest_job()["id"])
    part_row = rows[0]
    assert part_row["status"] == "다운로드 중"
    assert part_row["partPath"]
    restored.close()

    def ok_range(_path, _query, headers):
        requested = headers.get("range")
        start = int(requested.split("=")[1].split("-")[0]) if requested else 0
        if not requested:
            return Reply(200, body, {"Content-Type": "image/png", "ETag": '"v1"'})
        chunk = body[start:]
        return Reply(
            206,
            chunk,
            {
                "Content-Type": "image/png",
                "Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}",
                "ETag": '"v1"',
            },
        )

    lab.mount("/resume-me.png", ok_range)
    (tmp_path / "out").mkdir()
    engine = run_job(
        tmp_path / "out",
        [
            DownloadItem(
                part_row["itemId"],
                part_row["fetchUrl"],
                part_path=part_row["partPath"],
                downloaded=25,
                total=len(body),
                etag='"v1"',
                resume_capable=1,
            )
        ],
        EngineConfig(timeout=5),
    )
    event = _terminals(engine)[part_row["itemId"]]
    assert event.status == "완료", event.error
    assert Path(event.path).read_bytes() == body
