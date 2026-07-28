"""A.N.S Tools — entry point."""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from arkmacro.ui import icons
from arkmacro.ui import theme as T
from arkmacro.ui.main_window import APP_NAME, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(icons.pixmap("target", T.ACCENT, 64)))
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(T.QSS)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
