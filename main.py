"""A.N.S Tools — entry point."""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from arkmacro.ui import icons
from arkmacro.ui import theme as T
from arkmacro.ui.main_window import APP_NAME, MainWindow

# Per-monitor DPI awareness, v2. Qt sets this itself today, but the whole app
# leans on it: every coordinate it stores, moves the cursor to and reads pixels
# from is a PHYSICAL screen pixel, and without awareness Windows hands back
# virtualised ones on any display that is not at 100%. Stating it here makes the
# assumption the app's own, instead of a default that could change under it.
DPI_PER_MONITOR_V2 = -4


def _claim_dpi_awareness() -> None:
    user32 = getattr(ctypes, "windll", None)
    if user32 is None:              # not Windows: nothing to claim
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(DPI_PER_MONITOR_V2)
    except (AttributeError, OSError):
        # older than Windows 10 1703, or already set by something else — the
        # call failing is not a reason to refuse to start
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main() -> int:
    _claim_dpi_awareness()
    # no setFont here: the stylesheet's "*" rule sets family and size for
    # every widget, so an app font would only be dead weight
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(icons.pixmap("target", T.ACCENT, 64)))
    app.setStyleSheet(T.QSS)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
