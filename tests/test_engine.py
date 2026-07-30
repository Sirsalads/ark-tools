"""
Functional tests for the engine, with the input layer mocked.

Runs without the game and without sending a single real click:
    python tests/test_engine.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from arkmacro import engine as eng  # noqa: E402
from arkmacro import layout as ark_layout  # noqa: E402
from arkmacro import presets  # noqa: E402
from arkmacro import sweep as ark_sweep  # noqa: E402
from arkmacro.config import Config  # noqa: E402
from arkmacro.hotkeys import (MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT,  # noqa: E402
                              parse)

app = QCoreApplication(sys.argv[:1])
calls: list[tuple] = []


def pump(seconds: float) -> None:
    """Wait while processing Qt events — cross-thread signals are queued."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


class FakeW:
    """Stands in for arkmacro.engine.w, recording what would be sent."""

    VK = {"i": 0x49, "esc": 0x1B, "backspace": 0x08,
          "4": 0x34, "5": 0x35, "9": 0x39}

    # None for an unknown name, exactly like the real one: a fallback code here
    # would hide every "that is not a key" check from the tests
    @staticmethod
    def vk_from_name(name):
        return FakeW.VK.get(name)

    @staticmethod
    def find_window(_fragment):
        return None

    @staticmethod
    def is_window(_hwnd):
        return False

    @staticmethod
    def client_rect(_hwnd):
        return None

    @staticmethod
    def screen_to_client(_hwnd, x, y):
        return x, y

    @staticmethod
    def is_foreground(_hwnd):
        return True

    @staticmethod
    def get_cursor_pos():
        return (100, 100)

    @staticmethod
    def click(button, hold):
        calls.append(("click", button))

    @staticmethod
    def click_at(x, y, button="left", hold=0.0, settle=0.0):
        calls.append(("click_at", x, y))

    @staticmethod
    def post_click(*args, **_kwargs):
        calls.append(("post_click", args[1], args[2]))

    @staticmethod
    def tap(vk, hold=0.0):
        calls.append(("key", hex(vk)))

    @staticmethod
    def post_key(*args, **_kwargs):
        calls.append(("post_key", hex(args[1])))

    @staticmethod
    def type_text(text, delay=0.0, unicode_mode=False):
        calls.append(("type", text))

    @staticmethod
    def post_text(_hwnd, text, delay=0.0):
        calls.append(("type", text))

    @staticmethod
    def move_cursor(x, y):
        pass

    # unreadable screen by default: the engine falls back to counting presses
    @staticmethod
    def screen_pixel(_x, _y):
        return None


eng.w = FakeW

cfg = Config()
cfg.target.start_delay_s = 0
cfg.target.require_focus = False
cfg.drop.filter_point = [960, 300]
cfg.drop.dropall_point = [1400, 900]
cfg.drop.templates = [
    {"name": "Thatch", "keyword": "thatch", "enabled": True},
    {"name": "Disabled", "keyword": "wood", "enabled": False},
    {"name": "Stone", "keyword": "stone", "enabled": True},
]
cfg.drop.open_wait_ms = 10
cfg.drop.close_wait_ms = 10
cfg.drop.after_type_wait_ms = 10
cfg.drop.after_drop_wait_ms = 10

# ------------------------------------------------- 1) exact drop pass order
engine = eng.MacroEngine(cfg)
engine.log.connect(lambda _m, _l: None)
engine._running = True
engine._run_drop()

expected = [
    ("key", hex(0x49)),                       # open the inventory
    ("click_at", 960, 300),                   # focus the filter field
    *[("key", hex(0x08))] * eng.CLEAR_KEYS,   # a human may have left a word in
    ("type", "thatch"),                       # type the keyword
    ("click_at", 1400, 900),                  # Drop All
    ("click_at", 960, 300),
    ("type", "stone"),                        # no wipe: the drop cleared the box
    ("click_at", 1400, 900),
    ("key", hex(0x1B)),                 # Esc leaves the search field
    ("key", hex(0x1B)),                 # and only then closes the inventory
]
assert calls == expected, f"\nexpected:\n{expected}\ngot:\n{calls}"
assert not any(c == ("type", "wood") for c in calls), \
    "an unchecked template must not enter the cycle"
print(f"OK  drop pass order ({len(calls)} actions, unchecked one skipped)")

# ------------------------------ 1a) the box is only wiped where ARK has not
# ARK empties the search box when Drop All fires, so a wipe per template is
# 24 keystrokes of nothing. One per pass is what is left, for the box a human
# may have typed in.
wipes = sum(1 for c in calls if c == ("key", hex(0x08)))
assert wipes == eng.CLEAR_KEYS, f"{wipes} backspaces for two templates"
print("OK  the search box is wiped once per pass, not once per template")

# --------------------------------------- 1b) the close key is configurable
for presses, close_with, key in ((1, "same", 0x49), (3, "esc", 0x1B)):
    calls.clear()
    cfg.drop.close_presses = presses
    cfg.drop.close_with = close_with
    variant = eng.MacroEngine(cfg)
    variant.log.connect(lambda _m, _l: None)
    variant._running = True
    variant._run_drop()
    tail = calls[-presses:]
    assert tail == [("key", hex(key))] * presses, tail
cfg.drop.close_presses = 2
cfg.drop.close_with = "esc"
print("OK  close key and press count come from the config")

# --------------------------- 1c) with the screen readable, it checks instead
PANEL = (40, 44, 48)
WORLD = (120, 160, 90)


class Panel:
    """Screen where the inventory closes after `shuts_at` close presses."""

    def __init__(self, shuts_at: int) -> None:
        self.shuts_at = shuts_at
        self.presses = 0

    def pixel(self, _x, _y):
        return WORLD if self.presses >= self.shuts_at else PANEL

    def tap(self, vk, hold=0.0):
        calls.append(("key", hex(vk)))
        if vk == 0x1B:                  # only the close key shuts the panel
            self.presses += 1


def close_with_screen(shuts_at: int) -> list[tuple]:
    """One drop pass against that screen; returns the keys of the close phase."""
    screen = Panel(shuts_at)
    original_tap, original_pixel = FakeW.tap, FakeW.screen_pixel
    FakeW.tap, FakeW.screen_pixel = screen.tap, screen.pixel
    # this screen answers the same colour everywhere, so the search box never
    # looks like it took the keyword — and the close phase is what is under test
    verify, cfg.drop.verify_filter = cfg.drop.verify_filter, False
    try:
        calls.clear()
        probe_engine = eng.MacroEngine(cfg)
        probe_engine.log.connect(lambda _m, _l: None)
        probe_engine._running = True
        probe_engine._run_drop()
    finally:
        FakeW.tap, FakeW.screen_pixel = original_tap, original_pixel
        cfg.drop.verify_filter = verify
    # everything after the last Drop All click is the close phase
    last_drop = max(i for i, c in enumerate(calls) if c == ("click_at", 1400, 900))
    return [c for c in calls[last_drop:] if c[0] == "key" and c[1] == hex(0x1B)]

# one press is enough on this setup: a second Esc would reach the game and
# open the pause menu, so it must not be sent
assert close_with_screen(1) == [("key", hex(0x1B))], "it overshot a closed panel"
# the search field ate the first one, so it presses again — and then stops
assert close_with_screen(2) == [("key", hex(0x1B))] * 2
# a panel that never closes is capped, then the other key gets one try
stubborn = close_with_screen(99)
assert len(stubborn) == eng.CLOSE_ATTEMPTS, stubborn
print(f"OK  the close checks the panel: 1 press when 1 is enough, "
      f"{eng.CLOSE_ATTEMPTS} at most")

# ------------------------- 1d) nothing typed, nothing dropped
# The half second after typing is a hope, not a check: if the click missed the
# search field or the stream swallowed the keys, the box is empty and Drop All
# would empty the entire inventory. So the box is read before and after.
BOX = (18, 22, 26)
GLYPH = (232, 238, 240)


class Box:
    """
    Screen where the search box fills in only when `shows_text` is set.

    Reads on the filter band answer for the box, everything else answers for the
    panel — the panel probes run along the line to Drop All, well below it.
    """

    def __init__(self, shows_text: bool) -> None:
        self.shows_text = shows_text
        self.filled = False
        self.presses = 0

    def pixel(self, x, y):
        if abs(y - 300) <= 8:
            filled = self.filled and self.shows_text and 960 <= x <= 1040
            return GLYPH if filled else BOX
        return WORLD if self.presses else PANEL

    def type_text(self, text, delay=0.0, unicode_mode=False):
        calls.append(("type", text))
        self.filled = True

    def click_at(self, x, y, button="left", hold=0.0, settle=0.0):
        calls.append(("click_at", x, y))
        if (x, y) == (1400, 900):      # Drop All: ARK empties the filter itself
            self.filled = False

    def tap(self, vk, hold=0.0):
        calls.append(("key", hex(vk)))
        if vk == 0x1B:
            self.presses += 1
        elif vk == 0x08:
            self.filled = False        # a wipe leaves the box empty again


def drop_against(screen: Box) -> tuple[list[tuple], eng.MacroEngine]:
    original = (FakeW.tap, FakeW.screen_pixel, FakeW.type_text, FakeW.click_at)
    FakeW.tap, FakeW.screen_pixel = screen.tap, screen.pixel
    FakeW.type_text, FakeW.click_at = screen.type_text, screen.click_at
    try:
        calls.clear()
        checked = eng.MacroEngine(cfg)
        checked.log.connect(lambda _m, _l: None)
        checked._running = True
        checked._run_drop()
    finally:
        (FakeW.tap, FakeW.screen_pixel, FakeW.type_text,
         FakeW.click_at) = original
    return list(calls), checked


# the keyword shows up in the box: the pass runs exactly as before
visible, ran = drop_against(Box(shows_text=True))
assert sum(1 for c in visible if c == ("click_at", 1400, 900)) == 2, visible
assert ran.drops == 1, "a pass that dropped was not counted"

# the keyword never appears: no Drop All goes out at all
blind, skipped_pass = drop_against(Box(shows_text=False))
assert not any(c == ("click_at", 1400, 900) for c in blind), \
    "Drop All was clicked with an empty search box"
assert ("type", "stone") in blind, "it stopped the pass instead of skipping one"
# and a pass that dropped nothing is not a pass done — the weight is still up
assert skipped_pass.drops == 0, "an empty pass counted on the dashboard"
# and the filter is wiped on the way out, since no drop cleared it
esc = min(i for i, c in enumerate(blind) if c == ("key", hex(0x1B)))
assert blind[esc - 1] == ("key", hex(0x08)), blind[esc - 4:esc]

# with the check off it goes out anyway — the setting is a real switch
cfg.drop.verify_filter = False
unchecked, _ = drop_against(Box(shows_text=False))
cfg.drop.verify_filter = True
assert sum(1 for c in unchecked if c == ("click_at", 1400, 900)) == 2
print("OK  Drop All only fires when the keyword is visibly in the box")

# ------------------------------------------------- 2) dry run never drops
calls.clear()
shots: list[str] = []
cfg.drop.dry_run = True
dry_engine = eng.MacroEngine(cfg)
dry_engine.log.connect(lambda _m, _l: None)
dry_engine.shot_requested.connect(shots.append)
dry_engine._running = True
dry_engine._run_drop()
app.processEvents()
assert not any(c == ("click_at", 1400, 900) for c in calls), \
    "dry run clicked Drop All"
assert any(c == ("type", "thatch") for c in calls), "dry run did not filter"
assert shots == ["thatch", "stone"], f"captures requested: {shots}"
cfg.drop.dry_run = False
print("OK  dry run filters, captures and drops nothing")

# ------------------------------------------------- 3) click cadence
calls.clear()
cfg.autoclick.cps_min = cfg.autoclick.cps_max = 20.0
cfg.drop.enabled = False
cadence_engine = eng.MacroEngine(cfg)
cadence_engine.log.connect(lambda _m, _l: None)
cadence_engine.start()
started = time.perf_counter()
pump(1.5)
cadence_engine.request_stop()
cadence_engine.wait(3000)
elapsed = time.perf_counter() - started
cps = sum(1 for c in calls if c[0] == "click") / elapsed
assert 16 <= cps <= 24, f"cadence off target: {cps:.1f}"
print(f"OK  measured cadence {cps:.1f} cps (target 20)")

# ------------------------------------------------- 4) click-count trigger
calls.clear()
cfg.drop.enabled = True
cfg.drop.trigger = "clicks"
cfg.drop.every_clicks = 5
cfg.drop.min_farm_s = 0
states: list[str] = []
click_engine = eng.MacroEngine(cfg)
click_engine.state_changed.connect(states.append)
click_engine.log.connect(lambda _m, _l: None)
click_engine.start()
pump(2.0)
click_engine.request_stop()
click_engine.wait(3000)
passes = sum(1 for c in calls if c == ("click_at", 1400, 900))
assert passes >= 2, "click-count trigger never fired"
assert "dropping" in states and "farming" in states
print(f"OK  click-count trigger ({passes} passes)")

# ----------------------------- 4b) the count alone does not open the panel
# a dino with an attack cooldown burns the clicks in seconds; the pass has to
# wait out the farming stretch as well
calls.clear()
cfg.drop.min_farm_s = 30
gated_engine = eng.MacroEngine(cfg)
gated_engine.log.connect(lambda _m, _l: None)
gated_engine.start()
pump(1.5)
gated_engine.request_stop()
gated_engine.wait(3000)
assert sum(1 for c in calls if c[0] == "click") > 5, "it stopped farming"
assert not any(c == ("click_at", 1400, 900) for c in calls), \
    "the pass ran before the farming stretch was up"
cfg.drop.min_farm_s = 0
print("OK  the click trigger waits out the farming stretch too")

# ------------------------------------------------- 5) timer trigger
calls.clear()
cfg.drop.trigger = "interval"
cfg.drop.interval_s = 1
timer_engine = eng.MacroEngine(cfg)
timer_engine.log.connect(lambda _m, _l: None)
timer_engine.start()
# the interval is up at 1 s and the pass itself needs a moment: the box gets
# wiped once per pass, and that is 24 keystrokes before the first keyword
pump(2.4)
timer_engine.request_stop()
timer_engine.wait(3000)
assert any(c == ("click_at", 1400, 900) for c in calls), "timer trigger failed"
print("OK  timer trigger")

# ------------------------------------------------- 5b) auto-feed
# The hazard this has to avoid: a hotbar key pressed while the search field
# holds the keyboard types a digit into the filter instead of reaching the
# hotbar. So feeding lives in the farming loop, never inside a drop pass.
FOOD, WATER = hex(0x34), hex(0x35)


class Watcher:
    """Records the keys, and flags any feed press sent with the panel open."""

    def __init__(self) -> None:
        self.in_panel = False
        self.violations: list[str] = []

    def tap(self, vk, hold=0.0):
        key = hex(vk)
        calls.append(("key", key))
        if key in (FOOD, WATER) and self.in_panel:
            self.violations.append(key)
        if vk == 0x49:                  # the inventory key opened the panel
            self.in_panel = True
        elif vk == 0x1B:                # esc closed it again
            self.in_panel = False


calls.clear()
cfg.drop.trigger = "interval"
cfg.drop.interval_s = 1
cfg.auto_feed.enabled = True
cfg.auto_feed.interval_s = 0            # feed on every pass through the loop
cfg.auto_feed.gap_ms = 10
watcher = Watcher()
original_tap = FakeW.tap
FakeW.tap = watcher.tap
try:
    fed = eng.MacroEngine(cfg)
    fed.log.connect(lambda _m, _l: None)
    fed.start()
    pump(2.6)
    fed.request_stop()
    fed.wait(3000)
finally:
    FakeW.tap = original_tap

pairs = [i for i, c in enumerate(calls) if c == ("key", FOOD)]
assert pairs, "auto-feed never fired"
# food first, water straight after, every time
for index in pairs:
    assert calls[index + 1] == ("key", WATER), calls[index:index + 3]
assert not watcher.violations, \
    f"a hotbar key was sent with the inventory open: {watcher.violations}"
assert any(c == ("click_at", 1400, 900) for c in calls), \
    "feeding starved the drop pass"
print(f"OK  auto-feed presses both slots ({len(pairs)}x) and never mid-pass")

# ------------------------- 5c) slots that would misfire refuse to arm
for food, water, inv, why in (
    ("4", "4", "i", "the same slot twice"),
    ("i", "5", "i", "the inventory key as a slot"),
    ("nonsense", "5", "i", "a key name that does not exist"),
):
    cfg.auto_feed.food_key, cfg.auto_feed.water_key = food, water
    cfg.drop.inventory_key = inv
    picky = eng.MacroEngine(cfg)
    assert picky._feed_problem(), f"accepted {why}"

cfg.auto_feed.food_key, cfg.auto_feed.water_key = "4", "5"
cfg.drop.inventory_key = "i"
assert not eng.MacroEngine(cfg)._feed_problem(), "rejected a sane pair of slots"

# and a bad pair takes auto-feed out without taking the farm down with it.
# The drop is off here so the only thing that could press "i" is the feed.
cfg.auto_feed.food_key = "i"
cfg.drop.enabled = False
calls.clear()
refused = eng.MacroEngine(cfg)
levels: list[str] = []
refused.log.connect(lambda _m, level: levels.append(level))
refused.start()
pump(0.8)
refused.request_stop()
refused.wait(3000)
app.processEvents()
assert "err" in levels, "no error for a feed key that opens the inventory"
assert not any(c == ("key", hex(0x49)) for c in calls), \
    "the refused feed key was pressed anyway and opened the inventory"
assert sum(1 for c in calls if c[0] == "click") > 0, "it stopped farming too"
cfg.auto_feed.food_key = "4"
cfg.auto_feed.enabled = False
cfg.drop.enabled = True
print("OK  unusable feed slots are refused, and the farm carries on")

# ------------------------------------------------- 6) hotkey parsing
assert parse("F6")[1] == 0x75
assert parse("Ctrl+Shift+F6") == (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x75)
assert parse("Alt+D")[1] == 0x44
assert parse("") is None and parse("Ctrl") is None
print("OK  hotkey parsing")

# ------------------------------------------------- 7) HUD geometry
filter_point, drop_point = ark_layout.suggest(1920, 1080)
assert filter_point == [277, 193] and drop_point == [457, 193]
# windowed mode: the points travel with the window origin
windowed, _ = ark_layout.suggest(1920, 1080, (100, 50))
assert windowed == [377, 243], windowed
# rescaling stays anchored to the centre
assert ark_layout.rescale([277, 193], [1920, 1080], [1920, 1080]) == [277, 193]
assert ark_layout.rescale([277, 193], [1920, 1080], [2560, 1440]) == [369, 257]
print("OK  point estimation and rescaling")

# ------------------------------------------- 7b) hold-to-drop sweep path
# Every slot in the block has to be visited, which is why the path is a
# serpentine and not the circle it looks like on screen: a circle only touches
# its own ring and leaves every slot inside it untouched.
path = ark_sweep.serpentine([100, 200, 240, 200], 4, 4)
assert len(path) == 16, f"{len(path)} points for a 4x4 block"
assert len(set(path)) == 16, "the sweep visits a slot twice and misses another"
# rows alternate, so the cursor never jumps back across the grid
assert path[:4] == [(130, 225), (190, 225), (250, 225), (310, 225)], path[:4]
assert path[4:8] == [(310, 275), (250, 275), (190, 275), (130, 275)], path[4:8]
# consecutive points are one pitch apart — a longer step would cross a slot
# that is not part of the block, and while the drop key is held it would drop it
pitch = 240 / 4
for before, after in zip(path, path[1:]):
    step = max(abs(after[0] - before[0]), abs(after[1] - before[1]))
    assert step <= pitch + 1, f"the path jumps {step}px from {before}"

# every point lands inside the block, never on its border
for x, y in path:
    assert 100 < x < 340 and 200 < y < 400, (x, y)

# a drag in any direction gives the same rectangle
assert ark_sweep.normalise(340, 400, 100, 200) == [100, 200, 240, 200]
assert ark_sweep.normalise(100, 200, 340, 400) == [100, 200, 240, 200]

# a stray click is not a selection
assert ark_sweep.serpentine([0, 0, 10, 10], 4, 4) == []
assert not ark_sweep.usable([0, 0, 10, 10]) and ark_sweep.usable([0, 0, 240, 200])
assert not ark_sweep.usable("nonsense") and not ark_sweep.usable([1, 2])

# and the block scales with screen height, like everything else in the HUD
assert ark_sweep.rescale([100, 200, 240, 200], [1920, 1080],
                         [1920, 1080]) == [100, 200, 240, 200]
grown = ark_sweep.rescale([100, 200, 240, 200], [1920, 1080], [2560, 1440])
assert grown[2:] == [320, 267], grown
print(f"OK  the sweep visits all {len(path)} slots, in a serpentine")

# ------------------------------------------- 7c) skin overcap ping-pong
# One row, run end to end and back, so the cursor keeps passing over the strip.
strip = ark_sweep.pingpong([100, 900, 600, 80], 10)
# ten stops out, and the return leg skips both ends: they are the turning
# points, and stopping twice on the same spot only wastes a tick
assert len(strip) == 18, f"{len(strip)} stops in a lap of 10"
assert all(y == 940 for _x, y in strip), "the strip is not swept down its middle"
xs = [x for x, _y in strip]
assert xs[:10] == sorted(xs[:10]), "the outward leg is not left to right"
assert xs[10:] == sorted(xs[10:], reverse=True), "the return leg does not return"
assert xs[9] == max(xs) and xs[0] == min(xs), (xs[0], xs[9])
# looping it is continuous: the step from the last stop back to the first is
# the same as any other
assert xs[-1] - xs[0] == xs[1] - xs[0], "the loop back to the start jumps"
assert ark_sweep.pingpong([0, 0, 10, 10], 10) == []
print(f"OK  the strip sweep runs {len(strip)} stops out and back, and loops")

# ------------------------------------------------- 8) config migration
legacy = pathlib.Path(tempfile.gettempdir()) / "ark_macro_legacy.json"
legacy.write_text(json.dumps({
    "drop": {"keywords": ["thatch", "stone"]},
    "hotkeys": {"capture_point": "F10"},
}), encoding="utf-8")
migrated = Config.load(legacy)
assert migrated.drop.templates == [
    {"name": "Thatch", "keyword": "thatch", "enabled": True},
    {"name": "Stone", "keyword": "stone", "enabled": True},
], migrated.drop.templates
assert migrated.hotkeys.pick_points == "F10"
legacy.unlink()
print("OK  legacy config migration")

# --------------------------------- 8b) configs written before the close fix
stale = pathlib.Path(tempfile.gettempdir()) / "ark_macro_stale_close.json"
stale.write_text(json.dumps({
    "drop": {"close_with": "same", "trigger": "interval", "interval_s": 180},
}), encoding="utf-8")
upgraded = Config.load(stale)
assert upgraded.drop.close_with == "esc", upgraded.drop.close_with
assert upgraded.drop.close_presses == 2
assert upgraded.drop.trigger == "clicks" and upgraded.drop.every_clicks == 14
assert upgraded.drop.close_wait_ms == 2000, upgraded.drop.close_wait_ms

# the old click defaults follow too — nobody picked 600, or 12, on purpose
for old_count in (600, 12):
    stale.write_text(json.dumps({
        "drop": {"trigger": "clicks", "every_clicks": old_count,
                 "close_presses": 2},
    }), encoding="utf-8")
    assert Config.load(stale).drop.every_clicks == 14, old_count
stale.unlink()

# a timer that was actually chosen is left where it was put
kept = pathlib.Path(tempfile.gettempdir()) / "ark_macro_kept_timer.json"
kept.write_text(json.dumps({
    "drop": {"trigger": "interval", "interval_s": 90, "every_clicks": 400,
             "close_wait_ms": 1200},
}), encoding="utf-8")
survivor = Config.load(kept)
assert survivor.drop.trigger == "interval" and survivor.drop.every_clicks == 400
assert survivor.drop.close_wait_ms == 1200, "clobbered a chosen wait"
kept.unlink()
print("OK  an old config moves onto the double close and the click trigger")

# ------------------- 8c) hold-to-drop before the activation key existed
# "hold" used to mean holding the drop key itself; it means holding a separate
# activation key now. A config written before the split has to keep behaving
# the way its owner set it up, not silently start sending the drop key.
split = pathlib.Path(tempfile.gettempdir()) / "ark_macro_hold_split.json"
split.write_text(json.dumps({"hold_drop": {"mode": "hold", "key": "o"}}),
                 encoding="utf-8")
assert Config.load(split).hold_drop.mode == "manual"
# one that was already toggling was already having its drop key sent for it
split.write_text(json.dumps({"hold_drop": {"mode": "toggle"}}), encoding="utf-8")
assert Config.load(split).hold_drop.mode == "toggle"
# and a config written after the split is left alone
split.write_text(json.dumps({"hold_drop": {"mode": "hold",
                                           "activate_key": "f3"}}),
                 encoding="utf-8")
assert Config.load(split).hold_drop.mode == "hold"
split.unlink()
print("OK  a hold-to-drop config from before the split keeps its behaviour")

# ------------------------------------------------- 9) preset risk flags
assert presets.risk_of("stone")[0] == "high"
assert presets.risk_of("flint")[0] == "ok"
assert presets.risk_of("nonsense") == ("", "")
# nothing risky may ship enabled by default
assert not any(t["enabled"] for t in presets.default_templates()
               if presets.risk_of(t["keyword"])[0] == "high")
print("OK  preset risk flags")

# ------------------------------------------- 10) a hand-broken config is safe
broken = pathlib.Path(tempfile.gettempdir()) / "ark_macro_broken.json"
broken.write_text(json.dumps({
    "drop": {
        "filter_point": "nonsense",
        "dropall_point": [12],
        "points_resolution": None,
        "close_presses": 0,
        "templates": ["not a dict", {"keyword": "  "}, {"keyword": "thatch"},
                      {"name": "Stone", "keyword": "stone", "enabled": "yes"}],
    },
}), encoding="utf-8")
salvaged = Config.load(broken)
assert salvaged.drop.filter_point == [0, 0], salvaged.drop.filter_point
assert salvaged.drop.dropall_point == [0, 0], salvaged.drop.dropall_point
assert salvaged.drop.points_resolution == [0, 0]
# zero presses would leave the inventory open for the rest of the session
assert salvaged.drop.close_presses == 1, salvaged.drop.close_presses
assert salvaged.drop.templates == [
    {"name": "thatch", "keyword": "thatch", "enabled": False},
    {"name": "Stone", "keyword": "stone", "enabled": True},
], salvaged.drop.templates
# and the engine can run against it without blowing up on the bad points
recovered = eng.MacroEngine(salvaged)
recovered.log.connect(lambda _m, _l: None)
recovered._running = True
recovered._run_drop()   # refuses on empty points instead of raising
broken.unlink()
print("OK  a hand-broken config is coerced instead of crashing the engine")

# ------------------------------------------- 11) an empty list stays empty
empty = pathlib.Path(tempfile.gettempdir()) / "ark_macro_empty.json"
empty.write_text(json.dumps({"drop": {"templates": []}}), encoding="utf-8")
assert Config.load(empty).drop.templates == [], "defaults resurrected"
empty.unlink()
print("OK  clearing every template is respected on reload")

# ------------------------------------------- 12) saving is atomic
target = pathlib.Path(tempfile.gettempdir()) / "ark_macro_save.json"
target.write_text("{}", encoding="utf-8")
staged = target.with_name(target.name + ".tmp")
Config().save(target)
assert not staged.exists(), "the staging file was left behind"
assert Config.load(target).drop.templates, "saved config did not round-trip"
target.unlink()
print("OK  saving stages and renames, leaving no partial file")

# ------------------------------------------- 13) streaming latency allowance
timed = Config()
timed.target.require_focus = False
timed.drop.filter_point = [10, 10]
timed.drop.dropall_point = [20, 20]
timed.drop.templates = [{"name": "T", "keyword": "thatch", "enabled": True}]
for field_name in ("open_wait_ms", "close_wait_ms", "after_type_wait_ms",
                   "after_drop_wait_ms"):
    setattr(timed.drop, field_name, 0)

calls.clear()
native = eng.MacroEngine(timed)
native.log.connect(lambda _m, _l: None)
native._running = True
start = time.perf_counter()
native._run_drop()
baseline = time.perf_counter() - start

timed.target.stream_latency_ms = 120
streamed = eng.MacroEngine(timed)
streamed.log.connect(lambda _m, _l: None)
streamed._running = True
start = time.perf_counter()
streamed._run_drop()
with_stream = time.perf_counter() - start

# one pass has 8 waits — six, plus one after each of the two close presses —
# so the allowance should add roughly 8 * 120ms
added = with_stream - baseline
assert 0.85 <= added <= 1.30, f"latency allowance added {added:.2f}s"
print(f"OK  stream latency stretches every wait (+{added:.2f}s at 120ms)")

# ------------------------- 13b) background delivery cannot reach a stream
# The GeForce NOW client forwards real input from whatever has focus; a message
# posted to its window stops at the window. Arming anyway would pay every wait
# and send nothing into the game.
streamed_bg = Config()
streamed_bg.target.mode = "background"
streamed_bg.target.platform = "geforce_now"
streamed_bg.target.start_delay_s = 0
streamed_bg.drop.enabled = False
levels: list[str] = []
refuser = eng.MacroEngine(streamed_bg)
refuser.log.connect(lambda _m, level: levels.append(level))
calls.clear()
refuser.start()
refuser.wait(3000)
app.processEvents()
assert not calls, f"it sent input into a stream it cannot reach: {calls}"
assert "err" in levels, levels
print("OK  background delivery on GeForce NOW refuses to arm, loudly")

# ------------------------------------------- 14) letterboxed video area
assert ark_layout.video_area(0, 0, 1920, 1080) == (0, 0, 1920, 1080)
# 16:10 window -> bars top and bottom
assert ark_layout.video_area(100, 50, 1920, 1200) == (100, 110, 1920, 1080)
# ultrawide window -> bars left and right
assert ark_layout.video_area(0, 0, 2560, 1080) == (320, 0, 1920, 1080)
assert ark_layout.video_area(0, 0, 0, 0) == (0, 0, 0, 0)
print("OK  video area carves the picture out of the black bars")

print("\nALL TESTS PASSED")
