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
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arkmacro import config as config_module  # noqa: E402
from arkmacro import updater  # noqa: E402
from arkmacro.config import Config  # noqa: E402
from arkmacro.ui import icons  # noqa: E402
from arkmacro.ui.backdrop import Backdrop, load_brand  # noqa: E402
from arkmacro.ui.main_window import APP_NAME, MainWindow, NAV  # noqa: E402
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
for index, (_glyph, name) in enumerate(NAV):
    win.stack.setCurrentIndex(index)
    app.processEvents()
    page = win.stack.widget(index)
    assert page.widget().sizeHint().width() <= 1060, \
        f"page {name} is wider than the window and would clip"
print(f"OK  {len(NAV)} pages build and fit")

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

# rename the selected row, keeping its checked state
win.stack.setCurrentIndex(2)
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
assert win.stack.currentIndex() == 3, "user was not sent to the Points tab"
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
win.stack.setCurrentIndex(4)
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
win.stack.setCurrentIndex(3)
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
win.stack.setCurrentIndex(4)
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
win.stack.setCurrentIndex(2)
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
win.stack.setCurrentIndex(3)
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

# with an area, the watcher runs — but only the key starts a sweep
win.cfg.hold_drop.area = [100, 200, 240, 200]
win.cfg.hold_drop.area_resolution = list(w_module.screen_size())
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
# holding sends no keys at all — the player's own finger is what drops
assert taps == [], f"pressed the key while the player was holding it: {taps}"

# key up: it stops within one slot and puts the pointer back
held["down"] = False
win._sweep_step()
assert not win._sweep_timer.isActive(), "kept sweeping after the key came up"
assert moves[-1] == (7, 9), f"the cursor was left on a slot: {moves[-1]}"
print("OK  hold-to-drop sweeps while the key is held, and loops")

# ------------------------- 22a) toggle mode: press on, press off
win.cb_hold_mode.setCurrentIndex(1)         # press to start and stop
win._pull()
moves.clear()
taps.clear()
assert "another stops it" in win.lbl_hold_area.text(), win.lbl_hold_area.text()

# the key going down is a press; holding it down is not another one
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
# and because nobody is holding the key, the app has to send it itself
assert len(taps) == 4, f"a toggled sweep sent {len(taps)} presses for 4 slots"
assert set(taps) == {0x4F}, taps

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
win.cb_hold_mode.setCurrentIndex(0)
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
# Shift plus a hotbar key runs the cursor along a strip. Same machinery as
# hold-to-drop, a different path and a chord instead of one key.
moves.clear()
taps.clear()
chord = {"shift": False, "key": False}
w_module.key_is_down = lambda vk: (chord["shift"] if vk == 0x10
                                   else chord["key"])
win.cfg.skin_overcap.area = [100, 900, 600, 80]
win.cfg.skin_overcap.area_resolution = list(w_module.screen_size())
win.sw_skin.switch.setChecked(True)
win.cb_skin_key.setCurrentText("2")
win.sp_skin_stops.setValue(10)
win.sp_skin_dwell.setValue(5)
win._pull()
assert win._hold_watch.isActive(), "a ready strip did not arm the watcher"
assert "18 a full lap" in win.lbl_skin_area.text(), win.lbl_skin_area.text()

# the key alone is not the chord, and neither is Shift alone
chord["key"] = True
win._watch_skin_key()
assert not win._sweep_timer.isActive(), "ran on the key without Shift"
chord["key"], chord["shift"] = False, True
win._watch_skin_key()
assert not win._sweep_timer.isActive(), "ran on Shift alone"
assert moves == [], f"moved the mouse without the chord: {moves}"

# both down: it runs the strip, out and back, and sends no keys of its own
chord["key"] = True
win._watch_skin_key()
assert win._sweep_timer.isActive(), "the chord did not start the strip"
for _ in range(17):
    win._sweep_step()
assert len(moves) == 18, f"{len(moves)} moves for a full lap"
assert all(y == 940 for _x, y in moves), "it left the middle of the strip"
assert moves[9][0] == max(x for x, _y in moves), "it never reached the far end"
assert moves[-1][0] < moves[9][0], "it did not come back"
assert taps == [], f"skin overcap pressed keys of its own: {taps}"

# breaking the chord stops it within one stop, and the cursor goes back
chord["shift"] = False
win._sweep_step()
assert not win._sweep_timer.isActive(), "kept running with Shift released"
assert moves[-1] == (7, 9), f"the cursor was left on the strip: {moves[-1]}"
print("OK  skin overcap runs the strip on the chord, and sends nothing")

# ------------------------- 23b) the two sweeps never share the cursor
chord["shift"], chord["key"] = True, True
win._watch_skin_key()
assert win._sweep_kind == "skin"
# hold-to-drop is armed too, and its key reads as down through the same fake —
# it must not take the cursor from a strip that is already running
win._watch_hold_key()
assert win._sweep_kind == "skin", "hold-to-drop hijacked a running strip"
win._stop_sweep()
assert win._sweep_kind == "", "the kind outlived the sweep"

win.sw_skin.switch.setChecked(False)
win._pull()
chord["shift"] = chord["key"] = False
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

win.hotkeys.stop()
win.close()
print("\nALL UI TESTS PASSED")

