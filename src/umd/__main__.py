"""Launch the native-frame QML shell."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication

    from umd.app.shell import ShellBundle

    app = QApplication(sys.argv)
    app.setApplicationName("Universal Media Downloader")
    app.setOrganizationName("UMD")
    folder = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UniversalMediaDownloader"
    bundle = ShellBundle(db_path=str(folder / "library.sqlite"))
    engine = QQmlApplicationEngine()
    bundle.expose(engine)
    qml = Path(__file__).resolve().parent / "ui" / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():
        return 1
    def _stop_workers() -> None:
        bundle.shell.cancelDownload()
        bundle.shell.joinWorkers(None)

    app.aboutToQuit.connect(_stop_workers)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
