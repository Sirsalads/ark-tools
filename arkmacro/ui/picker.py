"""
Full-screen pickers, for one point and for an area.

Freezing the screen and letting the player click on a still frame — with a
magnifier under the cursor — beats a countdown timer: nothing moves, the
inventory stays open, and you can nudge pixel by pixel with the arrow keys
before committing.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .. import sweep
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


class AreaPicker(QWidget):
    """
    Overlay that returns one screen rectangle, in physical pixels.

    Drag a box over the slots you want emptied. The grid the sweep will actually
    follow is drawn inside the box as you drag, so the dots can be checked
    against the slot centres before anything is committed — that preview is the
    whole point of freezing the screen instead of typing four numbers.
    """

    picked = Signal(int, int, int, int)    # x, y, width, height
    cancelled = Signal()

    def __init__(self, shot: QPixmap, area: QRect, columns: int, rows: int,
                 origin: tuple[int, int] = (0, 0), label: str = "",
                 title: str = "", strip: bool = False,
                 ratio: float = 1.0, grid: bool = True) -> None:
        super().__init__(None)
        self._shot = shot
        self._columns = max(int(columns), 1)
        self._rows = max(int(rows), 1)
        # `origin` is this screen's top-left in Qt's LOGICAL coordinates, and
        # `ratio` is its device pixel ratio. Both are needed because the two
        # halves of this widget live in different spaces: mouse events arrive
        # logical, and everything the macro does later — moving the cursor,
        # reading pixels — is in PHYSICAL screen pixels. They only look alike
        # at 100% scaling, which is why mixing them survives a desktop and
        # falls apart on a laptop.
        self._origin = origin
        self._ratio = float(ratio) or 1.0
        self._label = label or f"HOLD-TO-DROP AREA · {self._columns} X "\
                               f"{self._rows}"
        self._title = title or "Drag a box over the slots to empty"
        # a strip is swept end to end and back, not covered row by row
        self._strip = strip
        # not every box is a path. The stop sign is a box the app will *look*
        # at, so drawing the dots a cursor would visit and calling them stops
        # would be describing something that never happens.
        self._grid = grid
        self._anchor: QPoint | None = None
        self._cursor = QPoint(area.width() // 2, area.height() // 2)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(area)

    # ------------------------------------------------------------ events
    def showEvent(self, event) -> None:
        super().showEvent(event)
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
        if event.button() != Qt.LeftButton:
            self._abort()
            return
        self._anchor = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._anchor is None:
            return
        self._cursor = event.position().toPoint()
        area = self._selection()
        if not sweep.usable(area):
            # a click instead of a drag: keep the overlay up rather than commit
            # a rectangle too small to hold a single slot
            self._anchor = None
            self.update()
            return
        self.hide()
        self.picked.emit(*area)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._abort()

    def _abort(self) -> None:
        self.hide()
        self.cancelled.emit()

    # ------------------------------------------------------------- model
    def _to_physical(self, point: QPoint) -> tuple[int, int]:
        """Widget point (logical) -> screen pixel (physical)."""
        return (round((point.x() + self._origin[0]) * self._ratio),
                round((point.y() + self._origin[1]) * self._ratio))

    def _selection(self) -> list[int]:
        """The dragged rectangle, in physical screen pixels."""
        if self._anchor is None:
            return [0, 0, 0, 0]
        first = self._to_physical(self._anchor)
        second = self._to_physical(self._cursor)
        return sweep.normalise(first[0], first[1], second[0], second[1])

    def _widget_rect(self) -> QRect:
        if self._anchor is None:
            return QRect()
        local = sweep.normalise(self._anchor.x(), self._anchor.y(),
                                self._cursor.x(), self._cursor.y())
        return QRect(local[0], local[1], local[2], local[3])

    # ------------------------------------------------------------- paint
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        rect = self.rect()
        painter.drawPixmap(rect, self._shot)
        painter.fillRect(rect, QColor(4, 8, 12, 110))

        box = self._widget_rect()
        if not box.isEmpty():
            # the selection shows the live screen, not the dimmed one
            painter.drawPixmap(box, self._shot, self._to_shot_rect(box))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(T.ERR), 2))
            painter.drawRect(box)
            if self._grid:
                self._paint_grid(painter, box)

        self._paint_crosshair(painter, rect)
        self._paint_banner(painter, rect, box)

    def _to_shot_rect(self, box: QRect) -> QRect:
        if not self.width() or not self.height():
            return box
        sx = self._shot.width() / self.width()
        sy = self._shot.height() / self.height()
        return QRect(round(box.x() * sx), round(box.y() * sy),
                     round(box.width() * sx), round(box.height() * sy))

    def _paint_grid(self, painter: QPainter, box: QRect) -> None:
        """The sweep path itself: the dots it visits, in the order it visits."""
        area = [box.x(), box.y(), box.width(), box.height()]
        path = (sweep.pingpong(area, self._columns) if self._strip
                else sweep.serpentine(area, self._columns, self._rows))
        if not path:
            return
        painter.setPen(QPen(QColor(T.ACCENT), 1, Qt.DashLine))
        for start, end in zip(path, path[1:]):
            painter.drawLine(start[0], start[1], end[0], end[1])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(T.ACCENT))
        for x, y in path:
            painter.drawEllipse(QPoint(x, y), 4, 4)
        # where the sweep starts, so a grid that is off by one row is obvious
        painter.setBrush(QColor(T.WARN))
        painter.drawEllipse(QPoint(*path[0]), 6, 6)

    def _paint_crosshair(self, painter: QPainter, rect: QRect) -> None:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(T.ACCENT), 1))
        painter.drawLine(self._cursor.x(), 0, self._cursor.x(), rect.height())
        painter.drawLine(0, self._cursor.y(), rect.width(), self._cursor.y())

    def _paint_banner(self, painter: QPainter, rect: QRect,
                      box: QRect) -> None:
        banner = QRect(rect.center().x() - 330, 46, 660, BANNER_H)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(16, 23, 34, 242))
        painter.drawRoundedRect(banner, 12, 12)
        painter.setPen(QPen(QColor(T.ACCENT_DEEP), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(banner, 12, 12)

        painter.setPen(QColor(T.ACCENT))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(banner.adjusted(22, 12, -22, 0), Qt.AlignLeft,
                         self._label)

        painter.setPen(QColor(T.TEXT))
        painter.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        painter.drawText(banner.adjusted(22, 28, -22, 0), Qt.AlignLeft,
                         self._title)

        if not self._grid:
            detail = (f"{box.width()} x {box.height()} px — keep it tight "
                      "around the icon, then release to confirm"
                      if not box.isEmpty() else
                      "Drag a box around the icon and nothing else. A box with "
                      "empty HUD in it matches half the screen. Esc cancels.")
        elif box.isEmpty():
            detail = ("Every dot is one stop the cursor will make. Drag from "
                      "one corner to the other. Esc cancels.")
        else:
            detail = (f"{box.width()} x {box.height()} px — check the dots land "
                      "on the slot centres, then release to confirm")
        painter.setPen(QColor(T.MUTED))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(banner.adjusted(22, 54, -22, -10),
                         Qt.AlignLeft | Qt.TextWordWrap, detail)
