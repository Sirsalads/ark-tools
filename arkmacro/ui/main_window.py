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
from .widgets import (Card, Divider, FormGrid, HotkeyEdit, KeyRow, NavButton,
                      PointThumb, StatTile, SwitchRow, TemplateEditor, TitleBar,
                      hint_label)

# (icon, label, section header shown above it — blank to continue the group).
# Grouped by what a page is *for*: the one you drive from, the three macros,
# and the two that are neither.
NAV = [
    ("gauge", "Dashboard", "CONTROL"),
    ("pickaxe", "Farm", "MACROS"),
    ("hand-drop", "Drop", ""),
    ("layers", "Overcap skin", ""),
    ("sliders", "Settings", "SYSTEM"),
    ("terminal", "Log", ""),
]

PAGE_DASHBOARD, PAGE_FARM, PAGE_DROP, PAGE_OVERCAP, PAGE_SETTINGS, PAGE_LOG = \
    range(len(NAV))

APP_NAME = "A.N.S Tools"

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / "state"
CAPTURE_DIR = ROOT / "captures"

# how often unattended updating looks for a new commit. Long on purpose: this
# fires a git fetch, and a farming session lasts hours, not seconds.
AUTO_CHECK_MIN = 20

# ARK's hotbar, in the order the keys sit on a keyboard
HOTBAR = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]

# hold-to-drop run modes, in the order the combo lists them
HOLD_MODES = ["toggle", "hold", "manual"]


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


def heading(title: str, subtitle: str, kicker: str = "") -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(4)
    if kicker:
        eyebrow = QLabel(kicker)
        eyebrow.setObjectName("pageKicker")
        box.addWidget(eyebrow)
        box.addSpacing(2)
    label = QLabel(title)
    label.setObjectName("pageTitle")
    sub = QLabel(subtitle)
    sub.setObjectName("pageSub")
    sub.setWordWrap(True)
    sub.setMinimumWidth(1)
    box.addWidget(label)
    box.addWidget(sub)
    return box


def group_label(text: str) -> QLabel:
    """Small caps rule inside a card, for grouping rows that belong together."""
    label = QLabel(text)
    label.setObjectName("groupLabel")
    return label


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
        self._hold_watch.timeout.connect(self._watch_keys)
        # which feature owns the running sweep: they share one cursor, so only
        # one of them can be moving it
        self._sweep_kind = ""
        self._sweep_timer = QTimer(self)
        self._sweep_timer.timeout.connect(self._sweep_step)
        self._sweep_path: list[tuple[int, int]] = []
        self._sweep_index = 0
        self._sweep_return: tuple[int, int] | None = None
        self._sweep_hwnd: int | None = None
        self._pick_area_kind = "drop"
        self._skin_was_down = False
        # whether the macro currently has Shift + a slot pressed down
        self._chord_held = False
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
        self._go(PAGE_SETTINGS)

    def _go(self, index: int) -> None:
        """Move the nav and the stack together — they are one thing to a user."""
        self.nav_group.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)

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
        self.stack.addWidget(self._page_farm())
        self.stack.addWidget(self._page_drop())
        self.stack.addWidget(self._page_overcap())
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

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (glyph, name, section) in enumerate(NAV):
            if section:
                if index:
                    lay.addSpacing(14)
                label = QLabel(section)
                label.setObjectName("navSection")
                lay.addWidget(label)
                lay.addSpacing(6)
            button = NavButton(glyph, name)
            button.setChecked(index == 0)
            self.nav_group.addButton(button, index)
            lay.addWidget(button)
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
            "Everything runs from the keys below. Keep ARK in front — the farm "
            "macro pauses by itself the moment it is not.", kicker="CONTROL"))

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.tile_clicks = StatTile("clicks", "0")
        self.tile_drops = StatTile("drop passes", "0")
        self.tile_time = StatTile("uptime", "00:00")
        for tile in (self.tile_clicks, self.tile_drops, self.tile_time):
            stats.addWidget(tile, 1)
        lay.addLayout(stats)

        control = Card("Farm macro", accent=True, icon="pickaxe")
        row = QHBoxLayout()
        row.setSpacing(11)
        self.btn_start = QPushButton("  Start macro")
        self.btn_start.setObjectName("primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setIconSize(QSize(16, 16))
        self.btn_start.setIcon(icons.icon("play", "#04222B", 16))
        self.btn_start.clicked.connect(self._toggle_macro)
        self.btn_drop = QPushButton("  Drop now")
        self.btn_drop.setIcon(icons.icon("hand-drop", T.TEXT_DIM, 15))
        self.btn_drop.setIconSize(QSize(15, 15))
        self.btn_drop.setCursor(Qt.PointingHandCursor)
        self.btn_drop.clicked.connect(self._drop_now)
        row.addWidget(self.btn_start, 2)
        row.addWidget(self.btn_drop, 1)
        control.add(row)

        self.lbl_ready = hint_label("")
        control.add(self.lbl_ready)
        lay.addWidget(control)

        lay.addWidget(self._keys_card())

        self.mini_log = QPlainTextEdit()
        self.mini_log.setObjectName("log")
        self.mini_log.setReadOnly(True)
        self.mini_log.setMaximumBlockCount(80)
        self.mini_log.setFixedHeight(118)
        lay.addWidget(self.mini_log)

        lay.addStretch(1)
        self._refresh_hotkey_chips()
        return page

    def _keys_card(self) -> Card:
        """
        Every key the app answers to, in one place.

        Split by what the key *is*: the four global ones work anywhere and are
        the app's own, and the two macro keys only mean something with ARK in
        front. Reading them as one list was the confusing part.
        """
        card = Card("Your keys", "What each one does, and when it applies.",
                    icon="keyboard")

        card.add(group_label("GLOBAL · anywhere, any time"))
        self.key_rows: dict[str, KeyRow] = {}
        for name, title, detail, tone in (
            ("toggle", "Start / stop the farm macro",
             "clicking, the drop passes, auto-feed — all of it", T.OK),
            ("drop_now", "Run a drop pass now",
             "empties the checked templates without waiting for the trigger",
             T.ACCENT),
            ("panic", "Emergency stop",
             "drops everything the app is doing, at once", T.ERR),
            ("pick_points", "Freeze the screen and pick",
             "for capturing the two farm points and the two areas", T.ACCENT),
        ):
            row = KeyRow("", title, detail, tone)
            self.key_rows[name] = row
            card.add(row)

        card.add(Divider())
        card.add(group_label("IN GAME · only with ARK in front"))
        for name, title, detail in (
            ("hold", "Sweep a block of slots",
             "drop everything in the area you picked, on the Drop page"),
            ("skin", "Run the hotbar strip",
             "the macro holds Shift + a slot for you, on the Overcap skin page"),
        ):
            row = KeyRow("", title, detail, T.WARN)
            self.key_rows[name] = row
            card.add(row)
        return card

    # ----------------------------------------------------------------- farm
    def _page_farm(self) -> QWidget:
        """
        Everything the farm macro is made of, in the order you set it up.

        Swinging, then when to stop and empty the bag, then what to drop, then
        the two points those drops are clicked on. They used to be three pages,
        which meant setting up one macro by walking a menu.
        """
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Farm",
            "The long-running macro: it swings for you, and every so often it "
            "opens the inventory and throws out what you told it to.",
            kicker="MACRO"))
        self._farm_clicking(lay)
        self._farm_drops(lay)
        lay.addWidget(self._auto_feed_card())
        self._farm_points(lay)
        lay.addStretch(1)
        self._sync_trigger_fields()
        return page

    def _farm_clicking(self, lay) -> None:
        card = Card("Swinging", "Speed is drawn at random between the two "
                                "bounds on every click, so the rhythm never "
                                "turns into a metronome.", icon="mouse")
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
                     "A short breather every N clicks. Zero turns it off.",
                     icon="clock")
        pgrid = FormGrid(pairs=2)
        self.sp_mp_every = spin(0, 5000, self.cfg.autoclick.micro_pause_every,
                                " clicks", 10)
        self.sp_mp_ms = spin(50, 5000, self.cfg.autoclick.micro_pause_ms, " ms", 50)
        pgrid.add("Pause every", self.sp_mp_every)
        pgrid.add("Pause length", self.sp_mp_ms)
        pause.add(pgrid)
        lay.addWidget(pause)

    def _farm_drops(self, lay) -> None:
        trigger = Card("When it empties the bag",
                       "How often the macro stops swinging to run a drop pass.",
                       icon="bolt")
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

        card = Card("What to drop",
                    "One checked row is one Drop All pass: a name for you, plus "
                    "the keyword typed into ARK's inventory filter.",
                    icon="list")
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
            "those pixels means nothing was typed, and the drop is skipped.",
            icon="shield")
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
                   "inventory to captures/ so you can check what would fall.",
                   icon="eye")
        self.sw_dry = SwitchRow("Run without dropping anything",
                                self.cfg.drop.dry_run)
        dry.add(self.sw_dry)
        lay.addWidget(dry)

        timing = Card("Inventory and timings",
                      "Raise the waits if your server is laggy — a filter that "
                      "has not refreshed yet is the usual cause of dropping the "
                      "wrong thing.", icon="clock")
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

    def _farm_points(self, lay) -> None:
        guide = Card(
            "The two points it clicks",
            "A drop pass clicks the search field and then Drop All. Where those "
            "sit depends on your resolution and on what the HUD is showing, so "
            "they are picked once on a frozen screen.",
            accent=True, icon="target")
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
                        "ultrawide. Always verify with Test afterwards.",
                        icon="sliders")
        btn_suggest = QPushButton("Estimate points for this resolution")
        btn_suggest.setCursor(Qt.PointingHandCursor)
        btn_suggest.clicked.connect(self._suggest_points)
        fallback.add(btn_suggest)
        lay.addWidget(fallback)

    def _auto_feed_card(self) -> Card:
        """Feeding belongs with the farm macro: it only runs while it does."""
        feed = Card(
            "Auto-feed", icon="shield", subtitle=
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
        return feed

    # ----------------------------------------------------------------- drop
    def _page_drop(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Drop",
            "Nothing to do with the farm loop. Point ARK's drop key at a block "
            "of slots and the cursor sweeps them, dropping every stack it "
            "passes — for emptying a forge or a bag by hand, fast.",
            kicker="MACRO"))
        lay.addWidget(self._hold_drop_card())
        lay.addWidget(self._hold_area_card())
        self._sync_hold_mode_note()
        lay.addStretch(1)
        return page

    # --------------------------------------------------------- overcap skin
    def _page_overcap(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Overcap skin",
            "Press your key and the macro holds Shift + a hotbar slot for you "
            "while the cursor runs your hotbar end to end and back, in a loop.",
            kicker="MACRO"))
        lay.addWidget(self._skin_overcap_card())
        lay.addWidget(self._skin_strip_card())
        lay.addStretch(1)
        return page

    # ------------------------------------------------------- skin overcap
    def _skin_overcap_card(self) -> Card:
        """The keys — yours to press, the chord for the macro to hold."""
        skin = self.cfg.skin_overcap
        card = Card("Keys and mode",
                    "Two keys, and they are not the same key: the one you press "
                    "belongs to the app, the chord belongs to the game and the "
                    "macro is what holds it.", icon="keyboard")
        self.sw_skin = SwitchRow("Skin overcap enabled", skin.enabled)
        card.add(self.sw_skin)
        card.add(Divider())

        sgrid = FormGrid(pairs=2)
        self.ed_skin_activate = QLineEdit(skin.activate_key)
        self.ed_skin_activate.setMaxLength(10)
        self.ed_skin_activate.setFixedWidth(124)
        self.ed_skin_activate.setAlignment(Qt.AlignCenter)
        sgrid.add("Start it with", self.ed_skin_activate,
                  "Yours, not the game's. Pick something ARK has nothing bound "
                  "to — it reaches the game as well")
        self.cb_skin_mode = combo(["Press to start and stop", "Hold the key"],
                                  1 if skin.mode == "hold" else 0, width=230)
        sgrid.add("How it runs", self.cb_skin_mode)
        self.cb_skin_key = combo(HOTBAR, HOTBAR.index(skin.key)
                                 if skin.key in HOTBAR else 1, width=124)
        sgrid.add("Macro holds Shift +", self.cb_skin_key,
                  "The hotbar slot the macro presses and holds while it sweeps")
        sgrid.skip()
        card.add(sgrid)
        self.skin_note = hint_label("")
        card.add(self.skin_note)
        card.add(hint_label(
            "The chord goes down when the sweep starts and comes back up when "
            "it ends, by every route out including losing focus and closing the "
            "app — a Shift left down would follow you into everything else you "
            "type."))
        return card

    def _skin_strip_card(self) -> Card:
        """The hotbar strip, and how fast the cursor runs it."""
        skin = self.cfg.skin_overcap
        card = Card("The strip it runs",
                    "Drag the box over your hotbar. It is one row, so only the "
                    "middle is swept — the height just has to cover the slots.",
                    icon="target")
        sgrid = FormGrid(pairs=2)
        self.sp_skin_stops = spin(2, 40, skin.stops, "", 1)
        sgrid.add("Stops across", self.sp_skin_stops,
                  "How many places the cursor pauses between the two ends. One "
                  "per hotbar slot is the usual answer")
        self.sp_skin_dwell = spin(5, 1000, skin.dwell_ms, " ms", 5)
        sgrid.add("Time per stop", self.sp_skin_dwell)
        card.add(sgrid)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_skin_area = QPushButton("  Freeze screen and select the strip")
        self.btn_skin_area.setObjectName("primary")
        self.btn_skin_area.setCursor(Qt.PointingHandCursor)
        self.btn_skin_area.setIcon(icons.icon("search", "#04222B", 16))
        self.btn_skin_area.setIconSize(QSize(16, 16))
        self.btn_skin_area.clicked.connect(self._begin_skin_pick)
        row.addWidget(self.btn_skin_area, 1)
        card.add(row)

        self.lbl_skin_area = hint_label("")
        card.add(self.lbl_skin_area)
        card.add(hint_label(
            "Same guards as the Drop macro — ARK in front, farm macro stopped — "
            "and the two never run at once, because there is one cursor."))
        return card

    # ------------------------------------------------------- hold to drop
    def _hold_drop_card(self) -> Card:
        """The keys and the mode — who presses what."""
        hold = self.cfg.hold_drop
        card = Card("Keys and mode",
                    "Two keys: the one you press to start, and the drop key "
                    "the game acts on. Which of you sends it depends on the "
                    "mode.", icon="keyboard")
        self.sw_hold = SwitchRow("Hold-to-drop enabled", hold.enabled)
        card.add(self.sw_hold)
        card.add(Divider())

        hgrid = FormGrid(pairs=2)
        self.cb_hold_mode = combo(["Press to start and stop",
                                   "Hold the activation key",
                                   "Hold the drop key yourself"],
                                  HOLD_MODES.index(hold.mode), width=230)
        self.cb_hold_mode.currentIndexChanged.connect(self._sync_hold_mode_note)
        hgrid.add("How it runs", self.cb_hold_mode)
        hgrid.skip()
        self.ed_hold_activate = QLineEdit(hold.activate_key)
        self.ed_hold_activate.setMaxLength(10)
        self.ed_hold_activate.setFixedWidth(124)
        self.ed_hold_activate.setAlignment(Qt.AlignCenter)
        hgrid.add("Start it with", self.ed_hold_activate,
                  "Yours, not the game's. Unused in the third mode, where your "
                  "finger on the drop key is the trigger")
        self.ed_hold_key = QLineEdit(hold.key)
        self.ed_hold_key.setMaxLength(10)
        self.ed_hold_key.setFixedWidth(124)
        self.ed_hold_key.setAlignment(Qt.AlignCenter)
        hgrid.add("Drop key", self.ed_hold_key,
                  "Whatever ARK has bound to dropping the item under the "
                  "cursor. Default: o")
        card.add(hgrid)
        self.hold_mode_note = hint_label("")
        card.add(self.hold_mode_note)
        card.add(hint_label(
            "Neither key is registered as a hotkey — a registered hotkey is "
            "swallowed before ARK sees it, and the drop key has to reach the "
            "game. So the activation press reaches it too: pick something ARK "
            "has nothing bound to."))
        return card

    def _hold_area_card(self) -> Card:
        """The block of slots, and how fast the cursor walks it."""
        hold = self.cfg.hold_drop
        card = Card("The block it sweeps",
                    "Drag a box over the slots you want emptied. The sweep path "
                    "is drawn inside it as you drag, so you can check the dots "
                    "land on the slot centres before committing.", icon="target")
        hgrid = FormGrid(pairs=2)
        self.sp_hold_cols = spin(1, 20, hold.columns, "", 1)
        hgrid.add("Columns", self.sp_hold_cols)
        self.sp_hold_rows = spin(1, 20, hold.rows, "", 1)
        hgrid.add("Rows", self.sp_hold_rows)
        self.sp_hold_dwell = spin(5, 1000, hold.dwell_ms, " ms", 5)
        hgrid.add("Time per slot", self.sp_hold_dwell,
                  "Too low and the game misses the hover — raise it on a "
                  "streamed session, which pays a round trip per slot")
        hgrid.skip()
        card.add(hgrid)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_hold_area = QPushButton("  Freeze screen and select the block")
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
            "It sweeps only while ARK is in front, stops the moment it is not, "
            "and refuses while the farm macro is running — an autoclick loose "
            "in an open inventory would move items around instead of dropping "
            "them."))
        return card

    def _sync_hold_mode_note(self) -> None:
        mode = HOLD_MODES[max(self.cb_hold_mode.currentIndex(), 0)]
        drop_key = (self.ed_hold_key.text().strip() or "o").upper()
        start = (self.ed_hold_activate.text().strip() or "f3").upper()
        if mode == "manual":
            self.hold_mode_note.setText(
                f"No activation key: you hold «{drop_key}» yourself and the "
                "sweep runs until you let go. The app sends no keys at all "
                "here — your finger is the instruction.")
        elif mode == "hold":
            self.hold_mode_note.setText(
                f"The sweep runs while you hold «{start}», and the macro taps "
                f"«{drop_key}» once per slot. Two different keys: the one you "
                "hold is the app's, the drop key is the game's.")
        else:
            self.hold_mode_note.setText(
                f"One press of «{start}» starts the sweep, another stops it, "
                f"and the macro taps «{drop_key}» once per slot. Hands free — "
                "this is the mode to use if you do not want to hold anything.")

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

    # ------------------------------------------------------------- settings
    def _page_settings(self) -> QWidget:
        page, lay = scroll_page()
        lay.addLayout(heading(
            "Settings",
            "The keys the app answers to, how its input reaches the game, and "
            "how it keeps itself up to date.", kicker="SYSTEM"))

        keys = Card("Global hotkeys",
                    "The app's own keys. They fire even while ARK has focus, "
                    "and the game never sees them.", icon="keyboard")
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

        target = Card("Target and delivery",
                      "Which window the macro aims at, and how its clicks and "
                      "keys get there.", icon="cursor")
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


        afk = Card("Anti-AFK", icon="clock", subtitle=
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
                    "screenshots are never touched.", icon="refresh")

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
        lay.addLayout(heading(
            "Log", "Everything the app did this session, newest at the bottom.",
            kicker="SYSTEM"))
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
        """Keep the dashboard key list showing the keys actually bound."""
        keys = self.cfg.hotkeys
        hold, skin = self.cfg.hold_drop, self.cfg.skin_overcap
        bound = {
            "toggle": keys.toggle,
            "drop_now": keys.drop_now,
            "panic": keys.panic,
            "pick_points": keys.pick_points,
            # the sweep key depends on the mode: in manual it is the drop key
            # itself that starts it, not the activation key
            "hold": hold.key if hold.mode == "manual" else hold.activate_key,
            "skin": skin.activate_key,
        }
        for name, row in getattr(self, "key_rows", {}).items():
            row.cap.set_key(bound.get(name, ""))
        # a macro that is switched off gets a dimmed row rather than a missing
        # one: the key still exists, it just will not do anything yet
        for name, feature in (("hold", hold), ("skin", skin)):
            row = getattr(self, "key_rows", {}).get(name)
            if row is not None:
                row.setEnabled(feature.enabled)
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
            self.ed_hold_activate,
            self.sw_skin.switch, self.cb_skin_key, self.sp_skin_stops,
            self.sp_skin_dwell, self.ed_skin_activate, self.cb_skin_mode,
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
        hold.activate_key = self.ed_hold_activate.text().strip().lower() or "f3"
        hold.mode = HOLD_MODES[max(self.cb_hold_mode.currentIndex(), 0)]
        hold.columns = self.sp_hold_cols.value()
        hold.rows = self.sp_hold_rows.value()
        hold.dwell_ms = self.sp_hold_dwell.value()

        skin = self.cfg.skin_overcap
        skin.enabled = self.sw_skin.switch.isChecked()
        skin.activate_key = self.ed_skin_activate.text().strip().lower() or "f4"
        skin.mode = "hold" if self.cb_skin_mode.currentIndex() == 1 else "toggle"
        skin.key = self.cb_skin_key.currentText()
        skin.stops = self.sp_skin_stops.value()
        skin.dwell_ms = self.sp_skin_dwell.value()
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
            self._go(PAGE_FARM)
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

    # ---------------------------------------------------------- hold to drop
    def _sync_hold_drop(self) -> None:
        hold = self.cfg.hold_drop
        skin = self.cfg.skin_overcap
        drop_ready = hold.enabled and sweep.usable(hold.area)
        skin_ready = skin.enabled and sweep.usable(skin.area)
        if drop_ready or skin_ready:
            vk = w.vk_from_name(hold.key)
            # a key that is already down as this arms is not a fresh press, or
            # switching the mode on with a finger on the key would start a sweep
            self._hold_was_down = bool(vk is not None and w.key_is_down(vk))
            self._hold_watch.start()
        else:
            self._hold_watch.stop()
            self._stop_sweep()
        if not drop_ready and self._sweep_kind == "drop":
            self._stop_sweep()
        if not skin_ready and self._sweep_kind == "skin":
            self._stop_sweep()
        self._refresh_hold_status()
        self._refresh_skin_status()

    def _watch_keys(self) -> None:
        """One poll for both key-driven sweeps. They share the cursor."""
        self._watch_hold_key()
        self._watch_skin_key()

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
        driven = {
            "toggle": f"«{hold.activate_key.upper()}» starts and stops it",
            "hold": f"it loops while «{hold.activate_key.upper()}» is held",
            "manual": f"it loops while «{hold.key.upper()}» is held",
        }[hold.mode]
        self.lbl_hold_area.setText(
            f"{width}x{height} px at ({x}, {y}){where} — {hold.columns}x"
            f"{hold.rows} = {slots} slots, about {pace:.1f}s per lap, and "
            f"{driven}.")

    def _refresh_skin_status(self) -> None:
        skin = self.cfg.skin_overcap
        problem = self._skin_problem()
        if problem:
            self.skin_note.setText(
                f"{problem[0].upper()}{problem[1:]}. Skin overcap will refuse "
                "to run.")
        else:
            starts = ("Hold" if skin.mode == "hold" else "Press")
            self.skin_note.setText(
                f"{starts} «{skin.activate_key.upper()}» and the macro holds "
                f"Shift+«{skin.key.upper()}» while it sweeps. Two different "
                "keys on purpose: the one you press is the app's, the chord is "
                "the game's.")
        if not sweep.usable(skin.area):
            self.lbl_skin_area.setText(
                "No strip selected yet — skin overcap will not do anything "
                "until you pick one on a frozen screen.")
            return
        x, y, width, height = skin.area
        path = len(sweep.pingpong(skin.area, skin.stops))
        pace = path * skin.dwell_ms / 1000.0
        res = skin.area_resolution
        where = f", captured at {res[0]}x{res[1]}" if res and all(res) else ""
        self.lbl_skin_area.setText(
            f"{width}x{height} px at ({x}, {y}){where} — {skin.stops} stops "
            f"each way, {path} a full lap, about {pace:.1f}s.")

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

    def _hold_problem(self) -> str:
        """Why hold-to-drop cannot run, or "" when it can."""
        hold = self.cfg.hold_drop
        if w.vk_from_name(hold.key) is None:
            return f'the drop key "{hold.key}" is not a key name'
        if hold.mode == "manual":
            return ""
        if w.vk_from_name(hold.activate_key) is None:
            return f'the activation key "{hold.activate_key}" is not a key name'
        if hold.activate_key == hold.key:
            return ("the activation key is the drop key — pick a different one, "
                    "or switch to holding the drop key yourself")
        return ""

    def _watch_hold_key(self) -> None:
        """
        Drive the sweep from whichever key the mode says is in charge.

        Manual watches the drop key itself, the way a finger on it would. The
        other two watch the activation key, which belongs to the app: holding
        reads its level, pressing reads its edge, so the press is acted on once
        and the release means nothing.
        """
        hold = self.cfg.hold_drop
        if not (hold.enabled and sweep.usable(hold.area)):
            return
        if self._sweep_kind == "skin":
            return
        problem = self._hold_problem()
        if problem:
            self._log(f"hold-to-drop off: {problem}", "err")
            # switch the feature off rather than stop the timer: the watcher is
            # shared, and skin overcap may still be using it
            self.sw_hold.switch.setChecked(False)
            return
        vk = w.vk_from_name(hold.key if hold.mode == "manual"
                            else hold.activate_key)
        down = w.key_is_down(vk)
        pressed = down and not self._hold_was_down
        self._hold_was_down = down

        if hold.mode == "toggle":
            if not pressed:
                return
            if self._sweep_timer.isActive():
                self._stop_sweep()
            elif self._can_sweep():
                self._start_drop_sweep()
            return

        if not down:
            self._stop_sweep()
            self._hold_refused = False
            return
        if self._sweep_timer.isActive():
            return
        if self._can_sweep():
            self._start_drop_sweep()

    def _skin_problem(self) -> str:
        """Why skin overcap cannot run, or "" when it can."""
        skin = self.cfg.skin_overcap
        if w.vk_from_name(skin.activate_key) is None:
            return f'the activation key "{skin.activate_key}" is not a key name'
        if w.vk_from_name(skin.key) is None:
            return f'the hotbar slot "{skin.key}" is not a key name'
        # the whole point of two keys: pressing the chord to start a macro whose
        # job is to hold that chord is a circle
        if skin.activate_key in (skin.key, "shift"):
            return ("the activation key is part of the chord the macro holds — "
                    "pick a different one")
        return ""

    def _watch_skin_key(self) -> None:
        """
        Drive the strip sweep from the activation key.

        That key is the app's, not the game's: it starts and stops the macro,
        and the macro is what holds Shift + the hotbar slot afterwards.
        """
        skin = self.cfg.skin_overcap
        if not (skin.enabled and sweep.usable(skin.area)):
            return
        if self._sweep_kind == "drop":
            return
        problem = self._skin_problem()
        if problem:
            self._log(f"skin overcap off: {problem}", "err")
            self.sw_skin.switch.setChecked(False)
            return
        vk = w.vk_from_name(skin.activate_key)
        down = w.key_is_down(vk)
        pressed = down and not self._skin_was_down
        self._skin_was_down = down

        if skin.mode == "toggle":
            if not pressed:
                return
            if self._sweep_timer.isActive():
                self._stop_sweep()
            elif self._can_sweep():
                self._start_skin_sweep()
            return

        if not down:
            self._stop_sweep()
            return
        if self._sweep_timer.isActive():
            return
        if self._can_sweep():
            self._start_skin_sweep()

    def _start_drop_sweep(self) -> None:
        hold = self.cfg.hold_drop
        path = sweep.serpentine(hold.area, hold.columns, hold.rows)
        if not path:
            return
        self._sweep_kind = "drop"
        how = {"toggle": "press again to stop",
               "hold": f"while {hold.activate_key.upper()} is held",
               "manual": f"while {hold.key.upper()} is held"}[hold.mode]
        self._begin_sweep(path, hold.dwell_ms,
                          f"hold-to-drop: sweeping {len(path)} slots, {how}")

    def _start_skin_sweep(self) -> None:
        skin = self.cfg.skin_overcap
        path = sweep.pingpong(skin.area, skin.stops)
        if not path:
            return
        self._sweep_kind = "skin"
        self._hold_chord(True)
        stop = ("release the key" if skin.mode == "hold" else "press again")
        self._begin_sweep(
            path, skin.dwell_ms,
            f"skin overcap: holding Shift+{skin.key.upper()} and running "
            f"{len(path)} stops a lap — {stop} to stop")

    def _hold_chord(self, down: bool) -> None:
        """
        Press or release Shift + the hotbar slot the macro holds for you.

        Releasing has to be unconditional and safe to repeat: a Shift left down
        because a sweep ended some way nobody planned for would follow you out of
        the game and into everything else you type.
        """
        shift = w.vk_from_name("shift")
        vk = w.vk_from_name(self.cfg.skin_overcap.key)
        if shift is None or vk is None:
            return
        if down:
            w.key_down(shift)
            w.key_down(vk)
            self._chord_held = True
            return
        if self._chord_held:
            w.key_up(vk)
            w.key_up(shift)
            self._chord_held = False

    def _begin_sweep(self, path: list[tuple[int, int]], dwell: int,
                     message: str) -> None:
        self._sweep_path = path
        self._sweep_return = w.get_cursor_pos()
        # remembered rather than looked up every tick: find_window walks every
        # window on the desktop, and this runs 25 times a second
        self._sweep_hwnd = w.find_window(self.cfg.target.window_title)
        # step onto the first stop here, so it gets a full dwell before the tick
        # that presses the key on it
        w.move_cursor(*path[0])
        self._sweep_index = 1
        self._sweep_timer.start(max(int(dwell), 5))
        self._log(message, "info")

    def _sweep_step(self) -> None:
        """
        One stop per tick, looping, until it is told to stop.

        The drop key is sent here in every mode but manual. Manual is the one
        where a finger is already on it, and a press on top of that would be a
        second drop.
        """
        if not self._sweep_path:
            self._stop_sweep()
            return
        if self._sweep_kind == "skin":
            return self._skin_step()

        hold = self.cfg.hold_drop
        vk = w.vk_from_name(hold.key)
        if vk is None:
            self._stop_sweep()
            return
        # re-checked here and not only on the watch timer: this runs far more
        # often, so the sweep stops within one slot of the key being released
        if hold.mode in ("hold", "manual"):
            watched = w.vk_from_name(hold.key if hold.mode == "manual"
                                     else hold.activate_key)
            if watched is None or not w.key_is_down(watched):
                self._stop_sweep()
                return
        # in every mode, a game that is no longer in front means the cursor and
        # the presses are landing in somebody else's window
        if not w.is_foreground(self._sweep_hwnd):
            self._stop_sweep()
            return
        if hold.mode != "manual":
            # The cursor has been resting on this slot for a full dwell. The
            # press is held for a third of that and never more than 25 ms: this
            # runs on the UI thread, so a hold as long as the tick would stall
            # the window and let the timers pile up behind each other — which is
            # exactly what happens when someone lowers the dwell chasing speed.
            w.tap(vk, hold=min(0.025, hold.dwell_ms / 3000.0))
        self._advance()

    def _skin_step(self) -> None:
        """
        One stop per tick along the strip, back and forth.

        The chord is already down — the macro pressed it when the sweep started
        and holds it until the sweep ends, which is what a finger on Shift and
        the slot would do.
        """
        skin = self.cfg.skin_overcap
        if skin.mode == "hold":
            vk = w.vk_from_name(skin.activate_key)
            if vk is None or not w.key_is_down(vk):
                self._stop_sweep()
                return
        if not w.is_foreground(self._sweep_hwnd):
            self._stop_sweep()
            return
        self._advance()

    def _advance(self) -> None:
        x, y = self._sweep_path[self._sweep_index % len(self._sweep_path)]
        w.move_cursor(x, y)
        self._sweep_index += 1

    def _stop_sweep(self) -> None:
        # released first and unconditionally: every path out of a sweep comes
        # through here, and a Shift left down would follow the user everywhere
        self._hold_chord(False)
        if not self._sweep_timer.isActive():
            self._sweep_kind = ""
            return
        self._sweep_timer.stop()
        laps = self._sweep_index / max(len(self._sweep_path), 1)
        name = "skin overcap" if self._sweep_kind == "skin" else "hold-to-drop"
        self._sweep_kind = ""
        # put the pointer back where it was, so releasing the key does not leave
        # the cursor parked on some slot in the middle of the panel
        if self._sweep_return:
            w.move_cursor(*self._sweep_return)
            self._sweep_return = None
        self._log(f"{name}: stopped after {self._sweep_index} stops "
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
        Convert the picked areas if the screen changed since they were picked.

        These are in screen pixels, not game pixels: they are dragged over a
        screenshot of the whole desktop, so the screen is what they scale with.
        """
        width, height = w.screen_size()
        for target, name in ((self.cfg.hold_drop, "hold-to-drop area"),
                             (self.cfg.skin_overcap, "skin overcap strip")):
            old = target.area_resolution
            if not (old and all(old)) or not sweep.usable(target.area):
                continue
            if [width, height] == list(old):
                continue
            target.area = sweep.rescale(target.area, old, [width, height])
            target.area_resolution = [width, height]
            self._log(f"screen changed from {old[0]}x{old[1]} to "
                      f"{width}x{height} — {name} rescaled, check it before "
                      "using it", "warn")
        self._refresh_hold_status()
        self._refresh_skin_status()

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

    def _begin_skin_pick(self) -> None:
        self._begin_area_pick(kind="skin")

    def _begin_area_pick(self, _checked: bool = False,
                         kind: str = "drop") -> None:
        if self._picking:
            return
        self._pick_area_kind = kind
        if self.engine is not None and self.engine.isRunning():
            self._stop_macro()
            self._log("macro stopped so it does not click into the picker",
                      "warn")
        self._stop_sweep()
        self._picking = True
        self._log("freezing the screen — bring up what you want to select over",
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
        if self._pick_area_kind == "skin":
            stops = self.sp_skin_stops.value()
            picker = AreaPicker(shot, geo, stops, 1, self._shot_origin,
                                label=f"SKIN OVERCAP STRIP · {stops} STOPS",
                                title="Drag a box over your hotbar",
                                strip=True)
        else:
            picker = AreaPicker(shot, geo, self.sp_hold_cols.value(),
                                self.sp_hold_rows.value(), self._shot_origin)
        picker.picked.connect(self._on_area_picked)
        picker.cancelled.connect(self._cancel_pick)
        self._drop_picker()
        self._picker = picker
        picker.show()

    def _on_area_picked(self, x: int, y: int, width: int, height: int) -> None:
        target = (self.cfg.skin_overcap if self._pick_area_kind == "skin"
                  else self.cfg.hold_drop)
        target.area = [x, y, width, height]
        target.area_resolution = list(w.screen_size())
        self._drop_picker()
        self._picking = False
        self._restore_window()
        name = ("skin overcap strip" if self._pick_area_kind == "skin"
                else "hold-to-drop area")
        self._log(f"{name} set: {width}x{height} px at ({x}, {y})", "ok")
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
        self._go(PAGE_FARM)

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
        # also releases the chord if a sweep was holding it
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
