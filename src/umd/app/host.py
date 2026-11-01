"""Native Windows frame. The shell does not take over caption buttons."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt


def native_window_flags() -> Qt.WindowType:
    """System caption, system menu, and resize frame.

    FramelessWindowHint and CustomizeWindowHint are omitted on purpose.
    CustomizeWindowHint can drop Snap Layouts and the system menu.
    """

    return (
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMinimizeButtonHint
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowCloseButtonHint
    )


def uses_frameless(flags: Qt.WindowType) -> bool:
    return bool(flags & Qt.WindowType.FramelessWindowHint)


def windows_reduce_motion() -> bool:
    """True when Windows client-area animation is switched off.

    This reads SPI_GETCLIENTAREAANIMATION. It does not scan user documents.
    """

    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    enabled = wintypes.BOOL()
    ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
    if not ok:
        return False
    return not bool(enabled.value)
