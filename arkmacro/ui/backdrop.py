"""
The canvas behind everything: petrol-to-black gradient, soft cyan glows and
the tribe brand melting out of the darkness.

Same treatment A.N.S Watcher uses (`Ui/Glass.cs`), ported to Qt so both tools
read as one product: the image is anchored top-right at cover scale, veiled
for readability, then faded to ink horizontally and vertically so it emerges
from the background instead of sitting on top of it.
"""
from __future__ import annotations

import pathlib

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QFrame, QWidget

from . import theme as T

ASSETS = pathlib.Path(__file__).resolve().parent.parent.parent / "assets"
BRAND_CANDIDATES = ("brand.png", "brand.gif", "brand.jpg", "brand.jpeg")

RADIUS = 14


def load_brand() -> QPixmap | None:
    """First brand image found next to the app. No file, no problem."""
    for name in BRAND_CANDIDATES:
        path = ASSETS / name
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return pixmap
    return None


class Backdrop(QFrame):
    """Root frame that paints the canvas under the whole UI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("root")
        self._brand = load_brand()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, RADIUS, RADIUS)
        painter.setClipPath(clip)

        self._paint_gradient(painter, rect)
        self._paint_glows(painter, rect)
        if self._brand is not None:
            self._paint_brand(painter, rect)
        self._paint_scrim(painter, rect)

        painter.end()
        # let the stylesheet draw the 1px border on top
        super().paintEvent(event)

    # ------------------------------------------------------------ layers
    def _paint_gradient(self, painter: QPainter, rect: QRectF) -> None:
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(T.INK_TOP))
        gradient.setColorAt(0.55, QColor(T.BG))
        gradient.setColorAt(1.0, QColor(T.INK))
        painter.fillRect(rect, QBrush(gradient))

    def _paint_glows(self, painter: QPainter, rect: QRectF) -> None:
        for cx, cy, span, alpha in (
            (-0.10, -0.15, 0.95, 34),
            (0.85, 0.80, 0.85, 22),
        ):
            centre = QPointF(rect.width() * cx, rect.height() * cy)
            radius = max(rect.width(), rect.height()) * span
            glow = QRadialGradient(centre, radius)
            accent = QColor(T.ACCENT)
            accent.setAlpha(alpha)
            glow.setColorAt(0.0, accent)
            accent_out = QColor(T.ACCENT)
            accent_out.setAlpha(0)
            glow.setColorAt(1.0, accent_out)
            painter.fillRect(rect, QBrush(glow))

    def _paint_brand(self, painter: QPainter, rect: QRectF) -> None:
        """
        The brand emerges from the canvas instead of sitting on it.

        The fade is applied to the image's own alpha (DestinationIn), not by
        painting ink rectangles over the background — otherwise the region
        edges show up as seams against the gradient.
        """
        if rect.width() < 300:
            return

        region = QRectF(rect.width() * 0.45, 0.0,
                        rect.width() * 0.55, rect.height() * 0.70)
        size = region.size().toSize()
        if size.width() < 2 or size.height() < 2:
            return

        layer = QImage(size, QImage.Format_ARGB32_Premultiplied)
        layer.fill(Qt.transparent)
        canvas = QPainter(layer)
        canvas.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # cover the region, anchored to its top-right corner
        scale = max(region.width() / self._brand.width(),
                    region.height() / self._brand.height())
        width = self._brand.width() * scale
        height = self._brand.height() * scale
        canvas.drawPixmap(QRectF(region.width() - width, 0, width, height),
                          self._brand, QRectF(self._brand.rect()))

        veil = QColor(T.INK)
        veil.setAlpha(140)
        canvas.fillRect(layer.rect(), veil)

        # feather the alpha: transparent on the left, transparent at the bottom
        canvas.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        opaque, clear = QColor(0, 0, 0, 255), QColor(0, 0, 0, 0)

        horizontal = QLinearGradient(0, 0, region.width() * 0.70, 0)
        horizontal.setColorAt(0.0, clear)
        horizontal.setColorAt(1.0, opaque)
        canvas.fillRect(QRectF(0, 0, region.width() * 0.70, region.height()),
                        QBrush(horizontal))

        vertical = QLinearGradient(0, region.height() * 0.30,
                                   0, region.height())
        vertical.setColorAt(0.0, opaque)
        vertical.setColorAt(1.0, clear)
        canvas.fillRect(QRectF(0, region.height() * 0.30,
                               region.width(), region.height() * 0.70),
                        QBrush(vertical))
        canvas.end()

        painter.setOpacity(0.62)
        painter.drawImage(region, layer)
        painter.setOpacity(1.0)

    def _paint_scrim(self, painter: QPainter, rect: QRectF) -> None:
        """Final flattening pass so page text never fights the backdrop."""
        scrim = QColor(T.INK)
        scrim.setAlpha(64)
        painter.fillRect(rect, scrim)
