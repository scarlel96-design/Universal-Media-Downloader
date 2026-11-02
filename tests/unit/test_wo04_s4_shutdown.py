"""Quit while a worker is alive without destroying that QThread.

The video case does not open a public site. ``download_video`` is replaced
with a local stand-in that blocks until cancel arrives, then waits before
it returns. That is the delayed acknowledgement. A real yt-dlp child is not
started here.
"""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from shell_hold import hold_shell
from umd.app.shell import ShellBundle, row_from_candidate
from umd.download.video_job import TransferStop
from wo02_support import PNG, LabServer, Reply

QML = Path(__file__).resolve().parents[2] / "src" / "umd" / "ui" / "qml" / "Main.qml"


@pytest.fixture
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def lab():
    server = LabServer()
    yield server
    server.shutdown()


def _wait_until(app, predicate, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting")


def _load(app, db_path: Path):
    bundle = ShellBundle(db_path=str(db_path))
    engine = QQmlApplicationEngine()
    bundle.expose(engine)
    engine.load(QUrl.fromLocalFile(str(QML)))
    roots = engine.rootObjects()
    assert roots
    win = roots[0]
    app.processEvents()
    hold_shell(bundle, engine, win)
    return bundle.shell


def _row(url: str, title: str, *, kind: str = "image", selected: bool = True, status: str = "대기") -> dict:
    row = row_from_candidate(
        {
            "classification": "content",
            "url": url,
            "title": title,
            "reasons": [],
            "mediaType": kind,
            "delivery": "yt-dlp" if kind == "video" else "http",
        },
        "http://127.0.0.1/page",
    )
    row["selected"] = selected
    row["status"] = status
    return row


def _install(shell, rows: list[dict], directory: Path) -> str:
    job_id = shell._library.create_job("http://127.0.0.1/page", rows)
    shell._job_id = job_id
    shell._using_samples = False
    shell._model.replace(rows)
    shell.setDownloadDirectory(str(directory))
    return job_id


def _poke(shell) -> None:
    shell.download()
    shell.analyze()
    shell.retryFailed()
    shell.resumeDownload()


def test_finished_http_download_quits_without_killing_the_thread(lab: LabServer, app, tmp_path: Path):
    body = PNG + b"\x01\x02"

    def ready(_path, _query, _headers):
        return Reply(200, body, {"Content-Type": "image/png", "Content-Length": str(len(body))})

    lab.mount("/ok.png", ready)
    shell = _load(app, tmp_path / "ok.sqlite")
    dest = tmp_path / "out"
    dest.mkdir()
    _install(shell, [_row(lab.url("/ok.png"), "Ok")], dest)
    shell.download()
    _wait_until(app, lambda: shell.jobPhase == "완료")
    saved = [path for path in dest.iterdir() if path.suffix == ".png"]
    assert len(saved) == 1
    assert saved[0].read_bytes() == body
    thread = shell._download_thread
    assert thread is not None and not thread.isRunning()
    shell.shutdownForQuit()
    assert shell.jobPhase == "종료 중"
    assert shell.statusLine == "종료를 기다리는 중"
    shell.joinWorkers(None)
    assert not thread.isRunning()
    assert saved[0].is_file()
    assert saved[0].read_bytes() == body
    assert list(dest.glob("*.part")) == []


def test_blocked_read_quit_shows_wait_and_removes_the_part(lab: LabServer, app, tmp_path: Path):
    def slow(_path, _query, _headers):
        return Reply(200, PNG + b"\x03" * 32, {"Content-Type": "image/png"}, trickle=8)

    lab.mount("/slow.png", slow)
    shell = _load(app, tmp_path / "stall.sqlite")
    dest = tmp_path / "out"
    dest.mkdir()
    rows = [
        _row(lab.url("/slow.png"), "Slow"),
        _row(lab.url("/other.png"), "Failed", selected=False, status="실패"),
    ]
    job_id = _install(shell, rows, dest)
    shell.setUrl("http://127.0.0.1/page")
    shell.download()
    _wait_until(app, lambda: any(dest.glob("*.part")))
    thread = shell._download_thread
    assert thread is not None and thread.isRunning()
    shell.shutdownForQuit()
    assert shell.jobPhase == "종료 중"
    assert shell.statusLine == "종료를 기다리는 중"
    assert shell._banner == "종료를 기다리는 중"
    _poke(shell)
    assert shell._download_thread is thread
    assert shell._extract_thread is None or not shell._extract_thread.isRunning()
    assert "종료를 기다리는 중" in shell.toast
    QTimer.singleShot(0, lambda: _poke(shell))
    started = time.perf_counter()
    shell.joinWorkers(None)
    elapsed = time.perf_counter() - started
    assert elapsed < 4, elapsed
    assert not thread.isRunning()
    assert thread.isFinished()
    assert list(dest.glob("*.part")) == []
    assert [path for path in dest.iterdir() if path.suffix == ".png"] == []
    item = next(row for row in shell._library.items(job_id) if row["title"] == "Slow")
    assert item["download_status"] == "취소"
    assert item["saved_path"] == ""
    assert shell._download_thread is thread


def test_delayed_video_cancel_is_delivered_before_the_thread_ends(app, tmp_path: Path, monkeypatch):
    started = {"seen": False, "cancel": False}

    def delayed(_page, directory, *, format_id, should_stop, on_progress):
        part = Path(directory) / ".umd-video-delay.part"
        part.write_bytes(b"partial-video")
        started["seen"] = True
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if should_stop():
                started["cancel"] = True
                time.sleep(0.35)
                part.unlink(missing_ok=True)
                raise TransferStop("cancel")
            time.sleep(0.02)
        raise AssertionError("cancel was not delivered")

    monkeypatch.setattr("umd.download.video_job.download_video", delayed)
    shell = _load(app, tmp_path / "video.sqlite")
    dest = tmp_path / "out"
    dest.mkdir()
    job_id = _install(
        shell,
        [_row("http://127.0.0.1/watch", "Clip", kind="video")],
        dest,
    )
    shell.download()
    _wait_until(app, lambda: started["seen"])
    thread = shell._download_thread
    assert thread is not None and thread.isRunning()
    shell.shutdownForQuit()
    assert shell.statusLine == "종료를 기다리는 중"
    assert shell.jobPhase == "종료 중"
    QTimer.singleShot(0, lambda: _poke(shell))
    clock = time.perf_counter()
    shell.joinWorkers(None)
    elapsed = time.perf_counter() - clock
    assert started["cancel"] is True
    assert elapsed >= 0.3
    assert elapsed < 4
    assert not thread.isRunning()
    assert thread.isFinished()
    assert shell._download_thread is thread
    assert list(dest.glob("*.part")) == []
    item = shell._library.items(job_id)[0]
    assert item["download_status"] == "취소"
    assert item["saved_path"] == ""
    assert item["download_status"] != "완료"
