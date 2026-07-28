"""Reusable widgets for the main window."""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QRectF,
                            QSize, Qt, Signal)
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import presets
from . import icons
from . import theme as T


def blank_pixmap(size: int = 14) -> QPixmap:
    """Transparent stand-in so rows without an icon keep their text aligned."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    return pixmap


# --------------------------------------------------------------- primitives

def hint_label(text: str, warn: bool = False) -> QLabel:
    """Small helper text. Always wraps, so it never widens the page."""
    label = QLabel(text)
    label.setObjectName("warnHint" if warn else "hint")
    label.setWordWrap(True)
    label.setMinimumWidth(1)
    return label


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFixedHeight(1)


class ToggleSwitch(QAbstractButton):
    """Animated on/off switch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(T.BORDER), QColor(T.ACCENT)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 2, 44, 20), 10, 10)
        painter.setBrush(QColor("#FFFFFF" if self.isChecked() else T.MUTED))
        painter.drawEllipse(QRectF(3 + self._pos * 21, 5, 14, 14))


class Card(QFrame):
    """Panel with a title, optional subtitle and a content area."""

    def __init__(self, title: str = "", subtitle: str = "",
                 accent: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cardAccent" if accent else "card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 15, 18, 17)
        outer.setSpacing(13)

        if title:
            head = QVBoxLayout()
            head.setSpacing(3)
            label = QLabel(title)
            label.setObjectName("cardTitle")
            head.addWidget(label)
            if subtitle:
                head.addWidget(hint_label(subtitle))
            outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(11)
        outer.addLayout(self.body)

    def add(self, item) -> "Card":
        if isinstance(item, QWidget):
            self.body.addWidget(item)
        else:
            self.body.addLayout(item)
        return self


class FormGrid(QWidget):
    """
    Label/control rows on a grid.

    With `pairs=2` two fields share a row, which keeps wide cards from looking
    like a column of lonely controls floating on the right.
    """

    def __init__(self, pairs: int = 1, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pairs = max(1, pairs)
        self._count = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(11)
        for slot in range(self._pairs):
            self.grid.setColumnMinimumWidth(slot * 3, 150)
            self.grid.setColumnStretch(slot * 3 + 2, 1)

    def add(self, label: str, widget: QWidget, tip: str = "") -> QLabel:
        """Adds a row and returns its label, so callers can hide the pair."""
        row, slot = divmod(self._count, self._pairs)
        text = QLabel(label)
        text.setObjectName("fieldLabel")
        text.setWordWrap(True)
        text.setMinimumWidth(1)
        if tip:
            text.setToolTip(tip)
            widget.setToolTip(tip)
        self.grid.addWidget(text, row, slot * 3, Qt.AlignVCenter)
        self.grid.addWidget(widget, row, slot * 3 + 1, Qt.AlignVCenter)
        self._count += 1
        return text

    def skip(self) -> None:
        """Leave a slot empty so related fields stay side by side."""
        self._count += 1


class SwitchRow(QWidget):
    """A label on the left, a toggle on the right."""

    def __init__(self, label: str, checked: bool = False, tip: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        text = QLabel(label)
        text.setObjectName("fieldLabel")
        text.setWordWrap(True)
        text.setMinimumWidth(1)
        self.switch = ToggleSwitch()
        self.switch.setChecked(checked)
        if tip:
            text.setToolTip(tip)
            self.switch.setToolTip(tip)
        row.addWidget(text, 1)
        row.addWidget(self.switch, 0, Qt.AlignRight)


class StatTile(QFrame):
    """Big number with a caption."""

    def __init__(self, label: str, value: str = "0",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 14)
        lay.setSpacing(3)
        self.value = QLabel(value)
        self.value.setObjectName("statValue")
        caption = QLabel(label.upper())
        caption.setObjectName("statLabel")
        lay.addWidget(self.value)
        lay.addWidget(caption)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class StatusPill(QLabel):
    """State indicator with a colored dot."""

    STATES = {
        "idle": (T.MUTED, "idle"),
        "farming": (T.OK, "farming"),
        "dropping": (T.ACCENT, "dropping"),
        "waiting": (T.WARN, "waiting"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self.set_state("idle")

    def set_state(self, state: str) -> None:
        color, text = self.STATES.get(state, self.STATES["idle"])
        self.setText(f"  ●  {text}  ")
        self.setStyleSheet(
            f"color:{color}; background:{T.SURFACE_2};"
            f"border:1px solid {T.BORDER}; border-radius:13px;"
            "font-size:12px; font-weight:600; padding:0 7px;"
        )


class HotkeyEdit(QLineEdit):
    """Captures the key combination pressed while focused."""

    captured = Signal(str)

    NAMED = {
        Qt.Key_Escape: "Esc", Qt.Key_Space: "Space", Qt.Key_Tab: "Tab",
        Qt.Key_Home: "Home", Qt.Key_End: "End", Qt.Key_Insert: "Insert",
        Qt.Key_Delete: "Delete", Qt.Key_PageUp: "PageUp",
        Qt.Key_PageDown: "PageDown", Qt.Key_Left: "Left", Qt.Key_Right: "Right",
        Qt.Key_Up: "Up", Qt.Key_Down: "Down", Qt.Key_Return: "Enter",
        Qt.Key_Backspace: "Backspace",
    }

    def __init__(self, value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        self.setPlaceholderText("click, then press")
        self.setToolTip("Click here and press the combination you want")

    def _name(self, key: int) -> str | None:
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            return f"F{key - Qt.Key_F1 + 1}"
        if key in self.NAMED:
            return self.NAMED[key]
        if 0x20 < key < 0x7F:
            return chr(key).upper()
        return None

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return
        name = self._name(key)
        if not name:
            return
        mods = []
        pressed = event.modifiers()
        if pressed & Qt.ControlModifier:
            mods.append("Ctrl")
        if pressed & Qt.AltModifier:
            mods.append("Alt")
        if pressed & Qt.ShiftModifier:
            mods.append("Shift")
        combo = "+".join(mods + [name])
        self.setText(combo)
        self.captured.emit(combo)


class PointThumb(QFrame):
    """
    Zoomed crop of the captured screen around a point.

    Seeing the actual pixels you targeted beats reading two numbers.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("thumb")
        self.setFixedSize(196, 104)
        self._pixmap: QPixmap | None = None

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self.update()

    @property
    def has_preview(self) -> bool:
        return self._pixmap is not None and not self._pixmap.isNull()

    def clear(self) -> None:
        self.set_pixmap(None)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        inner = self.rect().adjusted(1, 1, -1, -1)

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor(T.MUTED))
            painter.drawText(inner, Qt.AlignCenter, "no preview yet")
            return

        painter.drawPixmap(inner, self._pixmap)
        center = inner.center()
        painter.setPen(QPen(QColor(T.ACCENT), 1))
        painter.drawLine(center.x(), inner.top(), center.x(), inner.bottom())
        painter.drawLine(inner.left(), center.y(), inner.right(), center.y())
        painter.setPen(QPen(QColor(T.ACCENT), 2))
        painter.drawEllipse(center, 7, 7)


# ------------------------------------------------------------- templates UI

class PresetDialog(QDialog):
    """Ready-made templates grouped by what you are farming."""

    def __init__(self, existing: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ARK presets")
        self.setMinimumSize(540, 500)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(13)

        title = QLabel("Preset templates")
        title.setObjectName("cardTitle")
        lay.addWidget(title)
        lay.addWidget(hint_label(
            "ARK's filter matches any part of an item name, so short keywords "
            "also catch tools and armor. Entries marked ⚠ carry that risk — "
            "hover to see why."))

        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        for category, items in presets.PRESETS:
            header = QListWidgetItem(category.upper())
            header.setFlags(Qt.NoItemFlags)
            header.setForeground(QColor(T.ACCENT))
            header.setIcon(QIcon(blank_pixmap()))
            self.list.addItem(header)
            for name, keyword, risk, note in items:
                item = QListWidgetItem(f'{name}   ·   "{keyword}"')
                item.setIcon(icons.icon("warning", T.WARN, 14)
                             if risk == "high" else QIcon(blank_pixmap()))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                item.setToolTip(note)
                item.setData(Qt.UserRole, {"name": name, "keyword": keyword,
                                           "enabled": risk != "high"})
                if keyword.lower() in existing:
                    item.setFlags(Qt.NoItemFlags)
                    item.setForeground(QColor(T.MUTED))
                    item.setToolTip("already on your list")
                self.list.addItem(item)
        lay.addWidget(self.list, 1)

        lay.addWidget(hint_label(
            "High-risk presets are added unchecked — verify them with a dry "
            "run before arming."))

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("Add selected")
        confirm.setObjectName("primary")
        confirm.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(confirm)
        lay.addLayout(row)

    def chosen(self) -> list[dict]:
        picked = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.checkState() == Qt.Checked and item.data(Qt.UserRole):
                picked.append(dict(item.data(Qt.UserRole)))
        return picked


class TemplateEditor(QWidget):
    """
    Checkable list of drop templates.

    Every checked row is one Drop All pass of the cycle: a friendly name plus
    the keyword that gets typed into the inventory filter.
    """

    changed = Signal()

    def __init__(self, templates: list[dict],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.list = QListWidget()
        self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list.setMinimumHeight(168)
        self.list.setIconSize(QSize(14, 14))
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.currentItemChanged.connect(self._fill_editor)
        lay.addWidget(self.list)

        form = QHBoxLayout()
        form.setSpacing(9)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("template name (e.g. Stone)")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("keyword typed in game (e.g. stone)")
        self.keyword_edit.returnPressed.connect(self._add)
        form.addWidget(self.name_edit, 1)
        form.addWidget(self.keyword_edit, 1)
        lay.addLayout(form)

        row = QHBoxLayout()
        row.setSpacing(9)
        for text, glyph, slot, tip, width in (
            ("Add", "plus", self._add,
             "Create a template from the fields above", 0),
            ("Save", "check", self._update,
             "Apply the fields to the selected row", 0),
            ("Remove", "trash", self._remove, "Delete the selected row", 0),
            ("", "chevron-up", lambda: self._move(-1),
             "Move earlier in the cycle", 36),
            ("", "chevron-down", lambda: self._move(1),
             "Move later in the cycle", 36),
            ("Presets", "list", self._presets, "Ready-made ARK templates", 0),
        ):
            button = QPushButton(f" {text}" if text else "")
            button.setObjectName("tiny")
            button.setToolTip(tip)
            button.setIcon(icons.icon(glyph, T.TEXT_DIM, 14))
            button.setIconSize(QSize(14, 14))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(slot)
            if width:
                button.setFixedWidth(width)
            row.addWidget(button)
        row.addStretch(1)
        lay.addLayout(row)

        self.set_templates(templates)

    # ------------------------------------------------------------- data
    def set_templates(self, templates: list[dict]) -> None:
        self._loading = True
        self.list.clear()
        for template in templates:
            self._insert(template)
        self._loading = False

    def _make_item(self, template: dict) -> QListWidgetItem:
        keyword = str(template.get("keyword", "")).strip()
        name = str(template.get("name") or keyword).strip()
        risk, note = presets.risk_of(keyword)

        item = QListWidgetItem()
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if template.get("enabled") else Qt.Unchecked)
        item.setData(Qt.UserRole, {"name": name, "keyword": keyword})
        item.setText(f'{name}   ·   "{keyword}"')
        if risk == "high":
            item.setIcon(icons.icon("warning", T.WARN, 14))
            item.setForeground(QColor(T.WARN))
            item.setToolTip(f"Risk: {note}")
        else:
            item.setIcon(QIcon(blank_pixmap()))
            item.setToolTip(note or f'types "{keyword}" into the filter')
        return item

    def _insert(self, template: dict, row: int | None = None) -> QListWidgetItem:
        item = self._make_item(template)
        if row is None:
            self.list.addItem(item)
        else:
            self.list.insertItem(row, item)
        return item

    def templates(self) -> list[dict]:
        out = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            data = item.data(Qt.UserRole) or {}
            out.append({
                "name": data.get("name", ""),
                "keyword": data.get("keyword", ""),
                "enabled": item.checkState() == Qt.Checked,
            })
        return out

    def _keywords(self) -> set[str]:
        return {t["keyword"].lower() for t in self.templates() if t["keyword"]}

    # ---------------------------------------------------------- actions
    def _on_item_changed(self, _item) -> None:
        if not self._loading:
            self.changed.emit()

    def _fill_editor(self, item, _previous=None) -> None:
        data = (item.data(Qt.UserRole) or {}) if item else {}
        self.name_edit.setText(data.get("name", ""))
        self.keyword_edit.setText(data.get("keyword", ""))

    def _add(self) -> None:
        keyword = self.keyword_edit.text().strip()
        if not keyword or keyword.lower() in self._keywords():
            return
        name = self.name_edit.text().strip() or keyword.capitalize()
        self._insert({"name": name, "keyword": keyword, "enabled": True})
        self.name_edit.clear()
        self.keyword_edit.clear()
        self.changed.emit()

    def _update(self) -> None:
        item = self.list.currentItem()
        keyword = self.keyword_edit.text().strip()
        if not item or not keyword:
            return
        row = self.list.row(item)
        enabled = item.checkState() == Qt.Checked
        name = self.name_edit.text().strip() or keyword.capitalize()
        self._loading = True
        self.list.takeItem(row)
        self._insert({"name": name, "keyword": keyword, "enabled": enabled}, row)
        self._loading = False
        self.list.setCurrentRow(row)
        self.changed.emit()

    def _remove(self) -> None:
        item = self.list.currentItem()
        if item:
            self.list.takeItem(self.list.row(item))
            self.changed.emit()

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self.list.count()):
            return
        self._loading = True
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self._loading = False
        self.list.setCurrentRow(target)
        self.changed.emit()

    def _presets(self) -> None:
        dialog = PresetDialog(self._keywords(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        chosen = dialog.chosen()
        self._loading = True
        for template in chosen:
            self._insert(template)
        self._loading = False
        if chosen:
            self.changed.emit()


# ------------------------------------------------------------- window chrome

class NavButton(QPushButton):
    """Sidebar entry: painted icon that follows the checked state."""

    def __init__(self, icon_name: str, text: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(f"   {text}", parent)
        self.setObjectName("navbtn")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self._icon_name = icon_name
        self._refresh()
        self.toggled.connect(self._refresh)

    def _refresh(self, *_args) -> None:
        color = T.ACCENT if self.isChecked() else T.MUTED
        self.setIcon(icons.icon(self._icon_name, color, 18))


class WindowButton(QPushButton):
    def __init__(self, icon_name: str, name: str = "winbtn",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.setFixedSize(34, 28)
        self.setIconSize(QSize(16, 16))
        self._icon_name = icon_name
        self._hover = "#ffffff" if name == "closebtn" else T.TEXT
        self.setIcon(icons.icon(icon_name, T.MUTED, 16))

    def enterEvent(self, event) -> None:
        self.setIcon(icons.icon(self._icon_name, self._hover, 16))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setIcon(icons.icon(self._icon_name, T.MUTED, 16))
        super().leaveEvent(event)


class TitleBar(QWidget):
    """Draggable top bar of the frameless window."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._drag = None
        self.setObjectName("titlebar")
        self.setFixedHeight(54)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 12, 0)
        lay.setSpacing(9)

        mark = QLabel("A.N.S")
        mark.setObjectName("logoMark")
        name = QLabel("TOOLS")
        name.setObjectName("logoText")
        lay.addWidget(mark)
        lay.addWidget(name)
        lay.addSpacing(12)

        subtitle = QLabel("ark farm macro")
        subtitle.setObjectName("logoSub")
        lay.addWidget(subtitle)
        lay.addSpacing(14)

        self.status = StatusPill()
        lay.addWidget(self.status)

        # only shows up once a check finds the repo ahead of us
        self.update_pill = QPushButton("update available")
        self.update_pill.setObjectName("updatePill")
        self.update_pill.setCursor(Qt.PointingHandCursor)
        self.update_pill.setToolTip("Open Settings to install it")
        self.update_pill.hide()
        lay.addWidget(self.update_pill)

        lay.addStretch(1)

        self.minimize = WindowButton("minimize")
        self.close_btn = WindowButton("close", "closebtn")
        self.minimize.clicked.connect(window.showMinimized)
        self.close_btn.clicked.connect(window.close)
        lay.addWidget(self.minimize)
        lay.addWidget(self.close_btn)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag = (event.globalPosition().toPoint()
                          - self._window.frameGeometry().topLeft())

    def mouseMoveEvent(self, event) -> None:
        if self._drag and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag = None
