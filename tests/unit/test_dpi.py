import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CHILD = r"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from umd.app.shell import ShellBundle
app = QGuiApplication([])
bundle = ShellBundle()
engine = QQmlApplicationEngine()
bundle.expose(engine)
engine.load(QUrl.fromLocalFile(str(Path("src/umd/ui/qml/Main.qml").resolve())))
win = engine.rootObjects()[0]
win.setWidth(1440)
win.setHeight(900)
app.processEvents()
print(f"{win.devicePixelRatio():.2f} {int(win.property('sidebarWidth'))} {int(win.property('columnCount'))} {int(win.property('toolbarHeight'))}")
"""


@pytest.mark.parametrize("scale", ["1", "1.25", "1.5", "2"])
def test_logical_layout_survives_scale_factor(scale):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["QT_SCALE_FACTOR"] = scale
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    dpr, sidebar, columns, toolbar = proc.stdout.strip().split()
    assert abs(float(dpr) - float(scale)) < 0.02
    assert sidebar == "236"
    assert columns == "4"
    assert toolbar == "60"
