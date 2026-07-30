"""Main window of ARK Farm Macro."""
from __future__ import annotations

import pathlib
import sys
import time
from html import escape

from PySide6.QtCore import QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                               QDoubleSpinBox, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizeGrip, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from .. import layout as ark_layout
from .. import sweep
from .. import updater
from .. import winapi as w
from ..config import Config
from ..engine import MacroEngine
from ..hotkeys import HotkeyManager
from . import icons
from . import theme as T
from .backdrop import Backdrop
from .picker import AreaPicker, ScreenPicker
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

# how often unattended updating looks for a new commit. Long on purpose: this
# fires a git fetch, and a farming session lasts hours, not seconds.
AUTO_CHECK_MIN = 20

# ARK's hotbar, in the order the keys sit on a keyboard
HOTBAR = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]


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
    body = hint_label(detail)
    text.addWidget(head)
    text.addWidget(body)
    row.addWidget(badge, 0, Qt.AlignTop)
    row.addLayout(text, 1)
    # so callers can keep wording that mentions a setting in sync with it
    row.title_label = head
    row.detail_label = body
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
        self._picking = False
        self._applying_points = False
        self._state = "idle"

        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1060, 720)
        self.setMinimumSize(940, 620)

        self._build_ui()
        self._wire_autosave()

        # timers first: _apply_hotkeys pulls the widgets, and pulling arms the
        # anti-afk timer
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save)

        self._start_ts = time.time()
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._tick_time)

        self._afk_timer = QTimer(self)
        self._afk_timer.timeout.connect(self._afk_tick)

        # hold-to-drop: one timer watches the key, the other walks the slots.
        # Two timers rather than a loop with sleeps in it, so releasing the key
        # stops the sweep on the next tick instead of at the end of a lap, and
        # the window never freezes while it runs.
        self._hold_watch = QTimer(self)
        self._hold_watch.setInterval(60)
        self._hold_watch.timeout.connect(self._watch_hold_key)
        self._sweep_timer = QTimer(self)
        self._sweep_timer.timeout.connect(self._sweep_step)
        self._sweep_path: list[tuple[int, int]] = []
        self._sweep_index = 0
        self._sweep_return: tuple[int, int] | None = None
        self._sweep_hwnd: int | None = None
        self._hold_refused = False
        # toggling acts on the press, so the level has to be remembered between
        # ticks to tell a new press from a key that is simply still down
        self._hold_was_down = False

        # unattended updates: a check on a long timer, and a pull that waits for
        # the macro to be idle before it restarts the app
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(lambda: self._check_updates(silent=True))
        self._update_pending = False
        # so the "waiting for…" line is logged once, not on every check
        self._update_held = False
        # a pull that failed once will fail the same way every 20 minutes, so
        # unattended updating stands down for the session instead of looping
        self._auto_blocked = False

        self.hotkeys = HotkeyManager()
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkeys.failed.connect(
            lambda name, key: self._log(
                f'could not register "{key}" for {name} — another program may '
                "already own it", "err"))
        self._apply_hotkeys()

        self._load_thumbs()
        self._refresh_points_status()
        self._maybe_rescale_points()
        self._maybe_rescale_area()
        self._sync_hold_drop()
        self._refresh_version()
        self.titlebar.update_pill.clicked.connect(self._open_settings)
        self._log("ready. set the two points on the Points tab before the "
                  "first run.", "info")
        self._sync_auto_update()
        if self.cfg.app.check_updates_on_start or self.cfg.app.auto_update:
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
            ("2", "Focus the filter", "clicks the search field"),
            ("3", "Type the keyword", "one enabled template at a time"),
            ("4", "Check the box", "reads it — no keyword in there, no drop"),
            ("5", "Drop All", "with the filter on, only what is listed falls"),
            ("6", "Repeat and resume",
             "the drop clears the filter, Esc closes, back to farming"),
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
        # a dozen swings is a normal pass on a rich node, so the step is one
        self.sp_every_clicks = spin(1, 100000, self.cfg.drop.every_clicks,
                                    " clicks", 1)
        self.sp_min_farm = spin(0, 3600, self.cfg.drop.min_farm_s, " s", 5)
        self.lbl_interval = tgrid.add("Interval", self.sp_interval)
        self.lbl_clicks = tgrid.add("Run every", self.sp_every_clicks)
        self.lbl_min_farm = tgrid.add("Farm for at least", self.sp_min_farm,
                                      "Both have to be met before the pass "
                                      "runs: the clicks and the time")
        trigger.add(tgrid)
        self.hint_min_farm = hint_label(
            "Clicks are not swings — a dino with its own attack cooldown burns "
            "through fourteen clicks in two seconds and lands three hits. The "
            "stretch makes sure real farming happened before the inventory "
            "opens. Zero turns it off and goes back to counting clicks alone.")
        trigger.add(self.hint_min_farm)
        lay.addWidget(trigger)

        card = Card("Drop list")
        self.tpl_editor = TemplateEditor(self.cfg.drop.templates)
        card.add(self.tpl_editor)
        card.add(hint_label(
            "ARK's filter matches any part of an item name and ignores case: "
            '"stone" also lists Stone Pick and Stone Hatchet, and Drop All '
            "takes everything listed. Rows marked ⚠ carry that risk.", warn=True))
        lay.addWidget(card)

        guard = Card(
            "Before every Drop All",
            "Waiting half a second for the filter to appear is a hope, not a "
            "check — and an unfiltered Drop All empties the whole bag. So the "
            "macro reads the search box before and after typing: no change in "
            "those pixels means nothing was typed, and the drop is skipped.")
        self.sw_verify = SwitchRow("Only drop when the keyword reached the "
                                   "search box", self.cfg.drop.verify_filter)
        guard.add(self.sw_verify)
        guard.add(hint_label(
            "It sees that there is text, not which text — a keyword that got in "
            "halfway still passes. Turn it off only to measure how often the "
            "check trips on your connection: the drop then goes out anyway and "
            "the log says the box looked empty. Needs the screen to be "
            "readable, so borderless or windowed, foreground delivery."))
        lay.addWidget(guard)

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
        self.cb_close.currentIndexChanged.connect(self._sync_close_presses)
        igrid.add("Close inventory with", self.cb_close)
        self.sp_close_presses = spin(1, 5, self.cfg.drop.close_presses, "x", 1)
        igrid.add("Presses to close", self.sp_close_presses,
                  "Only used when the screen cannot be read — otherwise the "
                  "macro checks the panel and presses until it is gone")
        self.sp_open_wait = spin(100, 8000, self.cfg.drop.open_wait_ms, " ms", 50)
        self.sp_type_wait = spin(50, 5000, self.cfg.drop.after_type_wait_ms,
                                 " ms", 50)
        self.sp_drop_wait = spin(50, 5000, self.cfg.drop.after_drop_wait_ms,
                                 " ms", 50)
        self.sp_close_wait = spin(100, 8000, self.cfg.drop.close_wait_ms, " ms", 50)
        igrid.add("Wait after opening", self.sp_open_wait)
        igrid.add("Wait after typing", self.sp_type_wait)
        igrid.add("Wait after Drop All", self.sp_drop_wait)
        igrid.add("Wait after closing", self.sp_close_wait)
        timing.add(igrid)
        timing.add(hint_label(
            "Typing the filter leaves the search field holding the keyboard, "
            "so the first Esc only steps out of it and the second is what "
            "closes the inventory. How many it takes is not guessed: the macro "
            "reads the panel on screen and presses until those pixels change, "
            "so it never stops with the inventory up and never sends a spare "
            "Esc into the game. The count above is the fallback for when the "
            "screen cannot be read — background delivery, or exclusive "
            "fullscreen."))
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
        open_step = step_row("1", "Open the inventory in ARK", "")
        self.lbl_open_step = open_step.detail_label
        guide.add(open_step)
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

        lay.addWidget(self._hold_drop_card())
        self._sync_hold_mode_note()
        lay.addStretch(1)
        return page

    # ------------------------------------------------------- hold to drop
    def _hold_drop_card(self) -> Card:
        hold = self.cfg.hold_drop
        card = Card(
            "Hold-to-drop",
            "Nothing to do with the farm loop. Hold ARK's drop key over a block "
            "of slots and the cursor sweeps them, dropping every stack it passes "
            "— for emptying a forge or a bag by hand, fast.")
        self.sw_hold = SwitchRow("Sweep the area with the drop key", hold.enabled)
        card.add(self.sw_hold)

        hgrid = FormGrid(pairs=2)
        self.cb_hold_mode = combo(["Hold the key", "Press to start and stop"],
                                  1 if hold.mode == "toggle" else 0, width=230)
        self.cb_hold_mode.currentIndexChanged.connect(self._sync_hold_mode_note)
        hgrid.add("How it runs", self.cb_hold_mode)
        hgrid.skip()
        self.hold_mode_note = hint_label("")
        card.add(hgrid)
        card.add(self.hold_mode_note)

        hgrid = FormGrid(pairs=2)
        self.ed_hold_key = QLineEdit(hold.key)
        self.ed_hold_key.setMaxLength(10)
        self.ed_hold_key.setFixedWidth(124)
        self.ed_hold_key.setAlignment(Qt.AlignCenter)
        hgrid.add("Drop key", self.ed_hold_key,
                  "Whatever ARK has bound to dropping the item under the "
                  "cursor. Default: o")
        self.sp_hold_dwell = spin(5, 1000, hold.dwell_ms, " ms", 5)
        hgrid.add("Time per slot", self.sp_hold_dwell,
                  "Too low and the game misses the hover — raise it on a "
                  "streamed session, which pays a round trip per slot")
        self.sp_hold_cols = spin(1, 20, hold.columns, "", 1)
        hgrid.add("Columns", self.sp_hold_cols)
        self.sp_hold_rows = spin(1, 20, hold.rows, "", 1)
        hgrid.add("Rows", self.sp_hold_rows)
        card.add(hgrid)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_hold_area = QPushButton("  Freeze screen and select the area")
        self.btn_hold_area.setObjectName("primary")
        self.btn_hold_area.setCursor(Qt.PointingHandCursor)
        self.btn_hold_area.setIcon(icons.icon("search", "#04222B", 16))
        self.btn_hold_area.setIconSize(QSize(16, 16))
        self.btn_hold_area.clicked.connect(self._begin_area_pick)
        row.addWidget(self.btn_hold_area, 1)
        card.add(row)

        self.lbl_hold_area = hint_label("")
        card.add(self.lbl_hold_area)
        card.add(hint_label(
            "The key is watched, never registered as a hotkey: a registered "
            "hotkey is swallowed before ARK sees it, so your own press would "
            "stop reaching the game and nothing would drop. Either mode sweeps "
            "only while ARK is in front, stops the moment it is not, and "
            "refuses while the macro is farming — an autoclick loose in an open "
            "inventory would move items around instead."))
        return card

    def _sync_hold_mode_note(self) -> None:
        if self.cb_hold_mode.currentIndex() == 1:
            self.hold_mode_note.setText(
                "One press starts the sweep, another stops it. Your finger is "
                "off the key, so the app taps it once per slot — without that a "
                "toggled sweep would tour the slots and drop nothing. The press "
                "that starts it also reaches ARK, so it drops whatever the "
                "cursor is on at that moment.")
        else:
            self.hold_mode_note.setText(
                "The sweep runs while you hold the key and stops within one "
                "slot of letting go. The app sends no keys at all here — your "
                "finger is what tells ARK to drop.")

    def _point_card(self, title: str, subtitle: str, point: list[int], key: str):
        card = Card(title, subtitle)
        thumb = PointThumb()
        card.add(thumb)

        coords = QHBoxLayout()
        coords.setSpacing(8)
        # negative coordinates are legitimate: a monitor placed left of or
        # above the primary one lives at negative virtual-desktop offsets
        x_box = spin(-30000, 30000, point[0] if point else 0)
        y_box = spin(-30000, 30000, point[1] if len(point) > 1 else 0)
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
        self.cb_platform = combo(["Native (installed game)", "GeForce NOW"],
                                 0 if self.cfg.target.platform == "native" else 1,
                                 width=230)
        self.cb_platform.currentIndexChanged.connect(self._on_platform_changed)
        self.cb_mode = combo(["Foreground (recommended)", "Background (experimental)"],
                             0 if self.cfg.target.mode == "foreground" else 1,
                             width=230)
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        mgrid = FormGrid(pairs=1)
        mgrid.add("Where ARK runs", self.cb_platform)
        mgrid.add("Delivery mode", self.cb_mode)
        target.add(mgrid)
        self.platform_note = hint_label("")
        target.add(self.platform_note)
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
        self.sp_latency = spin(0, 3000, self.cfg.target.stream_latency_ms,
                               " ms", 25)
        wgrid.add("Stream latency", self.sp_latency,
                  "Added to every wait in the drop routine. Zero on an "
                  "installed game; raise it until the cycle stops racing the "
                  "video feed")
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

        feed = Card(
            "Auto-feed",
            "Presses two hotbar slots on a timer so the character eats and "
            "drinks without you. Put the food on one slot and a full waterskin "
            "or canteen on the other.")
        self.sw_feed = SwitchRow("Feed while farming", self.cfg.auto_feed.enabled)
        feed.add(self.sw_feed)
        fgrid = FormGrid(pairs=2)
        self.sp_feed_interval = spin(30, 7200, self.cfg.auto_feed.interval_s,
                                     " s", 30)
        fgrid.add("Feed every", self.sp_feed_interval,
                  "360 s is six minutes — often enough for the usual food and "
                  "water drain")
        self.sp_feed_gap = spin(50, 3000, self.cfg.auto_feed.gap_ms, " ms", 50)
        fgrid.add("Gap between presses", self.sp_feed_gap,
                  "So the game does not fold the two into one keystroke")
        self.cb_food = combo(HOTBAR, HOTBAR.index(self.cfg.auto_feed.food_key)
                             if self.cfg.auto_feed.food_key in HOTBAR else 3,
                             width=124)
        fgrid.add("Food slot", self.cb_food)
        self.cb_water = combo(HOTBAR, HOTBAR.index(self.cfg.auto_feed.water_key)
                              if self.cfg.auto_feed.water_key in HOTBAR else 4,
                              width=124)
        fgrid.add("Water slot", self.cb_water)
        feed.add(fgrid)
        self.feed_note = hint_label("")
        feed.add(self.feed_note)
        feed.add(hint_label(
            "It fires from inside the farming loop, never during a drop pass: a "
            "hotbar key sent while the search field has the keyboard would land "
            "in the filter as a digit instead of reaching the hotbar. It also "
            "waits while ARK is not in front, so the presses cannot go into "
            "whatever you are doing instead. What it cannot do is see your food "
            "bar — it presses the slot, and an empty slot presses nothing."))
        lay.addWidget(feed)

        afk = Card("Anti-AFK",
                   "A cloud session gets dropped when it sees no input for a "
                   "while. This taps one key on a timer to keep it alive — "
                   "F13 to F24 exist in the keyboard protocol but not on real "
                   "keyboards, so ARK has nothing bound to them and the tick "
                   "cannot touch the game.")
        self.sw_afk = SwitchRow("Keep the session awake",
                                self.cfg.anti_afk.enabled)
        afk.add(self.sw_afk)
        agrid = FormGrid(pairs=2)
        self.sp_afk_interval = spin(5, 3600, self.cfg.anti_afk.interval_s,
                                    " s", 15)
        agrid.add("Tick every", self.sp_afk_interval)
        self.ed_afk_key = QLineEdit(self.cfg.anti_afk.key)
        self.ed_afk_key.setFixedWidth(124)
        self.ed_afk_key.setAlignment(Qt.AlignCenter)
        agrid.add("Key to tap", self.ed_afk_key,
                  "Key name: f15, f16, scrolllock...")
        afk.add(agrid)
        afk.add(hint_label(
            "It only ticks while the target window has focus, and never in the "
            "middle of a drop pass. With the macro farming there is already "
            "plenty of input, so this is what covers the gaps."))
        lay.addWidget(afk)

        lay.addWidget(self._updates_card())
        lay.addStretch(1)
        self._sync_feed_note()
        self._sync_delivery_options(announce=False)
        self._sync_mode_note()
        self._sync_platform_note()
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
        self.sw_auto_update = SwitchRow("Update on its own, no button",
                                        self.cfg.app.auto_update)
        card.add(self.sw_auto_update)
        card.add(hint_label(
            f"Checks every {AUTO_CHECK_MIN} minutes as well as at start, and "
            "pulls without asking. A new commit reaches this app with nothing "
            "for you to click — and nothing to review either, so whatever is "
            "pushed is what you farm with. It never restarts mid-farm or under "
            "the point picker: an update that lands then is held until you are "
            "done. It stands aside for a folder with uncommitted changes, and "
            "for a commit that changes requirements.txt — restarting into "
            "dependencies you have not installed would not come back up."))
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
        self.lbl_min_farm.setVisible(index == 1)
        self.sp_min_farm.setVisible(index == 1)
        self.hint_min_farm.setVisible(index == 1)

    def _sync_close_presses(self) -> None:
        """
        Move the press count with the key that will be sent.

        Esc goes twice: once to step out of the search field, once to close the
        panel. The inventory key toggles instead, so a repeat would open it
        straight back up.
        """
        esc = self.cb_close.currentIndex() == 1
        if esc and self.sp_close_presses.value() < 2:
            self.sp_close_presses.setValue(2)
        elif not esc and self.sp_close_presses.value() > 1:
            self.sp_close_presses.setValue(1)

    @property
    def _streaming(self) -> bool:
        return self.cb_platform.currentIndex() == 1

    def _on_platform_changed(self) -> None:
        """Move the defaults that streaming actually changes, and say so."""
        if self._streaming:
            if self.ed_window.text().strip() in ("", "ARK"):
                self.ed_window.setText("GeForce NOW")
            if self.sp_latency.value() == 0:
                self.sp_latency.setValue(250)
            self._log("GeForce NOW: targeting the client window and adding "
                      "250 ms to every wait — recapture your points, the HUD "
                      "sits inside the video, not the window", "warn")
        else:
            if self.ed_window.text().strip() == "GeForce NOW":
                self.ed_window.setText("ARK")
            if self.sp_latency.value() == 250:
                self.sp_latency.setValue(0)
        self._sync_delivery_options()
        self._sync_platform_note()
        self._sync_mode_note()
        self._on_change()

    def _on_mode_changed(self) -> None:
        # the check runs on every change, not only when the platform moves: a
        # stored config or a stray setCurrentIndex must not land on a delivery
        # mode that cannot reach the game
        self._sync_delivery_options()
        self._sync_mode_note()

    def _sync_delivery_options(self, announce: bool = True) -> None:
        """
        Background delivery is not offered for a streamed session.

        It cannot work: the client grabs real input and forwards it over the
        network, so a posted message reaches its window and stops there. Leaving
        it selectable only buys a session that farms nothing.

        `announce` is off while the pages are still being built — the log view
        does not exist yet at that point.
        """
        item = self.cb_mode.model().item(1)
        if item is not None:
            item.setEnabled(not self._streaming)
        if self._streaming and self.cb_mode.currentIndex() == 1:
            self.cb_mode.setCurrentIndex(0)
            if announce:
                self._log("background delivery cannot reach a GeForce NOW "
                          "session — switched back to foreground", "warn")

    def _sync_platform_note(self) -> None:
        if self._streaming:
            self.platform_note.setText(
                "The GeForce NOW client forwards your real mouse and keyboard "
                "to the server, so foreground input works exactly as it does "
                "on an installed game — just one round trip later. Point "
                "estimates measure the video inside the window, ignoring the "
                "black bars.")
        else:
            self.platform_note.setText(
                "The game is installed and running on this machine.")

    def _sync_mode_note(self) -> None:
        if self._streaming:
            self.mode_note.setText(
                "Background is greyed out on GeForce NOW, and no setting can "
                "bring it back: the client forwards real input from whatever "
                "has focus, so a message posted to its window never enters the "
                "stream. Farming while you use the PC needs a second machine, "
                "or ARK streamed inside a VM with the macro running in the "
                "guest — see the README.")
            return
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
        if hasattr(self, "lbl_open_step"):
            self.lbl_open_step.setText(
                f"exactly the state the macro will use — inventory alone with "
                f"«{drop.inventory_key.upper()}», or with a storage box open. "
                "The icon row sits in a different place in each.")
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
            self.sp_every_clicks, self.sp_min_farm, self.ed_inv_key,
            self.cb_close,
            self.sp_close_presses,
            self.sp_open_wait, self.sp_close_wait, self.sp_type_wait,
            self.sp_drop_wait, self.sw_verify.switch, self.sp_fx, self.sp_fy,
            self.sp_dx, self.sp_dy, self.cb_mode, self.ed_window,
            self.sw_focus.switch, self.sp_delay, self.chk_unicode,
            self.hk_toggle, self.hk_drop, self.hk_panic, self.hk_pick,
            self.sw_dry.switch, self.sw_updates.switch,
            self.sw_auto_update.switch, self.cb_platform,
            self.sp_latency, self.sw_afk.switch, self.sp_afk_interval,
            self.ed_afk_key, self.sw_feed.switch, self.sp_feed_interval,
            self.sp_feed_gap, self.cb_food, self.cb_water,
            self.sw_hold.switch, self.ed_hold_key, self.sp_hold_cols,
            self.sp_hold_rows, self.sp_hold_dwell, self.cb_hold_mode,
        ]
        for widget in widgets:
            for name in ("valueChanged", "currentIndexChanged", "textChanged",
                         "toggled", "captured"):
                signal = getattr(widget, name, None)
                if signal is not None:
                    signal.connect(self._on_change)
                    break
        self.tpl_editor.changed.connect(self._on_change)
        for box in (self.sp_fx, self.sp_fy):
            box.valueChanged.connect(lambda *_: self._invalidate_thumb("filter"))
        for box in (self.sp_dx, self.sp_dy):
            box.valueChanged.connect(lambda *_: self._invalidate_thumb("dropall"))

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
        drop.min_farm_s = self.sp_min_farm.value()
        drop.inventory_key = self.ed_inv_key.text().strip().lower() or "i"
        drop.close_with = "same" if self.cb_close.currentIndex() == 0 else "esc"
        drop.close_presses = self.sp_close_presses.value()
        drop.open_wait_ms = self.sp_open_wait.value()
        drop.close_wait_ms = self.sp_close_wait.value()
        drop.after_type_wait_ms = self.sp_type_wait.value()
        drop.after_drop_wait_ms = self.sp_drop_wait.value()
        drop.verify_filter = self.sw_verify.switch.isChecked()
        drop.filter_point = [self.sp_fx.value(), self.sp_fy.value()]
        drop.dropall_point = [self.sp_dx.value(), self.sp_dy.value()]
        drop.templates = self.tpl_editor.templates()
        drop.dry_run = self.sw_dry.switch.isChecked()
        drop.unicode_typing = self.chk_unicode.isChecked()

        target = self.cfg.target
        target.mode = ("foreground" if self.cb_mode.currentIndex() == 0
                       else "background")
        target.platform = "geforce_now" if self._streaming else "native"
        target.window_title = self.ed_window.text().strip() or "ARK"
        target.require_focus = self.sw_focus.switch.isChecked()
        target.start_delay_s = self.sp_delay.value()
        target.stream_latency_ms = self.sp_latency.value()

        hold = self.cfg.hold_drop
        hold.enabled = self.sw_hold.switch.isChecked()
        hold.key = self.ed_hold_key.text().strip().lower() or "o"
        hold.mode = "toggle" if self.cb_hold_mode.currentIndex() == 1 else "hold"
        hold.columns = self.sp_hold_cols.value()
        hold.rows = self.sp_hold_rows.value()
        hold.dwell_ms = self.sp_hold_dwell.value()
        self._sync_hold_drop()

        feed = self.cfg.auto_feed
        feed.enabled = self.sw_feed.switch.isChecked()
        feed.interval_s = self.sp_feed_interval.value()
        feed.gap_ms = self.sp_feed_gap.value()
        feed.food_key = self.cb_food.currentText()
        feed.water_key = self.cb_water.currentText()
        self._sync_feed_note()

        afk = self.cfg.anti_afk
        afk.enabled = self.sw_afk.switch.isChecked()
        afk.interval_s = self.sp_afk_interval.value()
        afk.key = self.ed_afk_key.text().strip().lower() or "f15"
        self._sync_afk()

        keys = self.cfg.hotkeys
        keys.toggle = self.hk_toggle.text() or keys.toggle
        keys.drop_now = self.hk_drop.text() or keys.drop_now
        keys.panic = self.hk_panic.text() or keys.panic
        keys.pick_points = self.hk_pick.text() or keys.pick_points
        self.cfg.app.check_updates_on_start = self.sw_updates.switch.isChecked()
        self.cfg.app.auto_update = self.sw_auto_update.switch.isChecked()
        self._sync_auto_update()
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
        if self._picking:
            self._log("finish picking the points before starting", "warn")
            return
        # the sweep moves the mouse; the autoclick is about to want it
        self._stop_sweep()
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
        if self._update_pending:
            # the farm is over, so the restart is free now
            QTimer.singleShot(400, self._auto_apply)

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
        self._state = state
        self.titlebar.status.set_state(state)

    # ---------------------------------------------------------- hold to drop
    def _sync_hold_drop(self) -> None:
        hold = self.cfg.hold_drop
        ready = hold.enabled and sweep.usable(hold.area)
        if ready:
            vk = w.vk_from_name(hold.key)
            # a key that is already down as this arms is not a fresh press, or
            # switching the mode on with a finger on the key would start a sweep
            self._hold_was_down = bool(vk is not None and w.key_is_down(vk))
            self._hold_watch.start()
        else:
            self._hold_watch.stop()
            self._stop_sweep()
        self._refresh_hold_status()

    def _refresh_hold_status(self) -> None:
        hold = self.cfg.hold_drop
        if not sweep.usable(hold.area):
            self.lbl_hold_area.setText(
                "No area selected yet — hold-to-drop will not do anything until "
                "you pick one on a frozen screen.")
            return
        x, y, width, height = hold.area
        slots = hold.columns * hold.rows
        pace = slots * hold.dwell_ms / 1000.0
        res = hold.area_resolution
        where = f", captured at {res[0]}x{res[1]}" if res and all(res) else ""
        driven = (f"a press of «{hold.key.upper()}» starts it, another stops it"
                  if hold.mode == "toggle"
                  else f"it loops while «{hold.key.upper()}» is held")
        self.lbl_hold_area.setText(
            f"{width}x{height} px at ({x}, {y}){where} — {hold.columns}x"
            f"{hold.rows} = {slots} slots, about {pace:.1f}s per lap, and "
            f"{driven}.")

    def _can_sweep(self) -> bool:
        """Whether it is safe to start a sweep right now, and say why not once."""
        if self._picking:
            return False
        # an autoclick loose in an open inventory moves items around; the sweep
        # would be the least of the damage
        if self.engine is not None and self.engine.isRunning():
            if not self._hold_refused:
                self._hold_refused = True
                self._log("hold-to-drop ignored while the macro is farming — "
                          "stop it first", "warn")
            return False
        return w.is_foreground(w.find_window(self.cfg.target.window_title))

    def _watch_hold_key(self) -> None:
        """
        Drive the sweep from the drop key.

        Holding reads the key's level; toggling reads its edge, so the press is
        acted on once and the release means nothing.
        """
        hold = self.cfg.hold_drop
        vk = w.vk_from_name(hold.key)
        if vk is None:
            self._log(f'hold-to-drop: "{hold.key}" is not a key name', "err")
            self._hold_watch.stop()
            return
        down = w.key_is_down(vk)
        pressed = down and not self._hold_was_down
        self._hold_was_down = down

        if hold.mode == "toggle":
            if not pressed:
                return
            if self._sweep_timer.isActive():
                self._stop_sweep()
            elif self._can_sweep():
                self._start_sweep()
            return

        if not down:
            self._stop_sweep()
            self._hold_refused = False
            return
        if self._sweep_timer.isActive():
            return
        if self._can_sweep():
            self._start_sweep()

    def _start_sweep(self) -> None:
        hold = self.cfg.hold_drop
        path = sweep.serpentine(hold.area, hold.columns, hold.rows)
        if not path:
            return
        self._sweep_path = path
        self._sweep_return = w.get_cursor_pos()
        # remembered rather than looked up every tick: find_window walks every
        # window on the desktop, and this runs 25 times a second
        self._sweep_hwnd = w.find_window(self.cfg.target.window_title)
        # step onto the first slot here, so it gets a full dwell before the tick
        # that presses the key on it
        w.move_cursor(*path[0])
        self._sweep_index = 1
        self._sweep_timer.start(hold.dwell_ms)
        how = ("press again to stop" if hold.mode == "toggle"
               else "while the key is held")
        self._log(f"hold-to-drop: sweeping {len(path)} slots, {how}", "info")

    def _sweep_step(self) -> None:
        """
        One slot per tick, looping, until it is told to stop.

        The key is pressed here only when toggling. While the key is *held*
        there is nothing to send — the player's own finger is already telling
        ARK to drop, and a press on top of that would be a second drop.
        """
        hold = self.cfg.hold_drop
        vk = w.vk_from_name(hold.key)
        if vk is None or not self._sweep_path:
            self._stop_sweep()
            return
        # re-checked here and not only on the watch timer: this runs far more
        # often, so the sweep stops within one slot of the key being released
        if hold.mode == "hold" and not w.key_is_down(vk):
            self._stop_sweep()
            return
        # in either mode, a game that is no longer in front means the cursor and
        # the presses are landing in somebody else's window
        if not w.is_foreground(self._sweep_hwnd):
            self._stop_sweep()
            return
        if hold.mode == "toggle":
            # the cursor has been resting on this slot for a full dwell
            w.tap(vk, hold=0.03)
        x, y = self._sweep_path[self._sweep_index % len(self._sweep_path)]
        w.move_cursor(x, y)
        self._sweep_index += 1

    def _stop_sweep(self) -> None:
        if not self._sweep_timer.isActive():
            return
        self._sweep_timer.stop()
        laps = self._sweep_index / max(len(self._sweep_path), 1)
        # put the pointer back where it was, so releasing the key does not leave
        # the cursor parked on some slot in the middle of the panel
        if self._sweep_return:
            w.move_cursor(*self._sweep_return)
            self._sweep_return = None
        self._log(f"hold-to-drop: stopped after {self._sweep_index} slots "
                  f"({laps:.1f} laps)", "ok")

    # ------------------------------------------------------------ auto feeding
    def _sync_feed_note(self) -> None:
        """
        Say what is wrong with the two slots while it is still being set up.

        The engine refuses the same cases when it arms, but finding out then
        means finding out from a red line in the log, mid-session.
        """
        feed = self.cfg.auto_feed
        if feed.food_key == feed.water_key:
            self.feed_note.setText(
                f"Food and water are both on slot {feed.food_key} — the second "
                "press would eat again instead of drinking. Auto-feed will "
                "refuse to arm.")
        elif self.cfg.drop.inventory_key in (feed.food_key, feed.water_key):
            self.feed_note.setText(
                f"Slot {self.cfg.drop.inventory_key} is also your inventory key "
                "— that press would open the panel while the macro is farming. "
                "Auto-feed will refuse to arm.")
        else:
            self.feed_note.setText(
                f"Eats from slot {feed.food_key}, drinks from slot "
                f"{feed.water_key}, every {feed.interval_s}s.")

    # --------------------------------------------------------- auto updating
    def _sync_auto_update(self) -> None:
        if self.cfg.app.auto_update:
            self._auto_timer.start(AUTO_CHECK_MIN * 60 * 1000)
        else:
            self._auto_timer.stop()
            self._update_pending = False

    # -------------------------------------------------------------- anti-afk
    def _sync_afk(self) -> None:
        afk = self.cfg.anti_afk
        if afk.enabled:
            self._afk_timer.start(max(afk.interval_s, 5) * 1000)
        else:
            self._afk_timer.stop()

    def _afk_tick(self) -> None:
        """One harmless key, only when it cannot get in the way."""
        if self._picking or self._state == "dropping":
            return
        vk = w.vk_from_name(self.cfg.anti_afk.key)
        if vk is None:
            self._log(f'anti-afk: "{self.cfg.anti_afk.key}" is not a key name',
                      "err")
            self._afk_timer.stop()
            return
        hwnd = w.find_window(self.cfg.target.window_title)
        if not w.is_foreground(hwnd):
            # typing into whatever the user is actually doing would be rude,
            # and the stream would not see it anyway
            return
        w.tap(vk, hold=0.03)

    def _on_stats(self, clicks: int, drops: int) -> None:
        self.tile_clicks.set_value(f"{clicks:,}")
        self.tile_drops.set_value(str(drops))

    def _detect_window(self) -> None:
        fragment = self.ed_window.text().strip() or "ARK"
        titles = dict(w.list_windows())
        matches = [title for title in titles.values()
                   if fragment.lower() in title.lower()]
        chosen = w.find_window(fragment)
        if not chosen:
            visible = ", ".join(list(titles.values())[:8])
            self._log(f'no window contains "{fragment}". Visible titles: '
                      f"{visible}", "warn")
            return

        rect = w.client_rect(chosen)
        size = f"{rect[2]}x{rect[3]}" if rect else "unknown size"
        self._log(f'targeting "{titles.get(chosen, "?")}" ({size})', "ok")
        if len(matches) > 1:
            others = ", ".join(f'"{t}"' for t in matches
                               if t != titles.get(chosen))
            self._log(f"{len(matches)} windows match that text — also {others}. "
                      "Make the title more specific if the wrong one wins.",
                      "warn")

    # --------------------------------------------------------- game geometry
    def _game_area(self) -> tuple[int, int, int, int]:
        """
        (x, y, width, height) the HUD is anchored to.

        On a streaming client that is the picture inside the window, not the
        window itself — the black bars are not part of the game.
        """
        hwnd = w.find_window(self.cfg.target.window_title)
        rect = w.client_rect(hwnd) if hwnd else None
        if rect is None:
            width, height = w.screen_size()
            rect = (0, 0, width, height)
        if self.cfg.target.platform == "geforce_now":
            return ark_layout.video_area(*rect)
        return rect

    def _suggest_points(self) -> None:
        x, y, width, height = self._game_area()
        filter_point, drop_point = ark_layout.suggest(width, height, (x, y))
        # a window narrower than the HUD model puts the estimate off its left
        # edge; the spin boxes would clamp it to 0 and hand back a silent lie
        inside = all(x <= point[0] < x + width and y <= point[1] < y + height
                     for point in (filter_point, drop_point))
        if not inside:
            self._log(f"cannot estimate for a {width}x{height} target — that is "
                      "too narrow for ARK's HUD. Check the window title on the "
                      "Settings tab, or pick the points on a frozen screen.",
                      "err")
            return
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

    def _maybe_rescale_area(self) -> None:
        """
        Convert the hold-to-drop area if the screen changed since it was picked.

        The area is in screen pixels, not game pixels: it is dragged over a
        screenshot of the whole desktop, so the screen is what it scales with.
        """
        hold = self.cfg.hold_drop
        old = hold.area_resolution
        if not (old and all(old)) or not sweep.usable(hold.area):
            return
        width, height = w.screen_size()
        if [width, height] == list(old):
            return
        hold.area = sweep.rescale(hold.area, old, [width, height])
        hold.area_resolution = [width, height]
        self._refresh_hold_status()
        self._log(f"screen changed from {old[0]}x{old[1]} to {width}x{height} — "
                  "hold-to-drop area rescaled, check it before using it", "warn")

    def _test_point(self, x: int, y: int) -> None:
        if not (x or y):
            self._log("this point has not been set yet", "warn")
            return
        w.move_cursor(x, y)
        self._log(f"cursor moved to ({x}, {y})", "info")

    # ------------------------------------------------------- point picking
    def _begin_pick(self) -> None:
        if self._picking:
            return
        # a running macro would keep firing clicks into the overlay
        if self.engine is not None and self.engine.isRunning():
            self._stop_macro()
            self._log("macro stopped so it does not click into the picker",
                      "warn")
        self._picking = True
        self._log("freezing the screen — bring ARK's inventory up", "warn")
        self.hide()
        QApplication.processEvents()
        QTimer.singleShot(350, self._grab_and_pick)

    def _begin_area_pick(self) -> None:
        if self._picking:
            return
        if self.engine is not None and self.engine.isRunning():
            self._stop_macro()
            self._log("macro stopped so it does not click into the picker",
                      "warn")
        self._stop_sweep()
        self._picking = True
        self._log("freezing the screen — open the container you want to empty",
                  "warn")
        self.hide()
        QApplication.processEvents()
        QTimer.singleShot(350, self._grab_and_pick_area)

    def _grab_and_pick_area(self) -> None:
        screen = self._pick_target_screen()
        if screen is None:
            self._picking = False
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
        picker = AreaPicker(shot, geo, self.sp_hold_cols.value(),
                            self.sp_hold_rows.value(), self._shot_origin)
        picker.picked.connect(self._on_area_picked)
        picker.cancelled.connect(self._cancel_pick)
        self._drop_picker()
        self._picker = picker
        picker.show()

    def _on_area_picked(self, x: int, y: int, width: int, height: int) -> None:
        self.cfg.hold_drop.area = [x, y, width, height]
        screen_w, screen_h = w.screen_size()
        self.cfg.hold_drop.area_resolution = [screen_w, screen_h]
        self._drop_picker()
        self._picking = False
        self._restore_window()
        self._log(f"hold-to-drop area set: {width}x{height} px at ({x}, {y})",
                  "ok")
        self._pull()
        self._save()

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
            self._picking = False
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
        self._applying_points = True   # these edits come with a fresh preview
        if key == "filter":
            self.sp_fx.setValue(x)
            self.sp_fy.setValue(y)
        else:
            self.sp_dx.setValue(x)
            self.sp_dy.setValue(y)
        self._applying_points = False
        self._store_thumb(key, x, y)
        self._log(f"{key} point set to ({x}, {y})", "ok")
        QTimer.singleShot(60, lambda: self._pick_step(index + 1))

    def _cancel_pick(self) -> None:
        self._drop_picker()
        self._picking = False
        self._restore_window()
        self._log("picking cancelled", "warn")

    def _finish_pick(self) -> None:
        self._drop_picker()
        self._picking = False
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
    def _invalidate_thumb(self, key: str) -> None:
        """
        A hand-typed or rescaled coordinate no longer matches the old crop.

        The preview is meant to be proof of what you targeted, so a stale one
        is worse than none at all.
        """
        if self._applying_points:
            return
        thumb: PointThumb = getattr(self, f"_thumb_{key}")
        if not thumb.has_preview:
            return
        thumb.clear()
        try:
            (STATE_DIR / f"{key}.png").unlink(missing_ok=True)
        except OSError:
            pass

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
        self.btn_check.setEnabled(repo.ok)
        if not repo.ok:
            self.lbl_version.setText(f"v{__version__}  ·  {repo.reason}")
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
        # _refresh_version decides: outside a git clone there is nothing to check
        self._refresh_version()

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

        if not self.cfg.app.auto_update or status.dirty:
            return
        if status.requirements_changed:
            # pulling here would restart into an app whose dependencies are not
            # installed yet, and it would not come back up. Better to stay on
            # the old commit, running, and let the button drive this one.
            self._log("update needs new dependencies — not pulling on its own. "
                      "Use Update and restart, then run the pip install", "err")
            return
        self._auto_apply()

    def _auto_apply(self) -> None:
        """
        Pull without being asked — but never on top of a running macro.

        Restarting mid-pass would leave the inventory open and the session
        farming nothing, so the update waits for the macro to stop. `_on_finished`
        picks the pending flag back up. A restart under the point picker would
        take the frozen screen with it, so that waits too — for the next check,
        since picking ends without an engine signal.
        """
        if self._auto_blocked:
            return
        busy = ""
        if self.engine and self.engine.isRunning():
            busy = "the macro to stop"
            self._update_pending = True
        elif self._picking:
            busy = "the point picker to close"
        if busy:
            if not self._update_held:
                self._update_held = True
                self._log(f"update waiting for {busy} before it restarts the "
                          "app", "warn")
            return
        self._update_held = False
        self._update_pending = False
        self._log("updating on its own", "warn")
        self._apply_update()

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
            if self.cfg.app.auto_update and not self._auto_blocked:
                self._auto_blocked = True
                self._log("updating on its own is paused for this session — "
                          "the same pull would fail again every "
                          f"{AUTO_CHECK_MIN} minutes. Use the button once the "
                          "reason above is fixed", "warn")
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
        # messages carry window titles, which any program on the machine can
        # set — an unescaped "<" would eat the rest of the line
        line = (f'<span style="color:{T.BORDER}">{stamp}</span> '
                f'<span style="color:{color}">{escape(message)}</span>')
        self.log_view.appendHtml(line)
        self.mini_log.appendHtml(line)

    # --------------------------------------------------------------- close
    def closeEvent(self, event) -> None:
        self._afk_timer.stop()
        self._auto_timer.stop()
        self._hold_watch.stop()
        self._stop_sweep()
        # the macro stopping here must not kick off a pull on the way out
        self._update_pending = False
        self._stop_macro()
        if self._update_worker is not None:
            self._update_worker.wait(3000)
        self._pull()
        self._save()
        self.hotkeys.stop()
        event.accept()
