import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

from pathlib import Path

import pytest
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from umd.app.host import native_window_flags, uses_frameless
from umd.app.shell import ShellBundle

QML = Path(__file__).resolve().parents[2] / "src" / "umd" / "ui" / "qml" / "Main.qml"


@pytest.fixture(scope="module")
def window():
    app = QGuiApplication.instance() or QGuiApplication([])
    bundle = ShellBundle()
    engine = QQmlApplicationEngine()
    bundle.expose(engine)
    shell = bundle.shell
    engine.load(QUrl.fromLocalFile(str(QML)))
    roots = engine.rootObjects()
    assert roots, "QML failed to load"
    win = roots[0]
    app.processEvents()
    yield app, win, shell
    win.close()


def test_native_flags_are_not_frameless(window):
    app, win, _shell = window
    flags = win.flags()
    assert not uses_frameless(flags)
    expected = native_window_flags()
    for hint in (
        Qt.WindowType.WindowMinimizeButtonHint,
        Qt.WindowType.WindowMaximizeButtonHint,
        Qt.WindowType.WindowCloseButtonHint,
        Qt.WindowType.WindowSystemMenuHint,
    ):
        assert flags & hint
        assert expected & hint
    assert not (flags & Qt.WindowType.CustomizeWindowHint)
    assert win.property("hostMode") == "native-frame"
    app.processEvents()


def test_layout_at_required_sizes(window):
    app, win, shell = window
    shell.setReduceMotion(True)
    cases = (
        (1440, 900, 236, 4),
        (1280, 800, 236, 4),
        (1024, 768, 196, 3),
    )
    for width, height, sidebar, columns in cases:
        win.setWidth(width)
        win.setHeight(height)
        app.processEvents()
        assert win.property("toolbarHeight") == 60
        assert win.property("sidebarWidth") == sidebar
        assert win.property("columnCount") == columns
        assert win.property("inspectorWidth") == 0
    shell.toggleInspector()
    app.processEvents()
    assert win.width() == 1024
    assert win.property("inspectorWidth") == 265
    win.setWidth(1440)
    win.setHeight(900)
    app.processEvents()
    assert win.property("inspectorWidth") == 298
    shell.toggleSidebar()
    app.processEvents()
    assert win.property("sidebarWidth") == 0
    shell.toggleSidebar()
    shell.toggleInspector()
    shell.setReduceMotion(False)


def test_reduce_motion_flag(window):
    _app, win, shell = window
    shell.setReduceMotion(True)
    assert shell.reduceMotion is True
    assert win.property("motionEnabled") is False
    shell.setReduceMotion(False)
    assert win.property("motionEnabled") is True


def test_filter_and_selection(window):
    _app, _win, shell = window
    assert shell.visibleCount == 12
    assert shell.selectedCount == 10
    shell.setFilter("video")
    assert shell.visibleCount == 2
    assert shell.selectedCount == 1
    shell.setFilter("image")
    assert shell.visibleCount == 10
    shell.setFilter("all")
    shell.selectAllVisible()
    assert shell.selectedCount == 12
    shell.activate(0)
    assert shell.inspectorOpen is True
    assert shell.detailTitle
    shell.analyze()
    assert "연결되지 않았습니다" in shell.toast or "없습니다" in shell.toast
    shell.download()
    assert "저장하지 않습니다" in shell.toast
