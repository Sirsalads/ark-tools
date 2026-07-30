"""
Vector icons drawn with QPainter.

Font glyphs were a lottery — different Windows builds substitute different
symbol fonts and some render as tofu. These are paths, so they look identical
everywhere and can be tinted per state.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

GRID = 24.0   # every icon is authored on a 24x24 canvas


def _stroke(painter: QPainter, color: QColor, width: float = 1.8) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)


def _dot(painter: QPainter, color: QColor, x: float, y: float, r: float) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(x, y), r, r)


def _grid(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color)
    for x, y in ((3.5, 3.5), (13.5, 3.5), (3.5, 13.5), (13.5, 13.5)):
        painter.drawRoundedRect(QRectF(x, y, 7, 7), 2, 2)


def _mouse(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color)
    painter.drawRoundedRect(QRectF(7, 2.5, 10, 19), 5, 5)
    painter.drawLine(QPointF(12, 2.5), QPointF(12, 9))
    _dot(painter, color, 12, 6, 1.0)


def _list(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    for y in (5.5, 12.0, 18.5):
        painter.drawRoundedRect(QRectF(3, y - 2, 4, 4), 1, 1)
        painter.drawLine(QPointF(10.5, y), QPointF(21, y))


def _target(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color)
    painter.drawEllipse(QPointF(12, 12), 7, 7)
    for x1, y1, x2, y2 in ((12, 1.5, 12, 5), (12, 19, 12, 22.5),
                           (1.5, 12, 5, 12), (19, 12, 22.5, 12)):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    _dot(painter, color, 12, 12, 1.6)


def _sliders(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    for y, knob in ((6.0, 15.5), (12.0, 8.5), (18.0, 16.5)):
        painter.drawLine(QPointF(3, y), QPointF(21, y))
        _dot(painter, color, knob, y, 2.4)


def _terminal(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    painter.drawRoundedRect(QRectF(2.5, 4, 19, 16), 3, 3)
    path = QPainterPath(QPointF(6.5, 10))
    path.lineTo(9.5, 13.2)
    path.lineTo(6.5, 16.4)
    painter.drawPath(path)
    painter.drawLine(QPointF(12.5, 16.4), QPointF(17.5, 16.4))


def _play(painter: QPainter, color: QColor) -> None:
    path = QPainterPath(QPointF(8, 5))
    path.lineTo(18.5, 12)
    path.lineTo(8, 19)
    path.closeSubpath()
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)


def _stop(painter: QPainter, color: QColor) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(7, 7, 10, 10), 2, 2)


def _search(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color)
    painter.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
    painter.drawLine(QPointF(15.4, 15.4), QPointF(20, 20))


def _warning(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    path = QPainterPath(QPointF(12, 3.5))
    path.lineTo(21.5, 20)
    path.lineTo(2.5, 20)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(12, 9.5), QPointF(12, 14))
    _dot(painter, color, 12, 17, 1.1)


def _chevron_up(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 2.0)
    path = QPainterPath(QPointF(6, 14.5))
    path.lineTo(12, 8.5)
    path.lineTo(18, 14.5)
    painter.drawPath(path)


def _chevron_down(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 2.0)
    path = QPainterPath(QPointF(6, 9.5))
    path.lineTo(12, 15.5)
    path.lineTo(18, 9.5)
    painter.drawPath(path)


def _plus(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 2.0)
    painter.drawLine(QPointF(12, 5), QPointF(12, 19))
    painter.drawLine(QPointF(5, 12), QPointF(19, 12))


def _trash(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    painter.drawLine(QPointF(3.5, 6.5), QPointF(20.5, 6.5))
    painter.drawPath(_rounded_bin())
    painter.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 3.5))
    painter.drawLine(QPointF(9.5, 3.5), QPointF(14.5, 3.5))
    painter.drawLine(QPointF(14.5, 3.5), QPointF(14.5, 6.5))


def _rounded_bin() -> QPainterPath:
    path = QPainterPath(QPointF(5.5, 6.5))
    path.lineTo(6.5, 19.5)
    path.quadTo(6.6, 21, 8, 21)
    path.lineTo(16, 21)
    path.quadTo(17.4, 21, 17.5, 19.5)
    path.lineTo(18.5, 6.5)
    return path


def _check(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 2.2)
    path = QPainterPath(QPointF(5, 12.5))
    path.lineTo(10, 17.5)
    path.lineTo(19, 6.5)
    painter.drawPath(path)


def _minimize(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.6)
    painter.drawLine(QPointF(5, 12), QPointF(19, 12))


def _close(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.6)
    painter.drawLine(QPointF(6.5, 6.5), QPointF(17.5, 17.5))
    painter.drawLine(QPointF(17.5, 6.5), QPointF(6.5, 17.5))


def _gauge(painter: QPainter, color: QColor) -> None:
    """Dashboard: a dial with its needle."""
    _stroke(painter, color, 1.7)
    path = QPainterPath()
    path.arcMoveTo(QRectF(2.5, 4.5, 19, 19), 200)
    path.arcTo(QRectF(2.5, 4.5, 19, 19), 200, -220)
    painter.drawPath(path)
    painter.drawLine(QPointF(12, 14), QPointF(16.5, 9.5))
    _dot(painter, color, 12, 14, 1.5)


def _pickaxe(painter: QPainter, color: QColor) -> None:
    """
    Farm: the swing that pays for everything else.

    The head arc has to sag hard. A shallow one reads as a plain bar at 18px,
    and the whole icon turns into a letter T.
    """
    _stroke(painter, color, 1.9)
    painter.drawLine(QPointF(5, 20.5), QPointF(14.5, 8))
    blade = QPainterPath(QPointF(12.2, 4.2))
    blade.lineTo(20.5, 8.6)
    blade.lineTo(16.6, 13.4)
    blade.lineTo(10.6, 7.4)
    blade.closeSubpath()
    painter.drawPath(blade)


def _hand_drop(painter: QPainter, color: QColor) -> None:
    """
    Drop: a stack leaving, and the floor it lands on.

    Read at 18px this is an arrow onto a line, which is the one shape everybody
    already reads as "put this down".
    """
    _stroke(painter, color, 1.9)
    painter.drawLine(QPointF(12, 3), QPointF(12, 15.5))
    path = QPainterPath(QPointF(7, 10.5))
    path.lineTo(12, 15.6)
    path.lineTo(17, 10.5)
    painter.drawPath(path)
    painter.drawLine(QPointF(4.5, 20.5), QPointF(19.5, 20.5))


def _layers(painter: QPainter, color: QColor) -> None:
    """Overcap: one thing stacked on another."""
    _stroke(painter, color, 1.7)
    for offset in (0, 5.5):
        path = QPainterPath(QPointF(12, 3 + offset))
        path.lineTo(20.5, 7.5 + offset)
        path.lineTo(12, 12 + offset)
        path.lineTo(3.5, 7.5 + offset)
        path.closeSubpath()
        painter.drawPath(path)


def _keyboard(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.6)
    painter.drawRoundedRect(QRectF(2, 5.5, 20, 13), 2.5, 2.5)
    for x in (5.5, 9, 12.5, 16):
        _dot(painter, color, x, 9.5, 0.9)
    for x in (6.5, 10, 13.5, 17)[:3]:
        _dot(painter, color, x, 12.5, 0.9)
    painter.drawLine(QPointF(8, 15.5), QPointF(16, 15.5))
    _dot(painter, color, 18.5, 9.5, 0.9)


def _bolt(painter: QPainter, color: QColor) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    path = QPainterPath(QPointF(13.5, 2))
    path.lineTo(6, 13)
    path.lineTo(11, 13)
    path.lineTo(10.5, 22)
    path.lineTo(18, 11)
    path.lineTo(13, 11)
    path.closeSubpath()
    painter.drawPath(path)


def _clock(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    painter.drawEllipse(QPointF(12, 12), 9, 9)
    painter.drawLine(QPointF(12, 6.5), QPointF(12, 12))
    painter.drawLine(QPointF(12, 12), QPointF(16, 14.5))


def _shield(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    path = QPainterPath(QPointF(12, 2.5))
    path.lineTo(20, 5.8)
    path.lineTo(20, 12)
    path.quadTo(20, 18.5, 12, 21.5)
    path.quadTo(4, 18.5, 4, 12)
    path.lineTo(4, 5.8)
    path.closeSubpath()
    painter.drawPath(path)
    path = QPainterPath(QPointF(8.5, 11.8))
    path.lineTo(11, 14.4)
    path.lineTo(15.5, 9)
    painter.drawPath(path)


def _eye(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.7)
    path = QPainterPath(QPointF(2, 12))
    path.quadTo(12, 4, 22, 12)
    path.quadTo(12, 20, 2, 12)
    painter.drawPath(path)
    painter.drawEllipse(QPointF(12, 12), 3.2, 3.2)


def _refresh(painter: QPainter, color: QColor) -> None:
    _stroke(painter, color, 1.8)
    path = QPainterPath()
    path.arcMoveTo(QRectF(3.5, 3.5, 17, 17), 70)
    path.arcTo(QRectF(3.5, 3.5, 17, 17), 70, 260)
    painter.drawPath(path)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    head = QPainterPath(QPointF(14.5, 2.5))
    head.lineTo(19.5, 5.5)
    head.lineTo(14, 8)
    head.closeSubpath()
    painter.drawPath(head)


def _cursor(painter: QPainter, color: QColor) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    path = QPainterPath(QPointF(6, 3))
    path.lineTo(6, 18.5)
    path.lineTo(10, 14.8)
    path.lineTo(12.6, 21)
    path.lineTo(15.4, 19.7)
    path.lineTo(12.9, 13.8)
    path.lineTo(18, 13.2)
    path.closeSubpath()
    painter.drawPath(path)


DRAW = {
    "grid": _grid,
    "gauge": _gauge,
    "pickaxe": _pickaxe,
    "hand-drop": _hand_drop,
    "layers": _layers,
    "keyboard": _keyboard,
    "bolt": _bolt,
    "clock": _clock,
    "shield": _shield,
    "eye": _eye,
    "refresh": _refresh,
    "cursor": _cursor,
    "mouse": _mouse,
    "list": _list,
    "target": _target,
    "sliders": _sliders,
    "terminal": _terminal,
    "play": _play,
    "stop": _stop,
    "search": _search,
    "warning": _warning,
    "chevron-up": _chevron_up,
    "chevron-down": _chevron_down,
    "plus": _plus,
    "trash": _trash,
    "check": _check,
    "minimize": _minimize,
    "close": _close,
}

_CACHE: dict[tuple[str, str, int, int], QPixmap] = {}


def pixmap(name: str, color: str, size: int = 18, ratio: int = 2) -> QPixmap:
    """Tinted icon, rendered at `ratio` times the logical size for crispness."""
    key = (name, color, size, ratio)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    canvas = QPixmap(size * ratio, size * ratio)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(size * ratio / GRID, size * ratio / GRID)
    DRAW.get(name, _grid)(painter, QColor(color))
    painter.end()
    canvas.setDevicePixelRatio(float(ratio))
    _CACHE[key] = canvas
    return canvas


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))
