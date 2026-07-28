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
win.cb_trigger.setCurrentIndex(1)
app.processEvents()
assert win.sp_every_clicks.isVisible() and win.lbl_clicks.isVisible()
assert not win.sp_interval.isVisible() and not win.lbl_interval.isVisible()
win.cb_trigger.setCurrentIndex(2)
app.processEvents()
assert not win.sp_interval.isVisible() and not win.sp_every_clicks.isVisible()
print("OK  trigger fields show and hide with the label")

# ------------------------------------------------- 5) config round trip
win.sw_dry.switch.setChecked(True)
win.cb_mode.setCurrentIndex(1)
win.sp_cps_min.setValue(11.5)
win.ed_inv_key.setText("TAB")
win.hk_toggle.setText("Ctrl+F5")
win.sp_fx.setValue(277)
win.sp_fy.setValue(193)
win._pull()
win._save()

reloaded = Config.load(sandbox)
assert reloaded.drop.dry_run is True
assert reloaded.target.mode == "background"
assert reloaded.autoclick.cps_min == 11.5
assert reloaded.drop.inventory_key == "tab", reloaded.drop.inventory_key
assert reloaded.hotkeys.toggle == "Ctrl+F5"
assert reloaded.drop.filter_point == [277, 193]
assert reloaded.drop.templates == win.cfg.drop.templates
print("OK  every control round-trips through config.json")

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

# background delivery is impossible through the stream, and it says so
win.cb_mode.setCurrentIndex(1)
app.processEvents()
assert "cannot work through GeForce NOW" in win.mode_note.text()
win.cb_mode.setCurrentIndex(0)

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

win.hotkeys.stop()
win.close()
print("\nALL UI TESTS PASSED")

