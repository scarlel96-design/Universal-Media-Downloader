"""Keep QML shells alive until their worker threads return."""

from __future__ import annotations

_HELD_SHELLS: list[tuple] = []


def hold_shell(bundle, engine, win) -> None:
    """Retain the shell past the test function's local variables.

    Qt aborts if a QThread is destroyed while it is still running. Windows
    reports that abort as 0xC0000409, subcode FAST_FAIL_FATAL_APP_EXIT.
    """

    _HELD_SHELLS.append((bundle, engine, win))


def release_held_shells() -> None:
    if not _HELD_SHELLS:
        return
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance()
    while _HELD_SHELLS:
        bundle, _engine, win = _HELD_SHELLS.pop()
        shell = getattr(bundle, "shell", None)
        if shell is not None:
            try:
                shell.cancelDownload()
            except Exception:
                pass
            if app is not None:
                app.processEvents()
            try:
                shell.joinWorkers(None)
            except Exception:
                pass
        if win is not None:
            try:
                win.close()
            except Exception:
                pass
        if app is not None:
            app.processEvents()
