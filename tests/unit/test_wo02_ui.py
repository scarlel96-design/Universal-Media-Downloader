"""Download progress stays off the UI thread and can pause."""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from umd.app.shell import ShellBundle
from shell_hold import hold_shell
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


def wait_phase(qt_app, shell, expected: str, timeout: float = 8) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if shell.jobPhase == expected:
            return
        if expected not in {"실패", "취소", "일시정지"} and shell.jobPhase in {"실패", "취소"}:
            raise AssertionError(f"{shell.jobPhase}: {shell.toast}")
        time.sleep(0.02)
    raise AssertionError(f"timeout phase={shell.jobPhase} toast={shell.toast} line={shell.metricsLine}")


def open_shell(qt_app, db_path: Path):
    bundle = ShellBundle(db_path=str(db_path))
    engine = QQmlApplicationEngine()
    bundle.expose(engine)
    engine.load(QUrl.fromLocalFile(str(QML)))
    roots = engine.rootObjects()
    assert roots, "QML failed to load"
    win = roots[0]
    qt_app.processEvents()
    hold_shell(bundle, engine, win)
    return bundle, engine, win


def test_ui_stays_responsive_and_pause_resumes(lab: LabServer, app, tmp_path: Path):
    body = PNG + b"\x11" * 64

    def slow(_path, _query, _headers):
        return Reply(200, body, {"Content-Type": "image/png", "Content-Length": str(len(body))}, hold=0.7)

    lab.mount("/slow.png", slow)
    page = tmp_path / "page.html"
    page.write_text(
        f'<html><body><article><img src="{lab.url("/slow.png")}" alt="Slow"></article></body></html>',
        encoding="utf-8",
    )
    bundle, _engine, win = open_shell(app, tmp_path / "ui.sqlite")
    shell = bundle.shell
    win.setWidth(1280)
    win.setHeight(800)
    app.processEvents()
    shell.setUrl(page.as_uri())
    shell.analyze()
    wait_phase(app, shell, "추출 완료")
    dest = tmp_path / "out"
    dest.mkdir()
    shell.setDownloadDirectory(str(dest))
    shell.setDownloadMode("균형")
    started = time.perf_counter()
    shell.download()
    assert time.perf_counter() - started < 0.3
    assert shell.jobPhase == "다운로드 중"
    assert shell.metricsVisible is True
    assert shell.downloadMode == "균형"
    assert "계산 중" in shell.metricsLine
    assert shell.overallPercent == -1
    theme = shell.theme
    clicked = time.perf_counter()
    shell.toggleTheme()
    win.setWidth(1440)
    app.processEvents()
    assert time.perf_counter() - clicked < 0.3
    assert shell.theme != theme
    assert win.property("columnCount") == 4
    assert win.property("toolbarHeight") == 60
    assert win.property("hostMode") == "native-frame"
    shell.pauseDownload()
    app.processEvents()
    assert shell.jobPhase == "일시정지"
    shell.toggleTheme()
    app.processEvents()
    shell.resumeDownload()
    wait_phase(app, shell, "완료", timeout=8)
    assert shell.downloadOffUiThread is True
    files = [path for path in dest.iterdir() if not path.name.startswith(".")]
    assert len(files) == 1
    assert files[0].read_bytes() == body
    assert shell.doneCount == 1
    shell.joinWorkers()
    win.close()
