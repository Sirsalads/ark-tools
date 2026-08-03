"""A.N.S Tools — entry point."""
from __future__ import annotations

import ctypes
import datetime
import pathlib
import sys
import traceback

# Per-monitor DPI awareness, v2. Qt sets this itself today, but the whole app
# leans on it: every coordinate it stores, moves the cursor to and reads pixels
# from is a PHYSICAL screen pixel, and without awareness Windows hands back
# virtualised ones on any display that is not at 100%. Stating it here makes the
# assumption the app's own, instead of a default that could change under it.
DPI_PER_MONITOR_V2 = -4

ROOT = pathlib.Path(__file__).resolve().parent
CRASH_LOG = ROOT / "state" / "startup-error.txt"

MB_ICONERROR = 0x10


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


def _report(problem: str) -> None:
    """
    Put a startup failure somewhere a person will actually find it.

    The app is launched with pythonw.exe, which has no console — that is what
    keeps a black window from sitting behind it for the whole session, and it
    also means anything raised on the way up goes nowhere at all. A machine
    where the app will not start showed a command window for a few seconds and
    then nothing, forever, with the reason written to a stream that does not
    exist.

    So it goes to two places that survive: a file next to the app, and a message
    box, because nobody reads a file they have not been told about.
    """
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        CRASH_LOG.write_text(f"{stamp}\n{sys.version}\n\n{problem}",
                             encoding="utf-8")
    except OSError:
        pass
    # Trimmed for the box: the file has all of it, and a wall of traceback in a
    # dialog is a wall nobody reads.
    tail = problem.strip().splitlines()[-1] if problem.strip() else "unknown"
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            f"A.N.S Tools could not start.\n\n{tail}\n\n"
            f"The whole reason is in:\n{CRASH_LOG}",
            "A.N.S Tools", MB_ICONERROR)
    except (AttributeError, OSError):
        print(problem, file=sys.stderr)


def main() -> int:
    _claim_dpi_awareness()
    # imported here, not at module scope: an import that fails — a broken
    # install, a half-written package — is exactly the failure this has to be
    # able to report, and a module-level import would take the reporter with it
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from arkmacro.ui import icons
    from arkmacro.ui import theme as T
    from arkmacro.ui.main_window import APP_NAME, MainWindow

    # no setFont here: the stylesheet's "*" rule sets family and size for
    # every widget, so an app font would only be dead weight
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(icons.pixmap("target", T.ACCENT, 64)))
    app.setStyleSheet(T.QSS)

    window = MainWindow()
    window.show()
    # a start that got this far is a start that worked, and the file must not
    # outlive the problem it describes
    CRASH_LOG.unlink(missing_ok=True)
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        _report(traceback.format_exc())
        sys.exit(1)
