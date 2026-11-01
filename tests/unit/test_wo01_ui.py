import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from umd.app.shell import ShellBundle
from umd.storage.database import SCHEMA_VERSION
from wo01_support import EXPECTED, PHOTOS, base_url, serve

QML = Path(__file__).resolve().parents[2] / "src" / "umd" / "ui" / "qml" / "Main.qml"


@pytest.fixture(scope="module")
def server():
    httpd = serve()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def app():
    return QGuiApplication.instance() or QGuiApplication([])


def wait_phase(qt_app, shell, expected: str, timeout: float = 8) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if shell.jobPhase == expected:
            return
        if expected not in {"실패", "취소"} and shell.jobPhase in {"실패", "취소"}:
            raise AssertionError(f"{shell.jobPhase}: {shell.toast}")
        time.sleep(0.02)
    raise AssertionError(f"timeout phase={shell.jobPhase} toast={shell.toast}")


def open_shell(qt_app, db_path: Path):
    bundle = ShellBundle(db_path=str(db_path))
    engine = QQmlApplicationEngine()
    bundle.expose(engine)
    engine.load(QUrl.fromLocalFile(str(QML)))
    roots = engine.rootObjects()
    assert roots, "QML failed to load"
    win = roots[0]
    qt_app.processEvents()
    assert win.property("hostMode") == "native-frame"
    return bundle, engine, win


def test_07_user_can_select_an_uncertain_image(server, app, tmp_path: Path):
    bundle, _engine, win = open_shell(app, tmp_path / "uncertain.sqlite")
    shell = bundle.shell
    shell.setUrl(f"{base_url(server)}/article.html")
    shell.analyze()
    wait_phase(app, shell, "추출 완료")
    row = shell.findVisible("Widget")
    assert row >= 0
    assert shell.item_at(row)["classification"] == "uncertain"
    assert shell.item_at(row)["selected"] is False
    shell.activate(row)
    restored = shell.item_at(shell.findVisible("Widget"))
    assert restored["selected"] is True
    assert restored["classification"] == "uncertain"
    assert restored["override"] == "included"
    assert "판단 불확실" == shell.detailRelevance
    shell.joinWorkers()
    win.close()


def test_08_individual_and_bulk_selection(server, app, tmp_path: Path):
    bundle, _engine, win = open_shell(app, tmp_path / "select.sqlite")
    shell = bundle.shell
    shell.setUrl(f"{base_url(server)}/article.html")
    shell.analyze()
    wait_phase(app, shell, "추출 완료")
    content = len(EXPECTED["content"])
    uncertain = len(EXPECTED["uncertain"])
    excluded = len(EXPECTED["excluded"])
    assert shell.visibleCount == content + uncertain
    assert shell.selectedCount == content
    panel = shell.findVisible("Panel")
    shell.activate(panel)
    assert shell.item_at(shell.findVisible("Panel"))["selected"] is False
    assert shell.selectedCount == content - 1
    shell.activate(shell.findVisible("Panel"))
    assert shell.selectedCount == content
    shell.clearSelection()
    assert shell.selectedCount == 0
    shell.selectAllVisible()
    assert shell.selectedCount == shell.visibleCount == content + uncertain
    shell.clearSelection()
    shell.toggleShowExcluded()
    assert shell.visibleCount == content + uncertain + excluded
    sponsor = shell.findVisible("Sponsor")
    assert shell.item_at(sponsor)["classification"] == "excluded"
    assert shell.item_at(sponsor)["selected"] is False
    shell.activate(sponsor)
    assert shell.item_at(shell.findVisible("Sponsor"))["override"] == "included"
    shell.toggleShowExcluded()
    assert shell.findVisible("Sponsor") >= 0
    assert shell.item_at(shell.findVisible("Sponsor"))["selected"] is True
    assert shell.findVisible("Logo") < 0
    assert shell.visibleCount == content + uncertain + 1
    shell.joinWorkers()
    win.close()


def _completed_bytes(model) -> dict[str, bytes]:
    saved: dict[str, bytes] = {}
    for index in range(model.rowCount()):
        row = model.item(index)
        if row["status"] != "완료":
            continue
        name = urlsplit(row["mediaUrl"]).path.rsplit("/", 1)[-1]
        saved[name] = Path(row["savedPath"]).read_bytes()
    return saved


def test_09_selected_preview_rows_save_matching_bytes(server, app, tmp_path: Path):
    bundle, _engine, win = open_shell(app, tmp_path / "bytes.sqlite")
    shell = bundle.shell
    shell.setUrl(f"{base_url(server)}/article.html")
    shell.analyze()
    wait_phase(app, shell, "추출 완료")
    for index in range(bundle.model.rowCount()):
        row = bundle.model.item(index)
        if row["classification"] == "content":
            assert row["previewUrl"] == row["mediaUrl"]
            assert row["selected"] is True
    dest = tmp_path / "out"
    dest.mkdir()
    shell.setDownloadDirectory(str(dest))
    shell.download()
    wait_phase(app, shell, "완료", timeout=10)
    assert shell.downloadOffUiThread is True
    expect = {
        Path(spec["file"]).name: (PHOTOS / Path(spec["file"]).name).read_bytes()
        for spec in EXPECTED["content"]
    }
    assert _completed_bytes(bundle.model) == expect
    assert list(dest.glob("*.part")) == []
    shell.joinWorkers()
    win.close()


def test_12_sqlite_restores_the_finished_job(server, app, tmp_path: Path):
    database = tmp_path / "library.sqlite"
    dest = tmp_path / "out"
    dest.mkdir()
    bundle, _engine, win = open_shell(app, database)
    shell = bundle.shell
    shell.setUrl(f"{base_url(server)}/article.html")
    shell.analyze()
    wait_phase(app, shell, "추출 완료")
    shell.setDownloadDirectory(str(dest))
    shell.download()
    wait_phase(app, shell, "완료", timeout=10)
    job_id = shell._job_id
    shell.joinWorkers()
    win.close()
    app.processEvents()

    restored_bundle = ShellBundle(db_path=str(database))
    restored = restored_bundle.shell
    assert restored.usingSamples is False
    assert restored.jobPhase == "완료"
    assert restored._job_id == job_id
    assert restored.visibleCount == len(EXPECTED["content"]) + len(EXPECTED["uncertain"])
    assert restored.selectedCount == len(EXPECTED["content"])
    dot = next(item for item in restored_bundle.library.items(job_id) if item["title"] == "Dot")
    assert dot["download_status"] == "완료"
    assert Path(dot["saved_path"]).read_bytes() == (PHOTOS / "dot.png").read_bytes()
    assert restored_bundle.library.schema_version == SCHEMA_VERSION
    assert restored_bundle.library.integrity_issues() == []
    Path(dot["saved_path"]).unlink()
    assert restored_bundle.library.integrity_issues() == [f"missing:{dot['id']}"]
    restored_bundle.library.close()


def test_13_download_does_not_block_the_ui(server, app, tmp_path: Path):
    bundle, _engine, win = open_shell(app, tmp_path / "slow.sqlite")
    shell = bundle.shell
    win.setWidth(1280)
    win.setHeight(800)
    app.processEvents()
    shell.setUrl(f"{base_url(server)}/slow.html")
    shell.analyze()
    wait_phase(app, shell, "추출 완료")
    dest = tmp_path / "out"
    dest.mkdir()
    shell.setDownloadDirectory(str(dest))
    started = time.perf_counter()
    shell.download()
    assert time.perf_counter() - started < 0.3
    assert shell.jobPhase == "다운로드 중"
    theme = shell.theme
    clicked = time.perf_counter()
    shell.toggleTheme()
    win.setWidth(1440)
    app.processEvents()
    elapsed = time.perf_counter() - clicked
    assert elapsed < 0.3, elapsed
    assert shell.theme != theme
    assert win.width() == 1440
    assert win.property("columnCount") == 4
    assert win.property("toolbarHeight") == 60
    wait_phase(app, shell, "완료", timeout=8)
    assert shell.downloadOffUiThread is True
    files = [path for path in dest.iterdir() if not path.name.endswith(".part")]
    assert len(files) == 1
    assert files[0].read_bytes() == (PHOTOS / "panel.png").read_bytes()
    shell.joinWorkers()
    win.close()


def test_11_shell_records_http_failure(server, app, tmp_path: Path):
    bundle, _engine, win = open_shell(app, tmp_path / "bad.sqlite")
    shell = bundle.shell
    dest = tmp_path / "out"
    dest.mkdir()
    shell.setDownloadDirectory(str(dest))
    shell.setUrl(f"{base_url(server)}/bad.html")
    shell.analyze()
    wait_phase(app, shell, "추출 완료")
    shell.download()
    wait_phase(app, shell, "실패", timeout=8)
    assert shell.item_at(0)["status"] == "실패"
    assert "HTTP 404" in shell.item_at(0)["error"]
    assert list(dest.iterdir()) == []
    shell.joinWorkers()
    win.close()


def test_public_url_is_not_fetched(app, tmp_path: Path):
    bundle, _engine, win = open_shell(app, tmp_path / "public.sqlite")
    shell = bundle.shell
    shell.setUrl("https://example.com/post")
    shell.analyze()
    app.processEvents()
    assert shell.jobPhase == "대기"
    assert shell.usingSamples is True
    assert "127.0.0.1" in shell.toast
    shell.joinWorkers()
    win.close()
