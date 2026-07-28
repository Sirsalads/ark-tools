"""A.N.S Tools — entry point."""
from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from arkmacro.ui import icons
from arkmacro.ui import theme as T
from arkmacro.ui.main_window import APP_NAME, MainWindow


def main() -> int:
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
