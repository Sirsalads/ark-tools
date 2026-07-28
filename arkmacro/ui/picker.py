"""
Full-screen point picker.

Freezing the screen and letting the player click on a still frame — with a
magnifier under the cursor — beats a countdown timer: nothing moves, the
inventory stays open, and you can nudge pixel by pixel with the arrow keys
before committing.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .. import winapi as w
from . import theme as T

LOUPE = 190          # magnifier box, in widget pixels
ZOOM = 5             # magnification factor
BANNER_H = 96


class ScreenPicker(QWidget):
    """Overlay that returns one screen coordinate, in physical pixels."""

    picked = Signal(int, int)
    cancelled = Signal()

    def __init__(self, shot: QPixmap, area: QRect, title: str, subtitle: str,
                 step: str = "") -> None:
        super().__init__(None)
        self._shot = shot
        self._title = title
        self._subtitle = subtitle
        self._step = step
        self._cursor = QPoint(area.width() // 2, area.height() // 2)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setCursor(Qt.BlankCursor)
        self.setMouseTracking(True)
        self.setGeometry(area)

    # ------------------------------------------------------------ events
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # start the crosshair wherever the pointer already is, otherwise the
        # first frame draws it in the middle while the readout says elsewhere
        self._cursor = self.mapFromGlobal(QCursor.pos())
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)
        self.grabKeyboard()

    def hideEvent(self, event) -> None:
        self.releaseKeyboard()
        super().hideEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._cursor = event.position().toPoint()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._commit()
        else:
            self._abort()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self._abort()
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._commit()
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            dx = (key == Qt.Key_Right) - (key == Qt.Key_Left)
            dy = (key == Qt.Key_Down) - (key == Qt.Key_Up)
            x, y = w.get_cursor_pos()
            w.move_cursor(x + dx * step, y + dy * step)

    def _commit(self) -> None:
        # the owner disposes of us; closing here would free the object while
        # the signal is still being delivered
        x, y = w.get_cursor_pos()
        self.hide()
        self.picked.emit(x, y)

    def _abort(self) -> None:
        self.hide()
        self.cancelled.emit()

    # ------------------------------------------------------------- paint
    def _to_shot(self, point: QPoint) -> QPoint:
        """Widget point -> pixel inside the captured screenshot."""
        if not self.width() or not self.height():
            return point
        return QPoint(round(point.x() * self._shot.width() / self.width()),
                      round(point.y() * self._shot.height() / self.height()))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        rect = self.rect()
        painter.drawPixmap(rect, self._shot)
        painter.fillRect(rect, QColor(4, 8, 12, 96))

        cursor = self._cursor
        accent = QColor(T.ACCENT)

        # crosshair across the whole screen
        pen = QPen(accent)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(cursor.x(), 0, cursor.x(), rect.height())
        painter.drawLine(0, cursor.y(), rect.width(), cursor.y())

        self._paint_loupe(painter, cursor)
        self._paint_banner(painter, rect)

    def _paint_loupe(self, painter: QPainter, cursor: QPoint) -> None:
        margin = 26
        box = QRect(cursor.x() + margin, cursor.y() + margin, LOUPE, LOUPE + 26)
        if box.right() > self.width() - 8:
            box.moveLeft(cursor.x() - margin - LOUPE)
        if box.bottom() > self.height() - 8:
            box.moveTop(cursor.y() - margin - LOUPE - 26)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(T.BG))
        painter.drawRoundedRect(box, 10, 10)

        view = QRect(box.x() + 5, box.y() + 5, LOUPE - 10, LOUPE - 10)
        span = max(view.width() // ZOOM, 4)
        center = self._to_shot(cursor)
        source = QRect(center.x() - span // 2, center.y() - span // 2, span, span)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        # near a screen edge the source runs past the screenshot; draw only the
        # part that exists, in its proportional place, so the crosshair keeps
        # telling the truth about which pixel is under it
        visible = source.intersected(self._shot.rect())
        painter.fillRect(view, QColor(T.INK))
        if not visible.isEmpty():
            scale = view.width() / source.width()
            painter.drawPixmap(
                QRectF(view.x() + (visible.x() - source.x()) * scale,
                       view.y() + (visible.y() - source.y()) * scale,
                       visible.width() * scale, visible.height() * scale),
                self._shot, QRectF(visible))

        # center marker of the magnifier
        mid = view.center()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(T.ACCENT), 1))
        painter.drawLine(mid.x(), view.top(), mid.x(), view.bottom())
        painter.drawLine(view.left(), mid.y(), view.right(), mid.y())
        painter.setPen(QPen(QColor(T.WARN), 2))
        painter.drawRect(mid.x() - ZOOM // 2 - 1, mid.y() - ZOOM // 2 - 1,
                         ZOOM + 2, ZOOM + 2)

        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.drawRoundedRect(box, 10, 10)

        physical = w.get_cursor_pos()
        painter.setPen(QColor(T.TEXT_DIM))
        painter.setFont(QFont("Consolas", 9))
        painter.drawText(QRect(box.x(), box.bottom() - 24, box.width(), 20),
                         Qt.AlignCenter, f"x {physical[0]}    y {physical[1]}")

    def _paint_banner(self, painter: QPainter, rect: QRect) -> None:
        banner = QRect(rect.center().x() - 330, 46, 660, BANNER_H)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(16, 23, 34, 242))
        painter.drawRoundedRect(banner, 12, 12)
        painter.setPen(QPen(QColor(T.ACCENT_DEEP), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(banner, 12, 12)

        if self._step:
            painter.setPen(QColor(T.ACCENT))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(banner.adjusted(22, 12, -22, 0), Qt.AlignLeft,
                             self._step.upper())

        painter.setPen(QColor(T.TEXT))
        painter.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        painter.drawText(banner.adjusted(22, 28, -22, 0), Qt.AlignLeft,
                         self._title)

        painter.setPen(QColor(T.MUTED))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(banner.adjusted(22, 54, -22, -10),
                         Qt.AlignLeft | Qt.TextWordWrap, self._subtitle)
