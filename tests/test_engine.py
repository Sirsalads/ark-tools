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

    VK = {"i": 0x49, "esc": 0x1B, "backspace": 0x08}

    @staticmethod
    def vk_from_name(name):
        return FakeW.VK.get(name, 0x41)

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
cfg.drop.clear_backspaces = 3
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
    ("key", hex(0x49)),                 # open the inventory
    ("click_at", 960, 300),             # focus the filter field
    *[("key", hex(0x08))] * 3,          # wipe the previous text
    ("type", "thatch"),                 # type the keyword
    ("click_at", 1400, 900),            # Drop All
    ("click_at", 960, 300),
    *[("key", hex(0x08))] * 3,
    ("type", "stone"),
    ("click_at", 1400, 900),
    ("click_at", 960, 300),             # clear the filter at the end
    *[("key", hex(0x08))] * 3,
    ("key", hex(0x1B)),                 # Esc leaves the search field
    ("key", hex(0x1B)),                 # and only then closes the inventory
]
assert calls == expected, f"\nexpected:\n{expected}\ngot:\n{calls}"
assert not any(c == ("type", "wood") for c in calls), \
    "an unchecked template must not enter the cycle"
print(f"OK  drop pass order ({len(calls)} actions, unchecked one skipped)")

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
    try:
        calls.clear()
        probe_engine = eng.MacroEngine(cfg)
        probe_engine.log.connect(lambda _m, _l: None)
        probe_engine._running = True
        probe_engine._run_drop()
    finally:
        FakeW.tap, FakeW.screen_pixel = original_tap, original_pixel
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
pump(1.4)
timer_engine.request_stop()
timer_engine.wait(3000)
assert any(c == ("click_at", 1400, 900) for c in calls), "timer trigger failed"
print("OK  timer trigger")

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
timed.drop.clear_backspaces = 0
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

# one pass has 9 waits — seven, plus one after each of the two close presses —
# so the allowance should add roughly 9 * 120ms
added = with_stream - baseline
assert 0.85 <= added <= 1.30, f"latency allowance added {added:.2f}s"
print(f"OK  stream latency stretches every wait (+{added:.2f}s at 120ms)")

# ------------------------------------------- 14) letterboxed video area
assert ark_layout.video_area(0, 0, 1920, 1080) == (0, 0, 1920, 1080)
# 16:10 window -> bars top and bottom
assert ark_layout.video_area(100, 50, 1920, 1200) == (100, 110, 1920, 1080)
# ultrawide window -> bars left and right
assert ark_layout.video_area(0, 0, 2560, 1080) == (320, 0, 1920, 1080)
assert ark_layout.video_area(0, 0, 0, 0) == (0, 0, 0, 0)
print("OK  video area carves the picture out of the black bars")

print("\nALL TESTS PASSED")
