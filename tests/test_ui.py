"""
Front-end tests: drive the real widgets and check the config that comes out.

Runs offscreen, sends no input to the game:
    python tests/test_ui.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arkmacro import config as config_module  # noqa: E402
from arkmacro import stopsign  # noqa: E402
from arkmacro import updater  # noqa: E402
from arkmacro.config import Config  # noqa: E402
from arkmacro.ui import icons  # noqa: E402
from arkmacro.ui.backdrop import Backdrop, load_brand  # noqa: E402
from arkmacro.ui.main_window import (APP_NAME, NAV, PAGE_DASHBOARD,  # noqa: E402
                                     PAGE_DROP, PAGE_FARM, PAGE_LOG,
                                     PAGE_OVERCAP, PAGE_SETTINGS,
                                     MainWindow, round_trip)
from arkmacro.engine import MacroEngine  # noqa: E402
from arkmacro.ui.picker import ScreenPicker  # noqa: E402
from arkmacro.ui.theme import QSS  # noqa: E402
from arkmacro.ui.widgets import FormGrid, PresetDialog, TemplateEditor  # noqa: E402

# keep the real config.json out of the way, and never let the tests hit the
# network through the startup update check
sandbox = pathlib.Path(tempfile.mkdtemp()) / "config.json"
sandbox.write_text('{"app": {"check_updates_on_start": false}}',
                   encoding="utf-8")
config_module.CONFIG_PATH = sandbox

app = QApplication(sys.argv[:1])
app.setStyleSheet(QSS)

win = MainWindow()
win.resize(1060, 760)
win.show()
app.processEvents()

# ------------------------------------------------- 1) every page builds
for index, (_glyph, name, _section) in enumerate(NAV):
    win.stack.setCurrentIndex(index)
    app.processEvents()
    page = win.stack.widget(index)
    assert page.widget().sizeHint().width() <= 1060, \
        f"page {name} is wider than the window and would clip"
print(f"OK  {len(NAV)} pages build and fit")

# ------------------------------------------- 1b) the nav is grouped by job
# One page per thing you can run, not one page per settings panel: setting up
# the farm macro used to mean walking three tabs.
assert [name for _g, name, _s in NAV] == [
    "Dashboard", "Farm", "Drop", "Overcap skin", "Settings", "Log"], NAV
sections = [section for _g, _n, section in NAV if section]
assert sections == ["CONTROL", "MACROS", "SYSTEM"], sections
# every macro page owns its own controls, and Farm owns the ones that used to
# be scattered across Autoclick, Templates and Points
for widget, page in ((win.sp_cps_min, PAGE_FARM), (win.tpl_editor, PAGE_FARM),
                     (win.sp_fx, PAGE_FARM), (win.sw_feed.switch, PAGE_FARM),
                     (win.sw_hold.switch, PAGE_DROP),
                     (win.sw_skin.switch, PAGE_OVERCAP),
                     (win.sw_afk.switch, PAGE_SETTINGS)):
    holder = win.stack.widget(page)
    assert holder.isAncestorOf(widget), \
        f"{widget.objectName() or widget} is not on the page it belongs to"
print("OK  the nav groups pages by what they run, and each owns its controls")

# ------------------------------------------- 1c) the dashboard key list
# "What does F3 do" has to be answerable without opening a page.
win.stack.setCurrentIndex(PAGE_DASHBOARD)
win.cfg.hold_drop.mode = "toggle"
win.cfg.hold_drop.activate_key = "f3"
win.cfg.skin_overcap.activate_key = "f4"
win._refresh_key_list()
caps = {name: row.cap.text() for name, row in win.key_rows.items()}
assert caps == {"toggle": "F6", "drop_now": "F7", "panic": "F8",
                "pick_points": "F9", "hold": "F3", "skin": "F4"}, caps

# in manual mode the drop key itself is what starts the sweep, so that is the
# key the dashboard has to show
win.cfg.hold_drop.mode = "manual"
win.cfg.hold_drop.key = "o"
win._refresh_key_list()
assert win.key_rows["hold"].cap.text() == "O", win.key_rows["hold"].cap.text()
win.cfg.hold_drop.mode = "toggle"
win._refresh_key_list()
print("OK  the dashboard names every key, including the two macro ones")

# ------------------------------------------------- 2) template editor
editor: TemplateEditor = win.tpl_editor
before = len(editor.templates())
editor.name_edit.setText("Obsidian")
editor.keyword_edit.setText("obsidian")
editor._add()
assert len(editor.templates()) == before + 1
assert editor.templates()[-1] == {"name": "Obsidian", "keyword": "obsidian",
                                  "enabled": True}

# duplicates are refused
editor.name_edit.setText("Dupe")
editor.keyword_edit.setText("OBSIDIAN")
editor._add()
assert len(editor.templates()) == before + 1, "duplicate keyword got in"

# and Save cannot sneak one past either: the same filter twice in the cycle
# means a second pass typing into an inventory the first one already emptied
editor.list.setCurrentRow(0)
was = editor.templates()[0]["keyword"]
editor.name_edit.setText("Sneaky")
editor.keyword_edit.setText("obsidian")
editor._update()
assert editor.templates()[0]["keyword"] == was, "Save created a duplicate"
assert len({t["keyword"] for t in editor.templates()}) == len(editor.templates())
# renaming a row to the keyword it already has is not a clash with itself
editor.keyword_edit.setText(was)
editor.name_edit.setText("Renamed in place")
editor._update()
assert editor.templates()[0]["name"] == "Renamed in place", "a row blocked itself"

# a refused edit is silent in the list, so it has to reach the log
refusals: list[str] = []
editor.rejected.connect(refusals.append)
editor.keyword_edit.setText("OBSIDIAN")
editor._add()
assert refusals and "already a template" in refusals[-1], refusals

# a one-letter keyword goes in. It matches most of a bag, which is either a typo
# or an inverse filter — "o" drops everything except Metal and Element Shard —
# and that call belongs to whoever typed it. So: accepted, and said out loud.
warnings: list[str] = []
editor.warned.connect(warnings.append)
count = len(editor.templates())
editor.name_edit.setText("Not metal")
editor.keyword_edit.setText("o")
editor._add()
assert len(editor.templates()) == count + 1, '"o" was refused as a keyword'
assert editor.templates()[-1]["keyword"] == "o"
assert warnings and "most of the bag" in warnings[-1], warnings
# the row wears the warning too, so it is not a surprise later
broad_row = editor.list.item(editor.list.count() - 1)
assert "matches most of a bag" in broad_row.text(), broad_row.text()
assert not broad_row.toolTip().startswith("types "), "no explanation on the row"
# Save accepts one as well
editor.list.setCurrentRow(0)
editor.name_edit.setText("Two letters")
editor.keyword_edit.setText("st")
editor._update()
assert editor.templates()[0]["keyword"] == "st", "Save refused a short keyword"
editor.name_edit.setText("Thatch")
editor.keyword_edit.setText("thatch")
editor._update()
editor.list.setCurrentRow(editor.list.count() - 1)
editor._remove()

# rename the selected row, keeping its checked state
win.stack.setCurrentIndex(PAGE_FARM)
editor.list.setCurrentRow(0)
first_state = editor.templates()[0]["enabled"]
editor.name_edit.setText("Renamed")
editor.keyword_edit.setText("thatch")
editor._update()
assert editor.templates()[0]["name"] == "Renamed"
assert editor.templates()[0]["enabled"] is first_state

# reorder and remove
editor.list.setCurrentRow(0)
editor._move(1)
assert editor.templates()[1]["name"] == "Renamed"
editor.list.setCurrentRow(1)
editor._remove()
assert all(t["name"] != "Renamed" for t in editor.templates())
print("OK  template add / dedupe / rename / reorder / remove")

# unchecking a row reaches the config
item = editor.list.item(0)
item.setCheckState(Qt.Unchecked)
app.processEvents()
win._pull()
assert win.cfg.drop.templates[0]["enabled"] is False
assert all(t["enabled"] for t in win.cfg.drop.active_templates())
print("OK  checkbox state flows into the config")

# ------------------------------------------------- 3) preset dialog
dialog = PresetDialog(set())
checkable = [i for i in range(dialog.list.count())
             if dialog.list.item(i).flags() & Qt.ItemIsUserCheckable]
dialog.list.item(checkable[0]).setCheckState(Qt.Checked)
picked = dialog.chosen()
assert len(picked) == 1 and picked[0]["keyword"]
# a header row must never be selectable
headers = [i for i in range(dialog.list.count())
           if not (dialog.list.item(i).flags() & Qt.ItemIsUserCheckable)]
assert headers, "preset categories are missing"
dialog.deleteLater()

# already-owned keywords come back disabled
owned = PresetDialog({"thatch"})
row = next(i for i in range(owned.list.count())
           if '"thatch"' in owned.list.item(i).text())
assert owned.list.item(row).flags() == Qt.NoItemFlags
owned.deleteLater()
print("OK  preset dialog selection and duplicate guard")

# ------------------------------------------------- 4) trigger visibility
win.cb_trigger.setCurrentIndex(0)
app.processEvents()
assert win.sp_interval.isVisible() and win.lbl_interval.isVisible()
assert not win.sp_every_clicks.isVisible() and not win.lbl_clicks.isVisible()
assert not win.sp_min_farm.isVisible(), "the farm stretch belongs to clicks"
win.cb_trigger.setCurrentIndex(1)
app.processEvents()
assert win.sp_every_clicks.isVisible() and win.lbl_clicks.isVisible()
assert win.sp_min_farm.isVisible() and win.lbl_min_farm.isVisible()
assert not win.sp_interval.isVisible() and not win.lbl_interval.isVisible()
win.cb_trigger.setCurrentIndex(2)
app.processEvents()
assert not win.sp_interval.isVisible() and not win.sp_every_clicks.isVisible()
assert not win.sp_min_farm.isVisible() and not win.hint_min_farm.isVisible()
print("OK  trigger fields show and hide with the label")

# ------------------------------------------------- 5) config round trip
win.sw_dry.switch.setChecked(True)
win.sw_verify.switch.setChecked(False)
win.cb_mode.setCurrentIndex(1)
win.sp_cps_min.setValue(11.5)
win.ed_inv_key.setText("TAB")
win.sp_close_presses.setValue(3)
win.sp_min_farm.setValue(35)
win.hk_toggle.setText("Ctrl+F5")
win.sp_fx.setValue(277)
win.sp_fy.setValue(193)
win.sw_feed.switch.setChecked(True)
win.sp_feed_interval.setValue(420)
win.cb_food.setCurrentText("3")
win.cb_water.setCurrentText("6")
win._pull()
win._save()

reloaded = Config.load(sandbox)
assert reloaded.drop.dry_run is True
assert reloaded.drop.verify_filter is False, "the filter check did not persist"
assert reloaded.target.mode == "background"
assert reloaded.autoclick.cps_min == 11.5
assert reloaded.drop.inventory_key == "tab", reloaded.drop.inventory_key
assert reloaded.drop.close_presses == 3, reloaded.drop.close_presses
assert reloaded.drop.min_farm_s == 35, reloaded.drop.min_farm_s
assert reloaded.hotkeys.toggle == "Ctrl+F5"
assert reloaded.drop.filter_point == [277, 193]
assert reloaded.drop.templates == win.cfg.drop.templates
assert reloaded.auto_feed.enabled is True
assert reloaded.auto_feed.interval_s == 420, reloaded.auto_feed.interval_s
assert (reloaded.auto_feed.food_key,
        reloaded.auto_feed.water_key) == ("3", "6")
print("OK  every control round-trips through config.json")

# ------------------------------------------- 5b) the auto-feed slots warn early
# The engine refuses these when it arms; the card has to say so while they are
# still being picked, not from a red line mid-session.
win.cb_food.setCurrentText("5")
win.cb_water.setCurrentText("5")
win._pull()
assert "would eat again" in win.feed_note.text(), win.feed_note.text()

# the inventory key is "tab" from the round trip above, so put a slot on it
win.ed_inv_key.setText("5")
win.cb_water.setCurrentText("6")
win._pull()
assert "inventory key" in win.feed_note.text(), win.feed_note.text()

win.ed_inv_key.setText("i")
win.cb_food.setCurrentText("4")
win.cb_water.setCurrentText("5")
win._pull()
assert "slot 4" in win.feed_note.text() and "slot 5" in win.feed_note.text()
win.sw_feed.switch.setChecked(False)
win._pull()
print("OK  auto-feed flags a slot clash before the macro is ever armed")

# ------------------------------------------------- 6) start guard
win.sw_drop.switch.setChecked(True)
win.sw_dry.switch.setChecked(False)
win.sp_fx.setValue(0)
win.sp_fy.setValue(0)
win.sp_dx.setValue(0)
win.sp_dy.setValue(0)
win._start_macro()
assert win.engine is None, "macro started without the points being set"
assert win.stack.currentIndex() == PAGE_FARM, \
    "user was not sent to the page holding the points"
print("OK  refuses to arm without points and jumps to the right tab")

# ------------------------------------------------- 7) point estimate + thumbs
# pin the target area: the ambient desktop must not decide what this asserts
win._game_area = lambda: (0, 0, 1920, 1080)
win._suggest_points()
assert [win.sp_fx.value(), win.sp_fy.value()] == [277, 193]
assert [win.sp_dx.value(), win.sp_dy.value()] == [457, 193]
assert win.cfg.drop.points_resolution == [1920, 1080]

# the shape that started this: a tall, narrow Explorer window matching "ark"
# put the estimate at x = -175, which the spin box would silently clamp to 0
win.sp_fx.setValue(11)
win.sp_dx.setValue(11)
win._game_area = lambda: (8, 0, 891, 994)
win._suggest_points()
assert win.sp_fx.value() == 11, "an off-window estimate was applied anyway"
del win._game_area          # back to the real method for later sections
print("OK  estimate fills the fields, and refuses when it lands off-window")

# points on a monitor left of the primary one are representable
win.sp_fx.setValue(-1200)
assert win.sp_fx.value() == -1200, "negative coordinates got clamped"

shot = QPixmap(400, 300)
shot.fill(QColor("#204050"))
win._shot = shot
win._shot_origin = (0, 0)
win._store_thumb("filter", 200, 150)
assert win._thumb_filter.has_preview
# a point near the edge must not blow up
win._store_thumb("dropall", 3, 2)
print("OK  thumbnails crop safely near an edge")

# ------------------------------------------------- 8) picker geometry
picker = ScreenPicker(shot, QRect(0, 0, 800, 600), "title", "subtitle", "step")
assert picker._to_shot(QPoint(400, 300)) == QPoint(200, 150)
assert picker._to_shot(QPoint(0, 0)) == QPoint(0, 0)
picker.deleteLater()
print("OK  picker maps widget pixels back to screenshot pixels")

# ------------------------------------------------- 9) form grid pairing
grid = FormGrid(pairs=2)
from PySide6.QtWidgets import QLabel  # noqa: E402

first = grid.add("a", QLabel("1"))
grid.skip()
second = grid.add("b", QLabel("2"))
third = grid.add("c", QLabel("3"))
assert grid.grid.getItemPosition(grid.grid.indexOf(first))[0] == 0
assert grid.grid.getItemPosition(grid.grid.indexOf(second))[0] == 1
assert grid.grid.getItemPosition(grid.grid.indexOf(third))[0] == 1
print("OK  form grid keeps skipped slots aligned")

# ------------------------------------------------- 10) icons render
for name in icons.DRAW:
    art = icons.pixmap(name, "#40DCF0", 18)
    assert not art.isNull(), f"icon {name} rendered empty"
    image = art.toImage()
    painted = any(image.pixelColor(x, y).alpha() > 0
                  for x in range(0, image.width(), 3)
                  for y in range(0, image.height(), 3))
    assert painted, f"icon {name} drew nothing"
# cached lookups return the very same pixmap object
assert icons.pixmap("grid", "#40DCF0", 18) is icons.pixmap("grid", "#40DCF0", 18)
print(f"OK  {len(icons.DRAW)} vector icons render")

# ------------------------------------------------- 11) branded backdrop
assert load_brand() is not None, "assets/brand.png is missing"
canvas = Backdrop()
canvas.resize(900, 600)
frame = canvas.grab().toImage()
# the brand lives on the right; the left edge must stay clean canvas
left = frame.pixelColor(40, 300)
right = frame.pixelColor(820, 90)
assert left.alpha() == 255 and right.alpha() == 255
assert right.lightness() != left.lightness(), "brand backdrop did not paint"
# and it must never be so bright that text stops reading over it
assert right.lightness() < 130, f"backdrop too bright: {right.lightness()}"
canvas.deleteLater()
print("OK  backdrop paints the brand without blowing out the canvas")

# ------------------------------------------------- 12) branding
assert APP_NAME == "A.N.S Tools"
assert win.windowTitle() == APP_NAME
print("OK  window carries the A.N.S Tools name")

# ------------------------------------------------- 13) update card states
# unattended updating is on by default and would run a real `git pull` on the
# checkout these tests are running from. 13b turns it back on with the pull
# stubbed; here it stays off.
win.sw_auto_update.switch.setChecked(False)
win._pull()
win.stack.setCurrentIndex(PAGE_SETTINGS)
app.processEvents()
assert not win.btn_apply.isVisible(), "update button shows before any check"
assert not win.titlebar.update_pill.isVisible()

win._on_update_checked(updater.Status(ok=True, behind=0))
assert not win.btn_apply.isVisible() and not win.titlebar.update_pill.isVisible()
assert "latest" in win.lbl_update.text()

win._on_update_checked(updater.Status(
    ok=True, behind=2, commits=[("abc1234", "fix drop timing"),
                                ("def5678", "new preset")],
    requirements_changed=True))
assert win.btn_apply.isVisible() and win.btn_apply.isEnabled()
assert win.titlebar.update_pill.isVisible()
assert "2 new commits" in win.lbl_update.text()
assert "requirements.txt" in win.lbl_update.text()
assert "fix drop timing" in win.lbl_commits.text()

# a dirty working copy offers the button but keeps it locked
win._on_update_checked(updater.Status(ok=True, behind=1, dirty=True,
                                      commits=[("abc1234", "wip")]))
assert win.btn_apply.isVisible() and not win.btn_apply.isEnabled()
assert "uncommitted" in win.lbl_update.text()

win._on_update_checked(updater.Status(ok=False, error="could not reach origin"))
assert not win.btn_apply.isVisible()
assert "could not reach origin" in win.lbl_update.text()
print("OK  update card reflects every check outcome")

# ------------------------------------------- 13b) unattended updating
# The pull itself is stubbed: this is about *when* the app decides to pull, and
# a real `git pull` in a test would rewrite the checkout it is running from.
applies: list[int] = []
win._apply_update = lambda: applies.append(1)
new_commit = updater.Status(ok=True, behind=1, commits=[("abc1234", "fix")])


class Farming:
    """Stands in for a running engine."""

    @staticmethod
    def isRunning():
        return True


# switched off: a new commit waits for the button
win.sw_auto_update.switch.setChecked(False)
win._pull()
win._on_update_checked(new_commit)
assert not applies, "pulled without being asked while the switch was off"

# and it ships on, so a fresh config updates itself with nothing to click
assert Config().app.auto_update is True, "unattended updating no longer default"

# on, and nothing farming: it goes straight through
win.sw_auto_update.switch.setChecked(True)
win._pull()
win.engine = None
win._on_update_checked(new_commit)
assert applies == [1], f"unattended update did not fire: {applies}"

# on, but the macro is farming: held, not applied — a restart mid-pass would
# leave the inventory open and the session farming nothing
applies.clear()
win.engine = Farming()
win._on_update_checked(new_commit)
assert not applies, "restarted the app in the middle of a farm"
assert win._update_pending, "the update was dropped instead of held"

# the point picker is just as fatal to restart under
win.engine = None
win._picking = True
win._on_update_checked(new_commit)
assert not applies, "restarted the app under the frozen picker"
win._picking = False

# and it lands as soon as the macro stops
win.engine = None
win._on_finished()
for _ in range(40):                     # the pending apply is on a short timer
    app.processEvents()
    if applies:
        break
    time.sleep(0.02)
assert applies == [1], f"the held update never landed: {applies}"

# a dirty checkout is skipped entirely — apply() would refuse anyway
applies.clear()
win._on_update_checked(updater.Status(ok=True, behind=1, dirty=True,
                                      commits=[("abc1234", "wip")]))
assert not applies, "tried to pull onto uncommitted changes"

# and so is a commit that needs new dependencies: restarting into a missing
# PySide6 would take the app down and not bring it back
win._on_update_checked(updater.Status(ok=True, behind=1,
                                      requirements_changed=True,
                                      commits=[("abc1234", "bump deps")]))
assert not applies, "auto-pulled a commit that changes requirements.txt"

# a failed pull stands down for the session instead of retrying every 20 min
win._on_update_applied(False, "boom")
assert win._auto_blocked
applies.clear()
win._on_update_checked(new_commit)
assert not applies, "kept retrying a pull that already failed"

win._auto_blocked = False
win.sw_auto_update.switch.setChecked(False)
win._pull()
del win._apply_update
print("OK  unattended updating waits for an idle macro and gives up on failure")

# ------------------------------------------------- 14) stale preview guard
win.stack.setCurrentIndex(PAGE_FARM)
app.processEvents()
shot2 = QPixmap(400, 300)
shot2.fill(QColor("#204050"))
win._shot = shot2
win._shot_origin = (0, 0)
win._applying_points = True
win.sp_fx.setValue(200)
win.sp_fy.setValue(150)
win._applying_points = False
win._store_thumb("filter", 200, 150)
assert win._thumb_filter.has_preview, "picking should leave a preview"

# typing a coordinate by hand invalidates the crop it no longer matches
win.sp_fx.setValue(640)
app.processEvents()
assert not win._thumb_filter.has_preview, "stale preview survived a manual edit"
print("OK  hand-edited coordinates drop the preview that no longer matches")

# ------------------------------------------------- 15) log escaping
win.log_view.clear()
win._log('window found: "<script>Ark & Co</script>"', "ok")
app.processEvents()
logged = win.log_view.toPlainText()
assert "<script>" in logged, f"escaped text was lost: {logged}"
assert "&amp;" not in logged, "double-escaped the ampersand"
print("OK  window titles cannot inject markup into the log")

# ------------------------------------------------- 16) picker guards
win._picking = True
win.engine = None
win._start_macro()
assert win.engine is None, "macro armed while the picker was open"
win._picking = False
print("OK  the macro refuses to arm while points are being picked")

# ------------------------------------------------- 17) english formatting
win._on_stats(1284, 3)
assert win.tile_clicks.value.text() == "1,284", win.tile_clicks.value.text()
print("OK  numbers use the app's own locale")

# ------------------------------------------------- 18) GeForce NOW profile
win.stack.setCurrentIndex(PAGE_SETTINGS)
win.ed_window.setText("ARK")
win.sp_latency.setValue(0)
win.cb_platform.setCurrentIndex(1)          # GeForce NOW
app.processEvents()
assert win.cfg.target.platform == "geforce_now"
assert win.ed_window.text() == "GeForce NOW", "did not retarget the client"
assert win.cfg.target.stream_latency_ms == 250, "no latency allowance"
assert "GeForce NOW" in win.platform_note.text()

# background delivery is impossible through the stream: the entry is greyed
# out, the note says why, and anything that selects it anyway is bounced back
assert not win.cb_mode.model().item(1).isEnabled(), \
    "background delivery is still selectable on a streamed session"
assert "greyed out on GeForce NOW" in win.mode_note.text()
win.cb_mode.setCurrentIndex(1)
app.processEvents()
assert win.cb_mode.currentIndex() == 0, "background delivery stuck on GFN"
assert win.cfg.target.mode == "foreground", win.cfg.target.mode

# a hand-picked title and latency survive going back to native
win.ed_window.setText("ArkAscended")
win.sp_latency.setValue(180)
win.cb_platform.setCurrentIndex(0)
app.processEvents()
assert win.cfg.target.platform == "native"
assert win.ed_window.text() == "ArkAscended", "clobbered a custom title"
assert win.cfg.target.stream_latency_ms == 180, "clobbered a custom latency"
print("OK  GeForce NOW profile moves defaults without eating your edits")

# ------------------------------------------------- 19) letterboxed geometry
win.cb_platform.setCurrentIndex(1)
win._pull()
original_rect = (100, 50, 1920, 1200)       # a 16:10 client window
w_module = sys.modules["arkmacro.winapi"]
w_module.find_window = lambda _f: 7
w_module.client_rect = lambda _h: original_rect
# the picture is 16:9 inside it, so 60px of bar top and bottom
assert win._game_area() == (100, 110, 1920, 1080), win._game_area()
win.cb_platform.setCurrentIndex(0)
win._pull()
assert win._game_area() == original_rect, "native must use the whole window"
print("OK  streaming measures the video, native measures the window")

# ------------------------------------------------- 20) anti-afk guards
taps: list[int] = []
w_module.tap = lambda vk, hold=0.0: taps.append(vk)
w_module.is_foreground = lambda _h: True
win.sw_afk.switch.setChecked(True)
win.ed_afk_key.setText("f15")
win.sp_afk_interval.setValue(30)
app.processEvents()
assert win._afk_timer.isActive(), "enabling did not arm the timer"

win._afk_tick()
assert taps == [0x7E], f"F15 was not tapped: {taps}"

# never in the middle of a drop pass, and never while picking points
taps.clear()
win._state = "dropping"
win._afk_tick()
win._state = "idle"
win._picking = True
win._afk_tick()
win._picking = False
assert taps == [], "ticked at a moment it should have stayed quiet"

# nor into whatever else the user is doing
w_module.is_foreground = lambda _h: False
win._afk_tick()
assert taps == [], "ticked while the game was not in front"
w_module.is_foreground = lambda _h: True

# a bad key name disarms instead of tapping nonsense forever
win.ed_afk_key.setText("not-a-key")
app.processEvents()
win._afk_tick()
assert taps == [] and not win._afk_timer.isActive()
win.ed_afk_key.setText("f15")
win.sw_afk.switch.setChecked(False)
app.processEvents()
assert not win._afk_timer.isActive(), "disabling did not stop the timer"
print("OK  anti-afk taps a dead key, and only when it is safe to")

# ------------------------------------------------- 21) closing the inventory
win.stack.setCurrentIndex(PAGE_FARM)
win.cb_close.setCurrentIndex(1)             # Esc
win.sp_close_presses.setValue(1)
win.cb_close.setCurrentIndex(0)             # the inventory key only toggles
app.processEvents()
assert win.sp_close_presses.value() == 1, win.sp_close_presses.value()
win.cb_close.setCurrentIndex(1)             # Esc: the search field eats one
app.processEvents()
assert win.sp_close_presses.value() == 2, win.sp_close_presses.value()
win._pull()
assert win.cfg.drop.close_with == "esc" and win.cfg.drop.close_presses == 2
print("OK  the close press count follows the key that gets sent")

# ------------------------------------------------- 22) hold-to-drop sweep
win.stack.setCurrentIndex(PAGE_FARM)
moves: list[tuple[int, int]] = []
taps.clear()                                # `taps` records w.tap, from 20)
held = {"down": False}
w_module.move_cursor = lambda x, y: moves.append((x, y))
w_module.get_cursor_pos = lambda: (7, 9)
w_module.key_is_down = lambda _vk: held["down"]
w_module.is_foreground = lambda _h: True
w_module.find_window = lambda _f: 1

# no area picked yet: nothing to sweep, so the watcher stays off
win.cfg.hold_drop.area = [0, 0, 0, 0]
win.sw_hold.switch.setChecked(True)
win._pull()
assert not win._hold_watch.isActive(), "armed without an area"
assert "No area selected" in win.lbl_hold_area.text()

# with an area, the watcher runs — but only the key starts a sweep.
# Manual is the mode where your own finger holds the drop key.
win.cfg.hold_drop.area = [100, 200, 240, 200]
win.cfg.hold_drop.area_resolution = list(w_module.screen_size())
win.cb_hold_mode.setCurrentIndex(2)         # hold the drop key yourself
win.ed_hold_key.setText("o")
win.sp_hold_cols.setValue(4)
win.sp_hold_rows.setValue(4)
win.sp_hold_dwell.setValue(5)
win._pull()
assert win._hold_watch.isActive(), "an area was set and it did not arm"
assert "16 slots" in win.lbl_hold_area.text(), win.lbl_hold_area.text()

win._watch_hold_key()
assert not win._sweep_timer.isActive(), "swept without the key being held"
assert moves == [], f"moved the mouse with the key up: {moves}"

# key down: the sweep starts and walks the slots one tick at a time
held["down"] = True
win._watch_hold_key()
assert win._sweep_timer.isActive(), "holding the key did not start the sweep"
for _ in range(16):
    win._sweep_step()
# one move to step onto the first slot, then one per tick
assert len(moves) == 17, f"{len(moves)} moves for the start plus 16 ticks"
assert moves[:4] == [(130, 225), (190, 225), (250, 225), (310, 225)], moves[:4]
# and it loops: slot 17 is slot 1 again
assert moves[16] == moves[0], "the sweep stopped instead of looping"
# manual sends no keys at all — the player's own finger is what drops
assert taps == [], f"pressed the key while the player was holding it: {taps}"

# key up: it stops within one slot and puts the pointer back
held["down"] = False
win._sweep_step()
assert not win._sweep_timer.isActive(), "kept sweeping after the key came up"
assert moves[-1] == (7, 9), f"the cursor was left on a slot: {moves[-1]}"
print("OK  hold-to-drop sweeps while the drop key is held, and loops")

# ------------------------- 22a) toggle mode: press on, press off
# A separate activation key, so nothing has to be held. The macro is what taps
# the drop key now.
win.cb_hold_mode.setCurrentIndex(0)         # press to start and stop
win.ed_hold_activate.setText("f3")
win._pull()
moves.clear()
taps.clear()
assert "«F3» starts and stops it" in win.lbl_hold_area.text(), \
    win.lbl_hold_area.text()

# the activation key going down is a press; holding it is not another one
held["down"] = True
win._watch_hold_key()
assert win._sweep_timer.isActive(), "the press did not start the sweep"
win._watch_hold_key()
win._watch_hold_key()
assert win._sweep_timer.isActive(), "a still-held key was read as a new press"

# it keeps going with the key released — that is the whole point of the mode
held["down"] = False
for _ in range(4):
    win._watch_hold_key()
    win._sweep_step()
assert win._sweep_timer.isActive(), "letting go stopped a toggled sweep"
# and because nobody is holding the drop key, the macro has to send it itself
assert len(taps) == 4, f"a toggled sweep sent {len(taps)} presses for 4 slots"
assert set(taps) == {0x4F}, f"it tapped something other than the drop key: {taps}"

# the press is short next to the tick: it runs on the UI thread, so a hold as
# long as the dwell would stall the window and stack the timers up
holds: list[float] = []
w_module.tap = lambda vk, hold=0.0: (taps.append(vk), holds.append(hold))
win.sp_hold_dwell.setValue(15)              # someone chasing speed
win._pull()
win._sweep_step()
assert holds and holds[-1] <= 0.015 / 2, f"a {holds[-1]:.3f}s press in a 15ms tick"
win.sp_hold_dwell.setValue(40)
win._pull()
w_module.tap = lambda vk, hold=0.0: taps.append(vk)

# the next press stops it, and the cursor goes back
held["down"] = True
win._watch_hold_key()
assert not win._sweep_timer.isActive(), "the second press did not stop it"
assert moves[-1] == (7, 9), f"the cursor was left on a slot: {moves[-1]}"
held["down"] = False
win._watch_hold_key()
print("OK  toggle mode starts and stops on a press, and sends the key itself")

# ------------------------- 22b) a toggled sweep stops if ARK goes away
# nobody is holding a key to release, so losing focus is the only thing left
# between a runaway sweep and somebody else's window
held["down"] = True
win._watch_hold_key()
held["down"] = False
assert win._sweep_timer.isActive()
w_module.is_foreground = lambda _h: False
win._sweep_step()
assert not win._sweep_timer.isActive(), "kept sweeping after ARK lost focus"
w_module.is_foreground = lambda _h: True
win.cb_hold_mode.setCurrentIndex(2)         # back to holding the drop key
win._pull()
print("OK  a toggled sweep gives up when the game is no longer in front")

# ------------------------- 22c) the guards around it
held["down"] = True
moves.clear()


class Farming:
    @staticmethod
    def isRunning():
        return True


# an autoclick loose in an open inventory would move items, not drop them
win.engine = Farming()
win._watch_hold_key()
assert not win._sweep_timer.isActive(), "swept while the macro was farming"
win.engine = None

# nor into whatever else has focus
w_module.is_foreground = lambda _h: False
win._watch_hold_key()
assert not win._sweep_timer.isActive(), "swept while ARK was not in front"
w_module.is_foreground = lambda _h: True

# nor over the frozen picker
win._picking = True
win._watch_hold_key()
assert not win._sweep_timer.isActive(), "swept while picking"
win._picking = False

# the activation key cannot be the drop key: pressing the thing the macro is
# supposed to send is the circle this whole split exists to avoid
win.cb_hold_mode.setCurrentIndex(0)
win.ed_hold_activate.setText("o")
win._pull()
win._watch_hold_key()
assert not win._sweep_timer.isActive(), "ran with the activation key as the "\
    "drop key"
assert not win.sw_hold.switch.isChecked(), "a circular bind was left armed"
win.ed_hold_activate.setText("f3")
win.sw_hold.switch.setChecked(True)
win.cb_hold_mode.setCurrentIndex(2)
win._pull()

# a key name that does not exist disarms instead of watching nothing forever
win.ed_hold_key.setText("not-a-key")
win._pull()
win._watch_hold_key()
assert not win._hold_watch.isActive(), "kept watching a key that cannot exist"
assert not win._sweep_timer.isActive()
assert moves == [], f"moved the mouse in a case it should have refused: {moves}"

win.ed_hold_key.setText("o")
win.sw_hold.switch.setChecked(False)
win._pull()
assert not win._hold_watch.isActive(), "disabling did not stop the watcher"
held["down"] = False
print("OK  hold-to-drop refuses while farming, unfocused, picking or misbound")

# ------------------------------------------------- 23) skin overcap
# Two different keys, and the distinction is the feature: the activation key is
# yours and only tells the app to start, and the chord is the game's — held by
# the macro, not by you. Pressing the chord to start a macro that holds the
# chord would be a circle.
moves.clear()
taps.clear()
downs: list[int] = []
ups: list[int] = []
w_module.key_down = lambda vk: downs.append(vk)
w_module.key_up = lambda vk: ups.append(vk)
activate = {"down": False}
w_module.key_is_down = lambda vk: activate["down"] and vk == 0x73    # F4
win.cfg.skin_overcap.area = [100, 900, 600, 80]
win.cfg.skin_overcap.area_resolution = list(w_module.screen_size())
win.sw_skin.switch.setChecked(True)
win.ed_skin_activate.setText("f4")
win.cb_skin_mode.setCurrentIndex(0)         # press to start and stop
win.cb_skin_key.setCurrentText("2")
win.sp_skin_stops.setValue(10)
win.sp_skin_dwell.setValue(5)
win._pull()
assert win._hold_watch.isActive(), "a ready strip did not arm the watcher"
assert "18 a full lap" in win.lbl_skin_area.text(), win.lbl_skin_area.text()
assert "F4" in win.skin_note.text() and "2" in win.skin_note.text()

# the press starts it, and the macro takes Shift + the slot down itself
activate["down"] = True
win._watch_skin_key()
assert win._sweep_timer.isActive(), "the activation key did not start it"
assert downs == [0x10, 0x32], f"the macro did not hold Shift+2: {downs}"
assert ups == [], "it let go of the chord straight away"

# it keeps running with the activation key released — that is the toggle
activate["down"] = False
for _ in range(17):
    win._watch_skin_key()
    win._sweep_step()
assert win._sweep_timer.isActive(), "letting go of the activation key stopped it"
assert len(moves) == 18, f"{len(moves)} moves for a full lap"
assert all(y == 940 for _x, y in moves), "it left the middle of the strip"
assert moves[9][0] == max(x for x, _y in moves), "it never reached the far end"
assert moves[-1][0] < moves[9][0], "it did not come back"

# the next press stops it, and the chord comes back up in reverse order
activate["down"] = True
win._watch_skin_key()
assert not win._sweep_timer.isActive(), "the second press did not stop it"
assert ups == [0x32, 0x10], f"the chord was not released cleanly: {ups}"
assert moves[-1] == (7, 9), f"the cursor was left on the strip: {moves[-1]}"
print("OK  skin overcap holds the chord for you, and lets go on the way out")

# ------------------------- 23b) the Shift must never be left down
for leave in ("focus", "close"):
    downs.clear()
    ups.clear()
    # the watcher reads the key's edge, so it has to see the release first
    activate["down"] = False
    win._watch_skin_key()
    activate["down"] = True
    win._watch_skin_key()
    activate["down"] = False
    assert win._chord_held, "the macro is not holding the chord"
    if leave == "focus":
        w_module.is_foreground = lambda _h: False
        win._sweep_step()
        w_module.is_foreground = lambda _h: True
    else:
        win._stop_sweep()
    assert not win._chord_held, f"the chord survived losing {leave}"
    assert ups == [0x32, 0x10], f"Shift was left down after {leave}: {ups}"
print("OK  the held chord is released by every route out of a sweep")

# ------------------------- 23c) the two keys have to be different
win.ed_skin_activate.setText("2")           # the slot the macro holds
win._pull()
assert "different one" in win.skin_note.text(), win.skin_note.text()
win.ed_skin_activate.setText("shift")
win._pull()
assert "different one" in win.skin_note.text(), win.skin_note.text()
downs.clear()
win._watch_skin_key()
assert not win._sweep_timer.isActive() and not downs, "ran on a circular bind"
assert not win.sw_skin.switch.isChecked(), "a circular bind was left armed"
win.ed_skin_activate.setText("f4")
print("OK  the activation key cannot be part of the chord the macro holds")

# ------------------------- 23d) the two sweeps never share the cursor
win.sw_skin.switch.setChecked(True)
win._pull()
activate["down"] = False
win._watch_skin_key()                       # let the watcher see the release
activate["down"] = True
win._watch_skin_key()
assert win._sweep_kind == "skin", "the strip did not start"
# hold-to-drop is armed too; it must not take the cursor from a running strip
win._watch_hold_key()
assert win._sweep_kind == "skin", "hold-to-drop hijacked a running strip"
win._stop_sweep()
assert win._sweep_kind == "", "the kind outlived the sweep"

win.sw_skin.switch.setChecked(False)
win._pull()
activate["down"] = False
w_module.key_is_down = lambda _vk: held["down"]
print("OK  hold-to-drop and skin overcap never run at the same time")

# ------------------------------------------------- 24) the area picker
from arkmacro.ui.picker import AreaPicker  # noqa: E402

area_picker = AreaPicker(shot, QRect(0, 0, 800, 600), 4, 4, (1920, 0))
area_picker._anchor = QPoint(340, 400)
area_picker._cursor = QPoint(100, 200)
# dragged bottom-right to top-left, on a second monitor: still the same box,
# and the origin puts it back in physical desktop coordinates
assert area_picker._selection() == [2020, 200, 240, 200], area_picker._selection()
assert area_picker._widget_rect() == QRect(100, 200, 240, 200)
area_picker.deleteLater()
print("OK  the area picker normalises the drag and offsets to the real screen")

# ------------------------- 24b) a scaled display, which is every laptop
# Mouse events arrive in Qt's LOGICAL pixels; everything the macro does later —
# moving the cursor, reading the screen — is in PHYSICAL ones. At 100% the two
# are identical and mixing them survives; at 150% the area comes out a third too
# small and in the wrong place. That is the bug this pins down.
scaled = AreaPicker(shot, QRect(0, 0, 1280, 720), 4, 4, (0, 0), ratio=1.5)
scaled._anchor = QPoint(200, 100)
scaled._cursor = QPoint(400, 300)
assert scaled._selection() == [300, 150, 300, 300], scaled._selection()
# the drawn box stays in widget space — that is what the eye checks against
assert scaled._widget_rect() == QRect(200, 100, 200, 200)

# a scaled second monitor: the logical origin scales with everything else
offset = AreaPicker(shot, QRect(1280, 0, 1280, 720), 4, 4, (1280, 0), ratio=1.5)
offset._anchor = QPoint(0, 0)
offset._cursor = QPoint(200, 200)
assert offset._selection() == [1920, 0, 300, 300], offset._selection()
scaled.deleteLater()
offset.deleteLater()
print("OK  the area picker converts logical pixels to physical ones")

# ------------------------- 24c) what the picker hands back is what gets stored
win._pick_area_kind = "drop"
win._on_area_picked(300, 150, 300, 300)
assert win.cfg.hold_drop.area == [300, 150, 300, 300], win.cfg.hold_drop.area
assert win.cfg.hold_drop.area_resolution == list(w_module.screen_size())
win._pick_area_kind = "skin"
win._on_area_picked(100, 900, 600, 80)
assert win.cfg.skin_overcap.area == [100, 900, 600, 80]
assert win.cfg.hold_drop.area == [300, 150, 300, 300], "the two areas collided"
win._pick_area_kind = "drop"

# the geometry line is logged every pick, and a capture that does not match the
# screen it came from is called out — that is the shape of the bug this had
lines: list[str] = []
original_log = win._log
win._log = lambda message, level="info": lines.append(f"{level}:{message}")
win._log_screen_geometry(QRect(0, 0, 1280, 720), 1.5, QPixmap(1920, 1080))
assert any("1.5x scaling" in ln for ln in lines), lines
assert not any(ln.startswith("warn:") for ln in lines), lines
lines.clear()
win._log_screen_geometry(QRect(0, 0, 1280, 720), 1.5, QPixmap(1280, 720))
assert any("does not match the screen" in ln for ln in lines), lines
win._log = original_log
print("OK  a picked area reaches the right macro, and the scaling is logged")

# ------------------------- 24d) rescaling only touches the primary screen
# An area dragged on a second monitor has nothing to do with the primary
# changing resolution; scaling it by the primary's ratio would walk a good
# selection off target.
win.cfg.hold_drop.area = [100, 100, 400, 300]        # inside 1920x1080
win.cfg.hold_drop.area_resolution = [1920, 1080]
win.cfg.skin_overcap.area = [2100, 900, 600, 80]     # on a second monitor
win.cfg.skin_overcap.area_resolution = [1920, 1080]
w_module.screen_size = lambda: (2560, 1440)
win._maybe_rescale_area()
assert win.cfg.hold_drop.area_resolution == [2560, 1440], "the primary one "\
    "was not rescaled"
assert win.cfg.hold_drop.area != [100, 100, 400, 300], "it did not move"
assert win.cfg.skin_overcap.area == [2100, 900, 600, 80], \
    "an off-primary selection was rescaled anyway"
w_module.screen_size = lambda: (1920, 1080)
print("OK  only areas that sat on the primary screen get rescaled")

# ------------------------- 24e) the display check has to be able to fail
# It exists because the picked-area bug could not be reproduced anywhere but on
# a scaled display. A check that always passes would be worse than none.
lines.clear()
win._log = lambda message, level="info": lines.append(f"{level}:{message}")
w_module.dpi_awareness = lambda: "per-monitor v2"
w_module.screen_pixel = lambda x, y: (30 + x % 5, 40, 50)
w_module.screen_samples = lambda points: [w_module.screen_pixel(x, y)
                                          for x, y in points]
win._check_display()
assert any("DPI awareness" in ln for ln in lines), lines
assert any(ln.startswith("ok:") and "round-trips" in ln for ln in lines), lines
assert any(ln.startswith("ok:") and "screen reads fine" in ln for ln in lines), \
    lines
assert not any(ln.startswith("err:") for ln in lines), lines

# A screen that hands back nothing is the state this machine was actually in
# while the check reported a clean bill of health: every drop pass was refusing
# for want of a readable screen, and the check never once read a pixel. Green
# has to mean the guards can do their job.
lines.clear()
w_module.screen_pixel = lambda x, y: None
w_module.screen_samples = lambda points: None
win._check_display()
assert any(ln.startswith("err:") and "cannot be read" in ln for ln in lines), lines
assert lines[-1].startswith("err:"), lines
w_module.screen_pixel = lambda x, y: (30 + x % 5, 40, 50)
w_module.screen_samples = lambda points: [w_module.screen_pixel(x, y)
                                          for x, y in points]

# a cursor Windows reports somewhere the app cannot place is a real failure,
# and has to read as one
w_module.get_cursor_pos = lambda: (999999, 999999)
ok, detail = win._round_trip_cursor()
assert not ok and "not on any screen" in detail, detail

# and so is a coordinate that does not survive the trip
w_module.get_cursor_pos = lambda: (100, 100)
ok, detail = win._round_trip_cursor()
assert ok, detail
win._log = original_log

# the awkward geometries, checked directly: a second monitor to the LEFT of the
# primary sits at a negative offset, which is a real reported setup, and any
# scaling other than 100% is the case that broke the picker
for point, origin, ratio in (((1231, 621), (0, 0), 1.0),
                             ((-900, 400), (-1920, 0), 1.0),
                             ((742, 511), (0, 0), 1.5),
                             ((-2400, 300), (-1920, 0), 1.5),
                             ((3000, 700), (1920, 0), 1.25)):
    back, drift = round_trip(point, origin, ratio)
    assert drift <= 1, f"{point} at {ratio}x from {origin} came back {back}"
print("OK  the display check measures the machine, and can say no")

# ------------------------- 25) the stop sign is captured off the frozen shot
# By the time the capture runs the app is back in front of the game, so reading
# the live screen would remember the app's own window and the macro would stop
# the moment it was hidden. The picture has to come out of the screenshot the
# box was just dragged on.
lines.clear()
win._log = lambda message, level="info": lines.append(f"{level}:{message}")

shot = QPixmap(200, 200)
shot.fill(QColor(20, 22, 26))
painter = QPainter(shot)
painter.fillRect(40, 40, 60, 60, QColor(220, 60, 55))
painter.fillRect(60, 60, 20, 20, QColor(240, 240, 240))
painter.end()
win._shot = shot
win._shot_origin = (500, 400)
win._pick_area_kind = "stop"
w_module.screen_size = lambda: (1920, 1080)
# the live screen answers something else entirely, so a capture that read it
# instead of the screenshot is visible in the result
w_module.screen_samples = lambda points: [(1, 2, 3)] * len(points)

win._on_area_picked(540, 440, 60, 60)      # the red square, in screen coords
assert win.cfg.stop_sign.area == [540, 440, 60, 60]
assert win.cfg.stop_sign.sample, "nothing was captured"
assert (1, 2, 3) not in [tuple(c) for c in win.cfg.stop_sign.sample], \
    "it read the live screen instead of the frozen capture"
assert any("stop sign captured" in ln for ln in lines), lines
shades = stopsign.distinct(win.cfg.stop_sign.sample, win.cfg.stop_sign.tolerance)
assert shades >= 2, f"the red square and the white one read as {shades} shade(s)"

# a box dragged over empty HUD is flat, matches half the screen, and has to be
# called out at capture time rather than discovered by a farm stopping at random
lines.clear()
win._on_area_picked(500, 400, 30, 30)      # all background
assert any("flat colour" in ln and ln.startswith("err:") for ln in lines), lines

# A resolution change is the one thing a rescale cannot save here. The box could
# be moved like the sweep areas, but what it holds is a remembered picture, and
# the game draws that icon at a different size now — the colours would be
# compared against pixels they were never taken from, which either never matches
# or matches something else, and the second one stops a farm for no reason.
lines.clear()
win._on_area_picked(540, 440, 60, 60)
win.sw_stop.switch.setChecked(True)
assert win.cfg.stop_sign.sample and win.cfg.stop_sign.area_resolution == [1920, 1080]
w_module.screen_size = lambda: (2560, 1440)
win._maybe_rescale_area()
assert win.cfg.stop_sign.sample == [], "a picture from another resolution survived"
assert not win.sw_stop.switch.isChecked(), "it stayed armed with nothing to match"
assert any("captured stop-sign icon was dropped" in ln for ln in lines), lines
w_module.screen_size = lambda: (1920, 1080)

# and forgetting it clears both halves, so nothing half-remembered survives
win._on_area_picked(540, 440, 60, 60)
win._forget_stop_sign()
assert win.cfg.stop_sign.sample == [] and win.cfg.stop_sign.area == [0, 0, 0, 0]
assert not win.sw_stop.switch.isChecked()
assert "capture" in MacroEngine(win.cfg)._stop_sign_problem()
win._log = original_log
print("OK  the stop sign is captured off the frozen screen, and flat boxes are "
      "refused")

win.hotkeys.stop()
win.close()
print("\nALL UI TESTS PASSED")

