"""Main window of ARK Farm Macro."""
from __future__ import annotations

import pathlib
import sys
import time

from PySide6.QtCore import QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                               QDoubleSpinBox, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizeGrip, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from .. import layout as ark_layout
from .. import updater
from .. import winapi as w
from ..config import Config
from ..engine import MacroEngine
from ..hotkeys import HotkeyManager
from . import icons
from . import theme as T
from .backdrop import Backdrop
from .picker import ScreenPicker
from .widgets import (Card, Divider, FormGrid, HotkeyEdit, NavButton, PointThumb,
                      StatTile, SwitchRow, TemplateEditor, TitleBar, hint_label)

NAV = [
    ("grid", "Dashboard"),
    ("mouse", "Autoclick"),
    ("list", "Templates"),
    ("target", "Points"),
    ("sliders", "Settings"),
    ("terminal", "Log"),
]

APP_NAME = "A.N.S Tools"

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / "state"
CAPTURE_DIR = ROOT / "captures"


def spin(minimum, maximum, value, suffix="", step=1) -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(int(value))
    box.setSingleStep(step)
    if suffix:
        box.setSuffix(suffix)
    box.setFixedWidth(124)
    return box


def dspin(minimum, maximum, value, suffix="", step=0.5) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(1)
    box.setValue(float(value))
    box.setSingleStep(step)
    if suffix:
        box.setSuffix(suffix)
    box.setFixedWidth(124)
    return box


def combo(items: list[str], current: int = 0, width: int = 170) -> QComboBox:
    box = QComboBox()
    box.addItems(items)
    box.setCurrentIndex(current)
    box.setFixedWidth(width)
    return box


def scroll_page() -> tuple[QScrollArea, QVBoxLayout]:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(30, 26, 30, 26)
    lay.setSpacing(18)
    area.setWidget(inner)
    return area, lay


def heading(title: str, subtitle: str) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(4)
    label = QLabel(title)
    label.setObjectName("pageTitle")
    sub = QLabel(subtitle)
    sub.setObjectName("pageSub")
    sub.setWordWrap(True)
    sub.setMinimumWidth(1)
    box.addWidget(label)
    box.addWidget(sub)
    return box


def chip(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color:{T.TEXT_DIM}; background:{T.SURFACE_2};"
        f"border:1px solid {T.BORDER}; border-radius:7px;"
        "padding:5px 10px; font-size:11px;")
    return label


def step_row(number: str, title: str, detail: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(13)
    badge = QLabel(number)
    badge.setObjectName("stepNum")
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(22, 22)
    text = QVBoxLayout()
    text.setSpacing(1)
    head = QLabel(title)
    head.setObjectName("fieldLabel")
    text.addWidget(head)
    text.addWidget(hint_label(detail))
    row.addWidget(badge, 0, Qt.AlignTop)
    row.addLayout(text, 1)
    row.title_label = head          # so callers can keep the text in sync
    return row


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config.load()
        self.engine: MacroEngine | None = None
        self._picker: ScreenPicker | None = None
        self._shot: QPixmap | None = None
        self._shot_origin = (0, 0)
        self._pick_screen = None
        self._update_worker: updater.UpdateWorker | None = None
        self._silent_check = False
        self._restarting = False

        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1060, 720)
        self.setMinimumSize(940, 620)

        self._build_ui()
        self._wire_autosave()

        self.hotkeys = HotkeyManager()
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkeys.failed.connect(
            lambda name, key: self._log(
                f'could not register "{key}" for {name} — another program may '
                "already own it", "err"))
        self._apply_hotkeys()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save)

        self._start_ts = time.time()
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._tick_time)

        self._load_thumbs()
        self._refresh_points_status()
        self._maybe_rescale_points()
        self._refresh_version()
        self.titlebar.update_pill.clicked.connect(self._open_settings)
        self._log("ready. set the two points on the Points tab before the "
                  "first run.", "info")
        if self.cfg.app.check_updates_on_start:
            QTimer.singleShot(1200, lambda: self._check_updates(silent=True))

    def _open_settings(self) -> None:
        self.nav_group.button(4).setChecked(True)
        self.stack.setCurrentIndex(4)

    # -------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        root = Backdrop()
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 190))
        root.setGraphicsEffect(shadow)
        outer.addWidget(root)

        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        self.titlebar = TitleBar(self)
        root_lay.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root_lay.addLayout(body, 1)
        body.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)
        body.addWidget(self.stack, 1)

        self.stack.addWidget(self._page_dashboard())
        self.stack.addWidget(self._page_autoclick())
        self.stack.addWidget(self._page_templates())
        self.stack.addWidget(self._page_points())
        self.stack.addWidget(self._page_settings())
        self.stack.addWidget(self._page_log())

        grip = QSizeGrip(root)
        grip.setFixedSize(16, 16)
        root_lay.addWidget(grip, 0, Qt.AlignRight | Qt.AlignBottom)

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(196)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 18, 10, 16)
        lay.setSpacing(3)

        section = QLabel("CONTROL")
        section.setObjectName("navSection")
        lay.addWidget(section)
        lay.addSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (glyph, name) in enumerate(NAV):
            button = NavButton(glyph, name)
            button.setChecked(index == 0)
            self.nav_group.addButton(button, index)
            lay.addWidget(button)
            if index == 0:
                lay.addSpacing(6)
                setup = QLabel("SETUP")
                setup.setObjectName("navSection")
                lay.addWidget(setup)
                lay.addSpacing(6)
        lay.addStretch(1)

        version = QLabel(f"v{__version__}  ·  companion to A.N.S Watcher")
        version.setObjectName("footNote")
        version.setWordWrap(True)
        lay.addWidget(version)
        return side

    # ------------------------------------------------------------ dashboard
    def _page_dashboard(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Dashboard",
            "Keep ARK in front and drive everything from the global hotkeys. "
            "The macro swaps between farming and emptying your inventory on "
            "its own."))

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.tile_clicks = StatTile("clicks", "0")
        self.tile_drops = StatTile("drop passes", "0")
        self.tile_time = StatTile("uptime", "00:00")
        for tile in (self.tile_clicks, self.tile_drops, self.tile_time):
            stats.addWidget(tile, 1)
        lay.addLayout(stats)

        control = Card("Control", accent=True)
        row = QHBoxLayout()
        row.setSpacing(11)
        self.btn_start = QPushButton("  Start macro")
        self.btn_start.setObjectName("primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setIconSize(QSize(16, 16))
        self.btn_start.setIcon(icons.icon("play", "#04222B", 16))
        self.btn_start.clicked.connect(self._toggle_macro)
        self.btn_drop = QPushButton("  Drop now")
        self.btn_drop.setIcon(icons.icon("trash", T.TEXT_DIM, 15))
        self.btn_drop.setIconSize(QSize(15, 15))
        self.btn_drop.setCursor(Qt.PointingHandCursor)
        self.btn_drop.clicked.connect(self._drop_now)
        row.addWidget(self.btn_start, 2)
        row.addWidget(self.btn_drop, 1)
        control.add(row)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chip_toggle = chip("")
        self.chip_drop = chip("")
        self.chip_panic = chip("")
        for item in (self.chip_toggle, self.chip_drop, self.chip_panic):
            chips.addWidget(item)
        chips.addStretch(1)
        control.add(chips)

        self.lbl_ready = hint_label("")
        control.add(self.lbl_ready)
        lay.addWidget(control)

        cycle = Card("What one drop pass does")
        for number, title, detail in (
            ("1", "Pause and open", "stops clicking and presses the inventory key"),
            ("2", "Focus the filter", "clicks the search field and clears it"),
            ("3", "Type the keyword", "one enabled template at a time"),
            ("4", "Drop All", "with the filter on, only what is listed falls"),
            ("5", "Repeat and resume", "clears the filter, closes, back to farming"),
        ):
            cycle.add(step_row(number, title, detail))
        lay.addWidget(cycle)

        self.mini_log = QPlainTextEdit()
        self.mini_log.setObjectName("log")
        self.mini_log.setReadOnly(True)
        self.mini_log.setMaximumBlockCount(80)
        self.mini_log.setFixedHeight(118)
        lay.addWidget(self.mini_log)

        lay.addStretch(1)
        self._refresh_hotkey_chips()
        return page

    # ------------------------------------------------------------ autoclick
    def _page_autoclick(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Autoclick",
            "Speed is drawn at random between the two bounds on every click, so "
            "the rhythm never turns into a metronome."))

        card = Card("Clicking")
        grid = FormGrid(pairs=2)
        self.cb_button = combo(["left", "right", "middle"], width=124)
        self.cb_button.setCurrentText(self.cfg.autoclick.button)
        grid.add("Mouse button", self.cb_button)
        grid.skip()  # keep min/max pairs on their own rows
        self.sp_cps_min = dspin(0.5, 40, self.cfg.autoclick.cps_min, " cps", 0.5)
        self.sp_cps_max = dspin(0.5, 40, self.cfg.autoclick.cps_max, " cps", 0.5)
        grid.add("Minimum speed", self.sp_cps_min)
        grid.add("Maximum speed", self.sp_cps_max)
        self.sp_hold_min = spin(5, 500, self.cfg.autoclick.hold_min_ms, " ms", 5)
        self.sp_hold_max = spin(5, 500, self.cfg.autoclick.hold_max_ms, " ms", 5)
        grid.add("Hold time, min", self.sp_hold_min,
                 "How long the button stays pressed on each click")
        grid.add("Hold time, max", self.sp_hold_max)
        card.add(grid)
        card.add(hint_label(
            "Hold time counts towards the period, so 9 cps really means 9 "
            "clicks per second."))
        lay.addWidget(card)

        pause = Card("Micro pauses",
                     "A short breather every N clicks. Zero turns it off.")
        pgrid = FormGrid(pairs=2)
        self.sp_mp_every = spin(0, 5000, self.cfg.autoclick.micro_pause_every,
                                " clicks", 10)
        self.sp_mp_ms = spin(50, 5000, self.cfg.autoclick.micro_pause_ms, " ms", 50)
        pgrid.add("Pause every", self.sp_mp_every)
        pgrid.add("Pause length", self.sp_mp_ms)
        pause.add(pgrid)
        lay.addWidget(pause)

        lay.addStretch(1)
        return page

    # ------------------------------------------------------------ templates
    def _page_templates(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Templates",
            "Every checked row is one Drop All pass: a name for you, plus the "
            "keyword typed into ARK's inventory filter."))

        trigger = Card("When it runs")
        self.sw_drop = SwitchRow("Drop routine enabled", self.cfg.drop.enabled)
        trigger.add(self.sw_drop)
        tgrid = FormGrid(pairs=2)
        self.cb_trigger = combo(["On a timer", "Every N clicks", "Hotkey only"],
                                {"interval": 0, "clicks": 1,
                                 "manual": 2}.get(self.cfg.drop.trigger, 0))
        self.cb_trigger.currentIndexChanged.connect(self._sync_trigger_fields)
        tgrid.add("Trigger", self.cb_trigger)
        self.sp_interval = spin(10, 7200, self.cfg.drop.interval_s, " s", 10)
        self.sp_every_clicks = spin(10, 100000, self.cfg.drop.every_clicks,
                                    " clicks", 50)
        self.lbl_interval = tgrid.add("Interval", self.sp_interval)
        self.lbl_clicks = tgrid.add("Run every", self.sp_every_clicks)
        trigger.add(tgrid)
        lay.addWidget(trigger)

        card = Card("Drop list")
        self.tpl_editor = TemplateEditor(self.cfg.drop.templates)
        card.add(self.tpl_editor)
        card.add(hint_label(
            "ARK's filter matches any part of an item name and ignores case: "
            '"stone" also lists Stone Pick and Stone Hatchet, and Drop All '
            "takes everything listed. Rows marked ⚠ carry that risk.", warn=True))
        lay.addWidget(card)

        dry = Card("Dry run",
                   "Runs the whole cycle — opens, filters, types — but never "
                   "clicks Drop All. Saves a screenshot of the filtered "
                   "inventory to captures/ so you can check what would fall.")
        self.sw_dry = SwitchRow("Run without dropping anything",
                                self.cfg.drop.dry_run)
        dry.add(self.sw_dry)
        lay.addWidget(dry)

        timing = Card("Inventory and timings",
                      "Raise the waits if your server is laggy — a filter that "
                      "has not refreshed yet is the usual cause of dropping the "
                      "wrong thing.")
        igrid = FormGrid(pairs=2)
        self.ed_inv_key = QLineEdit(self.cfg.drop.inventory_key)
        self.ed_inv_key.setMaxLength(10)
        self.ed_inv_key.setFixedWidth(124)
        self.ed_inv_key.setAlignment(Qt.AlignCenter)
        igrid.add("Inventory key", self.ed_inv_key, "Key name: i, tab, f, esc...")
        self.cb_close = combo(["Same key", "Esc"],
                              0 if self.cfg.drop.close_with == "same" else 1,
                              width=124)
        igrid.add("Close inventory with", self.cb_close)
        self.sp_open_wait = spin(100, 8000, self.cfg.drop.open_wait_ms, " ms", 50)
        self.sp_type_wait = spin(50, 5000, self.cfg.drop.after_type_wait_ms,
                                 " ms", 50)
        self.sp_drop_wait = spin(50, 5000, self.cfg.drop.after_drop_wait_ms,
                                 " ms", 50)
        self.sp_close_wait = spin(100, 8000, self.cfg.drop.close_wait_ms, " ms", 50)
        self.sp_backspaces = spin(0, 80, self.cfg.drop.clear_backspaces, "x", 1)
        igrid.add("Wait after opening", self.sp_open_wait)
        igrid.add("Wait after typing", self.sp_type_wait)
        igrid.add("Wait after Drop All", self.sp_drop_wait)
        igrid.add("Wait after closing", self.sp_close_wait)
        igrid.add("Backspaces to clear", self.sp_backspaces,
                  "Must be longer than your longest keyword")
        timing.add(igrid)
        lay.addWidget(timing)

        lay.addStretch(1)
        self._sync_trigger_fields()
        return page

    # --------------------------------------------------------------- points
    def _page_points(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Points",
            "The two clicks of the routine depend on your resolution and on "
            "what the HUD is showing. Freeze the screen once and pick them."))

        guide = Card("Pick them on a frozen screen", accent=True)
        guide.add(step_row(
            "1", "Open the inventory in ARK",
            f"exactly the state the macro will use — inventory alone with "
            f"«{self.cfg.drop.inventory_key.upper()}», or with a storage box "
            "open. The icon row sits in a different place in each."))
        pick_step = step_row(
            "2", f"Press {self.cfg.hotkeys.pick_points}",
            "this window hides, the screen is frozen and a magnifier follows "
            "your cursor")
        self.lbl_pick_step = pick_step.title_label
        guide.add(pick_step)
        guide.add(step_row(
            "3", "Click the search field, then Drop All",
            "arrow keys nudge one pixel, Shift+arrow ten, Enter confirms, Esc "
            "cancels"))
        guide.add(Divider())
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_pick = QPushButton("  Freeze screen and pick both points")
        self.btn_pick.setObjectName("primary")
        self.btn_pick.setCursor(Qt.PointingHandCursor)
        self.btn_pick.setIcon(icons.icon("search", "#04222B", 16))
        self.btn_pick.setIconSize(QSize(16, 16))
        self.btn_pick.clicked.connect(self._begin_pick)
        row.addWidget(self.btn_pick, 1)
        guide.add(row)
        guide.add(hint_label(
            "Run ARK in borderless or windowed mode — exclusive fullscreen "
            "cannot be frozen or overlaid."))
        lay.addWidget(guide)

        pair = QHBoxLayout()
        pair.setSpacing(14)
        self.thumb_filter, self.sp_fx, self.sp_fy, filter_card = self._point_card(
            "Filter field", "The magnifier box at the top of the panel.",
            self.cfg.drop.filter_point, "filter")
        self.thumb_drop, self.sp_dx, self.sp_dy, drop_card = self._point_card(
            "Drop All button",
            "Second icon of the row, right next to the crossed arrows.",
            self.cfg.drop.dropall_point, "dropall")
        pair.addWidget(filter_card, 1)
        pair.addWidget(drop_card, 1)
        lay.addLayout(pair)

        self.lbl_points_status = hint_label("")
        lay.addWidget(self.lbl_points_status)

        fallback = Card("No screenshot? Estimate instead",
                        "ARK anchors its HUD to the centre of the screen and "
                        "scales it with height, so the maths also holds on "
                        "ultrawide. Always verify with Test afterwards.")
        btn_suggest = QPushButton("Estimate points for this resolution")
        btn_suggest.setCursor(Qt.PointingHandCursor)
        btn_suggest.clicked.connect(self._suggest_points)
        fallback.add(btn_suggest)
        lay.addWidget(fallback)

        lay.addStretch(1)
        return page

    def _point_card(self, title: str, subtitle: str, point: list[int], key: str):
        card = Card(title, subtitle)
        thumb = PointThumb()
        card.add(thumb)

        coords = QHBoxLayout()
        coords.setSpacing(8)
        x_box = spin(0, 30000, point[0] if point else 0)
        y_box = spin(0, 30000, point[1] if len(point) > 1 else 0)
        x_box.setFixedWidth(86)
        y_box.setFixedWidth(86)
        for label, box in (("X", x_box), ("Y", y_box)):
            text = QLabel(label)
            text.setObjectName("fieldLabel")
            coords.addWidget(text)
            coords.addWidget(box)
        test = QPushButton("  Test")
        test.setObjectName("tiny")
        test.setIcon(icons.icon("target", T.TEXT_DIM, 14))
        test.setIconSize(QSize(14, 14))
        test.setCursor(Qt.PointingHandCursor)
        test.setToolTip("Moves the cursor to the saved point without clicking")
        test.clicked.connect(lambda: self._test_point(x_box.value(), y_box.value()))
        coords.addWidget(test)
        coords.addStretch(1)
        card.add(coords)

        setattr(self, f"_thumb_{key}", thumb)
        return thumb, x_box, y_box, card

    # ------------------------------------------------------------- settings
    def _page_settings(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading("Settings",
                              "Global hotkeys and how input reaches the game."))

        keys = Card("Global hotkeys", "They fire even while ARK has focus.")
        kgrid = FormGrid(pairs=2)
        self.hk_toggle = HotkeyEdit(self.cfg.hotkeys.toggle)
        self.hk_drop = HotkeyEdit(self.cfg.hotkeys.drop_now)
        self.hk_panic = HotkeyEdit(self.cfg.hotkeys.panic)
        self.hk_pick = HotkeyEdit(self.cfg.hotkeys.pick_points)
        for edit in (self.hk_toggle, self.hk_drop, self.hk_panic, self.hk_pick):
            edit.setFixedWidth(140)
            edit.captured.connect(self._apply_hotkeys)
        kgrid.add("Start / stop", self.hk_toggle)
        kgrid.add("Drop now", self.hk_drop)
        kgrid.add("Emergency stop", self.hk_panic)
        kgrid.add("Pick points", self.hk_pick)
        keys.add(kgrid)
        lay.addWidget(keys)

        target = Card("Target and delivery")
        self.cb_mode = combo(["Foreground (recommended)", "Background (experimental)"],
                             0 if self.cfg.target.mode == "foreground" else 1,
                             width=230)
        self.cb_mode.currentIndexChanged.connect(self._sync_mode_note)
        mgrid = FormGrid(pairs=1)
        mgrid.add("Delivery mode", self.cb_mode)
        target.add(mgrid)
        self.mode_note = hint_label("")
        target.add(self.mode_note)
        target.add(Divider())

        wgrid = FormGrid(pairs=2)
        self.ed_window = QLineEdit(self.cfg.target.window_title)
        self.ed_window.setFixedWidth(170)
        wgrid.add("Window title", self.ed_window,
                  "Fragment of the game window title. Default: ARK")
        self.sp_delay = dspin(0, 30, self.cfg.target.start_delay_s, " s", 0.5)
        wgrid.add("Start delay", self.sp_delay,
                  "Time for you to get back into the game before the first click")
        target.add(wgrid)

        self.sw_focus = SwitchRow("Only click while the game is focused",
                                  self.cfg.target.require_focus)
        target.add(self.sw_focus)

        self.chk_unicode = QCheckBox("Type in unicode mode")
        self.chk_unicode.setChecked(self.cfg.drop.unicode_typing)
        target.add(self.chk_unicode)
        target.add(hint_label("Only enable this if the in-game search field "
                              "ignores the letters the macro types."))

        detect = QPushButton("Find the ARK window")
        detect.setCursor(Qt.PointingHandCursor)
        detect.clicked.connect(self._detect_window)
        target.add(detect)
        lay.addWidget(target)

        lay.addWidget(self._updates_card())
        lay.addStretch(1)
        self._sync_mode_note()
        return page

    def _updates_card(self) -> Card:
        card = Card("Updates",
                    "Pulls straight from the repository this app is published "
                    "to, then restarts. Your config, captured points and "
                    "screenshots are never touched.")

        self.lbl_version = hint_label("")
        card.add(self.lbl_version)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_check = QPushButton("  Check for updates")
        self.btn_check.setCursor(Qt.PointingHandCursor)
        self.btn_check.setIcon(icons.icon("target", T.TEXT_DIM, 15))
        self.btn_check.setIconSize(QSize(15, 15))
        self.btn_check.clicked.connect(lambda: self._check_updates())
        self.btn_apply = QPushButton("  Update and restart")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.setIcon(icons.icon("play", "#04222B", 15))
        self.btn_apply.setIconSize(QSize(15, 15))
        self.btn_apply.clicked.connect(self._apply_update)
        self.btn_apply.hide()
        row.addWidget(self.btn_check)
        row.addWidget(self.btn_apply)
        row.addStretch(1)
        card.add(row)

        self.lbl_update = hint_label("")
        card.add(self.lbl_update)
        self.lbl_commits = hint_label("")
        self.lbl_commits.hide()
        card.add(self.lbl_commits)

        self.sw_updates = SwitchRow("Check when the app starts",
                                    self.cfg.app.check_updates_on_start)
        card.add(self.sw_updates)
        return card

    def _page_log(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading("Log", "Everything the macro did this session."))
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1500)
        lay.addWidget(self.log_view, 1)
        clear = QPushButton("Clear log")
        clear.clicked.connect(self.log_view.clear)
        lay.addWidget(clear, 0, Qt.AlignRight)
        return page

    # ----------------------------------------------------------- ui syncing
    def _sync_trigger_fields(self) -> None:
        index = self.cb_trigger.currentIndex()
        self.lbl_interval.setVisible(index == 0)
        self.sp_interval.setVisible(index == 0)
        self.lbl_clicks.setVisible(index == 1)
        self.sp_every_clicks.setVisible(index == 1)

    def _sync_mode_note(self) -> None:
        if self.cb_mode.currentIndex() == 0:
            self.mode_note.setText(
                "Sends real input (SendInput). Always works, but ARK has to be "
                "in front — the macro pauses by itself when you switch away and "
                "resumes when you come back.")
        else:
            self.mode_note.setText(
                "Posts messages straight to the window (PostMessage) so you can "
                "use the PC while farming. Unreal usually reads Raw Input and "
                "ignores this, so test it: if nothing happens in game, go back "
                "to foreground.")

    def _refresh_hotkey_chips(self) -> None:
        keys = self.cfg.hotkeys
        self.chip_toggle.setText(f"{keys.toggle}   start / stop")
        self.chip_drop.setText(f"{keys.drop_now}   drop now")
        self.chip_panic.setText(f"{keys.panic}   emergency stop")
        if hasattr(self, "lbl_pick_step"):
            self.lbl_pick_step.setText(f"Press {keys.pick_points}")

    def _refresh_points_status(self) -> None:
        drop = self.cfg.drop
        res = drop.points_resolution
        ready = any(drop.filter_point) and any(drop.dropall_point)
        where = f" · captured at {res[0]}x{res[1]}" if res and all(res) else ""
        self.lbl_points_status.setText(
            f"Both points set{where}." if ready
            else "Points are still missing — the drop routine will refuse to run.")
        if hasattr(self, "lbl_ready"):
            self.lbl_ready.setText(
                "Ready to farm." if ready or not drop.enabled
                else "Set the two points on the Points tab before starting.")

    # ---------------------------------------------------------- config i/o
    def _wire_autosave(self) -> None:
        widgets = [
            self.cb_button, self.sp_cps_min, self.sp_cps_max, self.sp_hold_min,
            self.sp_hold_max, self.sp_mp_every, self.sp_mp_ms,
            self.sw_drop.switch, self.cb_trigger, self.sp_interval,
            self.sp_every_clicks, self.ed_inv_key, self.cb_close,
            self.sp_open_wait, self.sp_close_wait, self.sp_type_wait,
            self.sp_drop_wait, self.sp_backspaces, self.sp_fx, self.sp_fy,
            self.sp_dx, self.sp_dy, self.cb_mode, self.ed_window,
            self.sw_focus.switch, self.sp_delay, self.chk_unicode,
            self.hk_toggle, self.hk_drop, self.hk_panic, self.hk_pick,
            self.sw_dry.switch, self.sw_updates.switch,
        ]
        for widget in widgets:
            for name in ("valueChanged", "currentIndexChanged", "textChanged",
                         "toggled", "captured"):
                signal = getattr(widget, name, None)
                if signal is not None:
                    signal.connect(self._on_change)
                    break
        self.tpl_editor.changed.connect(self._on_change)

    def _on_change(self, *_args) -> None:
        self._pull()
        self._save_timer.start(600)

    def _pull(self) -> None:
        """Copy widget values into the configuration object."""
        auto = self.cfg.autoclick
        auto.button = self.cb_button.currentText()
        auto.cps_min = self.sp_cps_min.value()
        auto.cps_max = self.sp_cps_max.value()
        auto.hold_min_ms = self.sp_hold_min.value()
        auto.hold_max_ms = self.sp_hold_max.value()
        auto.micro_pause_every = self.sp_mp_every.value()
        auto.micro_pause_ms = self.sp_mp_ms.value()

        drop = self.cfg.drop
        drop.enabled = self.sw_drop.switch.isChecked()
        drop.trigger = ["interval", "clicks",
                        "manual"][self.cb_trigger.currentIndex()]
        drop.interval_s = self.sp_interval.value()
        drop.every_clicks = self.sp_every_clicks.value()
        drop.inventory_key = self.ed_inv_key.text().strip().lower() or "i"
        drop.close_with = "same" if self.cb_close.currentIndex() == 0 else "esc"
        drop.open_wait_ms = self.sp_open_wait.value()
        drop.close_wait_ms = self.sp_close_wait.value()
        drop.after_type_wait_ms = self.sp_type_wait.value()
        drop.after_drop_wait_ms = self.sp_drop_wait.value()
        drop.clear_backspaces = self.sp_backspaces.value()
        drop.filter_point = [self.sp_fx.value(), self.sp_fy.value()]
        drop.dropall_point = [self.sp_dx.value(), self.sp_dy.value()]
        drop.templates = self.tpl_editor.templates()
        drop.dry_run = self.sw_dry.switch.isChecked()
        drop.unicode_typing = self.chk_unicode.isChecked()

        target = self.cfg.target
        target.mode = ("foreground" if self.cb_mode.currentIndex() == 0
                       else "background")
        target.window_title = self.ed_window.text().strip() or "ARK"
        target.require_focus = self.sw_focus.switch.isChecked()
        target.start_delay_s = self.sp_delay.value()

        keys = self.cfg.hotkeys
        keys.toggle = self.hk_toggle.text() or keys.toggle
        keys.drop_now = self.hk_drop.text() or keys.drop_now
        keys.panic = self.hk_panic.text() or keys.panic
        keys.pick_points = self.hk_pick.text() or keys.pick_points
        self.cfg.app.check_updates_on_start = self.sw_updates.switch.isChecked()
        self._refresh_hotkey_chips()
        self._refresh_points_status()

    def _save(self) -> None:
        try:
            self.cfg.save()
        except OSError as error:
            self._log(f"could not save the config: {error}", "err")

    # ---------------------------------------------------------- macro ctrl
    def _toggle_macro(self) -> None:
        if self.engine and self.engine.isRunning():
            self._stop_macro()
        else:
            self._start_macro()

    def _start_macro(self) -> None:
        self._pull()
        self._save()
        drop = self.cfg.drop
        missing = not any(drop.filter_point) or (not drop.dry_run
                                                 and not any(drop.dropall_point))
        if drop.enabled and missing:
            self._log("set the filter and Drop All points before arming the "
                      "drop routine", "err")
            self.nav_group.button(3).setChecked(True)
            self.stack.setCurrentIndex(3)
            return

        self.engine = MacroEngine(self.cfg)
        self.engine.log.connect(self._log)
        self.engine.state_changed.connect(self._on_state)
        self.engine.stats_changed.connect(self._on_stats)
        self.engine.shot_requested.connect(self._save_shot)
        self.engine.finished.connect(self._on_finished)
        self._start_ts = time.time()
        self._time_timer.start(1000)
        self.engine.start()
        self._set_start_button(running=True)

    def _stop_macro(self) -> None:
        if self.engine:
            self.engine.request_stop()
            self.engine.wait(3000)
        self._time_timer.stop()

    def _set_start_button(self, running: bool) -> None:
        self.btn_start.setText("  Stop macro" if running else "  Start macro")
        self.btn_start.setIcon(icons.icon("stop" if running else "play",
                                          "#ffffff" if running else "#04222B",
                                          16))
        self.btn_start.setObjectName("danger" if running else "primary")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)

    def _on_finished(self) -> None:
        self._set_start_button(running=False)
        self._time_timer.stop()

    def _drop_now(self) -> None:
        if self.engine and self.engine.isRunning():
            self.engine.request_drop()
            self._log("manual drop pass requested", "info")
        else:
            self._log("start the macro before asking for a drop pass", "warn")

    def _tick_time(self) -> None:
        elapsed = int(time.time() - self._start_ts)
        self.tile_time.set_value(f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def _on_state(self, state: str) -> None:
        self.titlebar.status.set_state(state)

    def _on_stats(self, clicks: int, drops: int) -> None:
        self.tile_clicks.set_value(f"{clicks:,}".replace(",", "."))
        self.tile_drops.set_value(str(drops))

    def _detect_window(self) -> None:
        fragment = self.ed_window.text().strip() or "ARK"
        matches = [title for _hwnd, title in w.list_windows()
                   if fragment.lower() in title.lower()]
        if matches:
            self._log(f'window found: "{matches[0]}"', "ok")
        else:
            visible = ", ".join(t for _h, t in w.list_windows()[:8])
            self._log(f'no window contains "{fragment}". Visible titles: '
                      f"{visible}", "warn")

    # --------------------------------------------------------- game geometry
    def _game_area(self) -> tuple[int, int, int, int]:
        """(x, y, width, height) of the game area, or of the primary monitor."""
        hwnd = w.find_window(self.cfg.target.window_title)
        rect = w.client_rect(hwnd) if hwnd else None
        if rect:
            return rect
        width, height = w.screen_size()
        return 0, 0, width, height

    def _suggest_points(self) -> None:
        x, y, width, height = self._game_area()
        filter_point, drop_point = ark_layout.suggest(width, height, (x, y))
        self.sp_fx.setValue(filter_point[0])
        self.sp_fy.setValue(filter_point[1])
        self.sp_dx.setValue(drop_point[0])
        self.sp_dy.setValue(drop_point[1])
        self.cfg.drop.points_resolution = [width, height]
        self._log(f"estimated for {width}x{height}: filter {filter_point}, "
                  f"Drop All {drop_point} — verify with Test", "warn")
        self._on_change()

    def _maybe_rescale_points(self) -> None:
        """Convert the saved points if the resolution changed since capture."""
        drop = self.cfg.drop
        old = drop.points_resolution
        if not (old and all(old)):
            return
        if not (any(drop.filter_point) or any(drop.dropall_point)):
            return
        _x, _y, width, height = self._game_area()
        if [width, height] == list(old):
            return
        drop.filter_point = ark_layout.rescale(drop.filter_point, old,
                                               [width, height])
        drop.dropall_point = ark_layout.rescale(drop.dropall_point, old,
                                                [width, height])
        drop.points_resolution = [width, height]
        self.sp_fx.setValue(drop.filter_point[0])
        self.sp_fy.setValue(drop.filter_point[1])
        self.sp_dx.setValue(drop.dropall_point[0])
        self.sp_dy.setValue(drop.dropall_point[1])
        self._refresh_points_status()
        self._log(f"resolution changed from {old[0]}x{old[1]} to "
                  f"{width}x{height} — points rescaled, verify with Test",
                  "warn")

    def _test_point(self, x: int, y: int) -> None:
        if not (x or y):
            self._log("this point has not been set yet", "warn")
            return
        w.move_cursor(x, y)
        self._log(f"cursor moved to ({x}, {y})", "info")

    # ------------------------------------------------------- point picking
    def _begin_pick(self) -> None:
        if self._picker is not None:
            return
        self._log("freezing the screen — bring ARK's inventory up", "warn")
        self.hide()
        QApplication.processEvents()
        QTimer.singleShot(350, self._grab_and_pick)

    def _pick_target_screen(self):
        hwnd = w.find_window(self.cfg.target.window_title)
        rect = w.client_rect(hwnd) if hwnd else None
        if rect:
            centre = (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)
            for screen in QApplication.screens():
                geo = screen.geometry()
                ratio = screen.devicePixelRatio()
                if (geo.x() * ratio <= centre[0] < (geo.x() + geo.width()) * ratio
                        and geo.y() * ratio <= centre[1]
                        < (geo.y() + geo.height()) * ratio):
                    return screen
        return self.screen() or QApplication.primaryScreen()

    def _grab_and_pick(self) -> None:
        screen = self._pick_target_screen()
        if screen is None:
            self.show()
            self._log("no screen available to capture", "err")
            return
        shot = screen.grabWindow(0)
        shot.setDevicePixelRatio(1.0)
        geo = screen.geometry()
        ratio = screen.devicePixelRatio()
        self._shot = shot
        self._shot_origin = (round(geo.x() * ratio), round(geo.y() * ratio))
        self._pick_screen = screen
        self._pick_step(0)

    def _pick_step(self, index: int) -> None:
        steps = [
            ("filter", "Click the inventory search field",
             "The magnifier box at the top of your inventory panel. Left click "
             "to confirm, arrow keys to nudge, Esc to cancel."),
            ("dropall", "Click the Drop All button",
             "Second icon of the row, right next to the crossed arrows that "
             "mean transfer all. Left click to confirm, Esc to cancel."),
        ]
        if index >= len(steps):
            self._finish_pick()
            return
        key, title, subtitle = steps[index]
        picker = ScreenPicker(self._shot, self._pick_screen.geometry(), title,
                              subtitle, f"step {index + 1} of {len(steps)}")
        picker.picked.connect(
            lambda x, y, k=key, i=index: self._on_picked(k, x, y, i))
        picker.cancelled.connect(self._cancel_pick)
        self._drop_picker()
        self._picker = picker
        picker.show()

    def _drop_picker(self) -> None:
        if self._picker is not None:
            self._picker.deleteLater()
            self._picker = None

    def _on_picked(self, key: str, x: int, y: int, index: int) -> None:
        if key == "filter":
            self.sp_fx.setValue(x)
            self.sp_fy.setValue(y)
        else:
            self.sp_dx.setValue(x)
            self.sp_dy.setValue(y)
        self._store_thumb(key, x, y)
        self._log(f"{key} point set to ({x}, {y})", "ok")
        QTimer.singleShot(60, lambda: self._pick_step(index + 1))

    def _cancel_pick(self) -> None:
        self._drop_picker()
        self._restore_window()
        self._log("point picking cancelled", "warn")

    def _finish_pick(self) -> None:
        self._drop_picker()
        _x, _y, width, height = self._game_area()
        self.cfg.drop.points_resolution = [width, height]
        self._restore_window()
        self._on_change()
        self._log("both points captured — hit Test to confirm the cursor lands "
                  "where you expect", "ok")

    def _restore_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.nav_group.button(3).setChecked(True)
        self.stack.setCurrentIndex(3)

    # ------------------------------------------------------------ previews
    def _store_thumb(self, key: str, x: int, y: int) -> None:
        """Keep a zoomed crop of what was targeted, as a visual receipt."""
        if self._shot is None:
            return
        local_x = x - self._shot_origin[0]
        local_y = y - self._shot_origin[1]
        crop = self._shot.copy(local_x - 49, local_y - 26, 98, 52)
        if crop.isNull():
            return
        thumb: PointThumb = getattr(self, f"_thumb_{key}")
        thumb.set_pixmap(crop)
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            crop.save(str(STATE_DIR / f"{key}.png"))
        except OSError:
            pass

    def _load_thumbs(self) -> None:
        for key in ("filter", "dropall"):
            path = STATE_DIR / f"{key}.png"
            if path.exists():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    getattr(self, f"_thumb_{key}").set_pixmap(pixmap)

    def _save_shot(self, keyword: str) -> None:
        """Full screen capture taken during a dry run."""
        screen = self._pick_target_screen()
        if screen is None:
            return
        try:
            CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
            safe = "".join(c if c.isalnum() else "_" for c in keyword)[:24]
            path = CAPTURE_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{safe}.png"
            screen.grabWindow(0).save(str(path))
            self._log(f"capture saved to captures/{path.name}", "ok")
        except OSError as error:
            self._log(f"could not save the capture: {error}", "err")

    # ------------------------------------------------------------- updates
    def _refresh_version(self) -> None:
        repo = updater.local_state()
        if not repo.ok:
            self.lbl_version.setText(f"v{__version__}  ·  {repo.reason}")
            self.btn_check.setEnabled(False)
            return
        dirty = "  ·  local changes" if repo.dirty else ""
        self.lbl_version.setText(
            f"v{__version__}  ·  {repo.branch} @ {repo.sha}  ·  "
            f"committed {repo.committed}{dirty}")

    def _check_updates(self, silent: bool = False) -> None:
        if self._update_worker is not None:
            return
        self._silent_check = silent
        self.btn_check.setEnabled(False)
        if not silent:
            self.lbl_update.setText("checking…")
        worker = updater.UpdateWorker("check", self)
        worker.checked.connect(self._on_update_checked)
        worker.finished.connect(self._clear_update_worker)
        self._update_worker = worker
        worker.start()

    def _clear_update_worker(self) -> None:
        if self._update_worker is not None:
            self._update_worker.deleteLater()
            self._update_worker = None
        self.btn_check.setEnabled(True)

    def _on_update_checked(self, status: updater.Status) -> None:
        self._refresh_version()
        if not status.ok:
            self.btn_apply.hide()
            self.lbl_commits.hide()
            self.lbl_update.setText(f"check failed: {status.error}")
            if not self._silent_check:
                self._log(f"update check failed: {status.error}", "err")
            return

        if status.behind == 0:
            self.btn_apply.hide()
            self.lbl_commits.hide()
            self.titlebar.update_pill.hide()
            self.lbl_update.setText("you are on the latest commit")
            if not self._silent_check:
                self._log("already up to date", "ok")
            return

        plural = "commit" if status.behind == 1 else "commits"
        extra = ""
        if status.ahead:
            extra += f", {status.ahead} local not pushed"
        if status.requirements_changed:
            extra += " — requirements.txt changed, run pip install after"
        self.lbl_update.setText(f"{status.behind} new {plural} available{extra}")
        self.lbl_commits.setText("\n".join(f"{sha}  {subject}"
                                           for sha, subject in status.commits))
        self.lbl_commits.show()
        self.btn_apply.setEnabled(not status.dirty)
        self.btn_apply.show()
        self.titlebar.update_pill.show()
        if status.dirty:
            self.lbl_update.setText(
                f"{status.behind} new {plural}, but this folder has "
                "uncommitted changes — commit or discard them first")
        self._log(f"{status.behind} new {plural} available", "warn")

    def _apply_update(self) -> None:
        if self._update_worker is not None:
            return
        self._stop_macro()
        self._pull()
        self._save()
        self.btn_apply.setEnabled(False)
        self.lbl_update.setText("updating…")
        worker = updater.UpdateWorker("apply", self)
        worker.applied.connect(self._on_update_applied)
        worker.finished.connect(self._clear_update_worker)
        self._update_worker = worker
        worker.start()

    def _on_update_applied(self, ok: bool, message: str) -> None:
        self._refresh_version()
        if not ok:
            self.btn_apply.setEnabled(True)
            self.lbl_update.setText(f"update failed: {message}")
            self._log(f"update failed: {message}", "err")
            return
        self.lbl_update.setText(f"{message} — restarting…")
        self._log(f"{message} — restarting", "ok")
        QTimer.singleShot(700, self._restart)

    def _restart(self) -> None:
        """Relaunch from the freshly pulled source and quit this instance."""
        script = ROOT / "main.py"
        started = QProcess.startDetached(sys.executable, [str(script)],
                                         str(ROOT))
        if not started:
            self._log("could not relaunch — start the app again manually",
                      "err")
            return
        self._restarting = True
        self.close()

    # ------------------------------------------------------------- hotkeys
    def _apply_hotkeys(self, *_args) -> None:
        self._pull()
        keys = self.cfg.hotkeys
        self.hotkeys.apply({
            "toggle": keys.toggle,
            "drop_now": keys.drop_now,
            "panic": keys.panic,
            "pick_points": keys.pick_points,
        })

    def _on_hotkey(self, name: str) -> None:
        if name == "toggle":
            self._toggle_macro()
        elif name == "drop_now":
            self._drop_now()
        elif name == "panic":
            self._stop_macro()
            self._log("EMERGENCY STOP", "err")
        elif name == "pick_points":
            if self._picker is None:
                self._begin_pick()

    # ----------------------------------------------------------------- log
    def _log(self, message: str, level: str = "info") -> None:
        color = {"ok": T.OK, "warn": T.WARN, "err": T.ERR}.get(level, T.MUTED)
        stamp = time.strftime("%H:%M:%S")
        html = (f'<span style="color:{T.BORDER}">{stamp}</span> '
                f'<span style="color:{color}">{message}</span>')
        self.log_view.appendHtml(html)
        self.mini_log.appendHtml(html)

    # --------------------------------------------------------------- close
    def closeEvent(self, event) -> None:
        self._stop_macro()
        if self._update_worker is not None:
            self._update_worker.wait(3000)
        self._pull()
        self._save()
        self.hotkeys.stop()
        event.accept()
