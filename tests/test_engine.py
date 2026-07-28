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
    ("key", hex(0x49)),                 # close the inventory
]
assert calls == expected, f"\nexpected:\n{expected}\ngot:\n{calls}"
assert not any(c == ("type", "wood") for c in calls), \
    "an unchecked template must not enter the cycle"
print(f"OK  drop pass order ({len(calls)} actions, unchecked one skipped)")

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
        "templates": ["not a dict", {"keyword": "  "}, {"keyword": "thatch"},
                      {"name": "Stone", "keyword": "stone", "enabled": "yes"}],
    },
}), encoding="utf-8")
salvaged = Config.load(broken)
assert salvaged.drop.filter_point == [0, 0], salvaged.drop.filter_point
assert salvaged.drop.dropall_point == [0, 0], salvaged.drop.dropall_point
assert salvaged.drop.points_resolution == [0, 0]
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

# one pass has 6 waits, so the allowance should add roughly 6 * 120ms
added = with_stream - baseline
assert 0.55 <= added <= 0.95, f"latency allowance added {added:.2f}s"
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
