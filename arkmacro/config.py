"""Persisted configuration (JSON next to the project root)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .presets import default_templates

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class AutoClick:
    button: str = "left"           # left | right | middle
    cps_min: float = 6.0           # clicks per second, lower bound
    cps_max: float = 9.0           # clicks per second, upper bound
    hold_min_ms: int = 25          # how long the button stays down
    hold_max_ms: int = 55
    micro_pause_every: int = 0     # short break every N clicks (0 = off)
    micro_pause_ms: int = 400


@dataclass
class DropRoutine:
    enabled: bool = True
    trigger: str = "clicks"        # interval | clicks | manual
    interval_s: int = 180
    every_clicks: int = 14
    # clicks are not swings: a dino with an attack cooldown burns through the
    # count in seconds, so the pass also waits out a stretch of real farming
    min_farm_s: int = 20
    inventory_key: str = "i"
    close_with: str = "esc"        # same | esc
    # ARK's search field keeps the keyboard after the filter is typed, so the
    # first key press only leaves the field — the panel itself needs another
    close_presses: int = 2
    open_wait_ms: int = 1100
    # two seconds of hands off after the last press: the panel has to be gone
    # before the next swing, or the click lands in the inventory again
    close_wait_ms: int = 2000
    filter_point: list[int] = field(default_factory=lambda: [0, 0])
    dropall_point: list[int] = field(default_factory=lambda: [0, 0])
    # screen size when the points were captured, used to rescale them later
    points_resolution: list[int] = field(default_factory=lambda: [0, 0])
    # each template: {"name": str, "keyword": str, "enabled": bool}
    templates: list[dict] = field(default_factory=default_templates)
    after_type_wait_ms: int = 500   # let the filter settle
    after_drop_wait_ms: int = 450   # let the drop go through
    # read the search box before and after typing, and skip Drop All when the
    # keyword did not visibly land in it — an unfiltered Drop All empties the
    # entire inventory
    verify_filter: bool = True
    unicode_typing: bool = False
    # dry run: filter and screenshot, but never click Drop All
    dry_run: bool = False

    def active_templates(self) -> list[dict]:
        return [t for t in self.templates
                if t.get("enabled") and str(t.get("keyword", "")).strip()]


@dataclass
class Hotkeys:
    toggle: str = "F6"
    drop_now: str = "F7"
    panic: str = "F8"
    pick_points: str = "F9"


@dataclass
class Target:
    mode: str = "foreground"        # foreground | background
    platform: str = "native"        # native | geforce_now
    window_title: str = "ARK"       # fragment of the game window title
    require_focus: bool = True      # only click while the game is focused
    start_delay_s: float = 2.0      # grace period before the first click
    # streaming puts a round trip between every click and what you see, so
    # every wait in the drop routine gets this much extra
    stream_latency_ms: int = 0


@dataclass
class AntiAfk:
    """Keeps a streaming session from being dropped for inactivity."""

    enabled: bool = False
    interval_s: int = 60
    # F13-F24 exist in the keyboard protocol but not on real keyboards, so
    # nothing in ARK is bound to them and the tick cannot affect the game
    key: str = "f15"


@dataclass
class HoldDrop:
    """
    Sweeps the cursor across a block of slots while ARK's drop key is held.

    The app never presses the key — you hold it, the app moves the mouse. So the
    key here is only *watched*, never registered: a registered hotkey never
    reaches the game, and then nothing would drop.
    """

    enabled: bool = False
    key: str = "o"                  # ARK's drop key: the instruction
    activate_key: str = "f3"        # yours, to start and stop the macro
    # toggle -> press the activation key to start, again to stop. Hands free,
    #           and the macro taps the drop key once per slot
    # hold   -> the same, but only while the activation key is held
    # manual -> no activation key: you hold the drop key itself, and the app
    #           sends nothing because your finger is already the instruction
    mode: str = "toggle"
    area: list[int] = field(default_factory=lambda: [0, 0, 0, 0])  # x,y,w,h
    # screen size when the area was selected, used to rescale it later
    area_resolution: list[int] = field(default_factory=lambda: [0, 0])
    columns: int = 6
    rows: int = 5
    # how long the cursor rests on each slot. Too low and the game misses the
    # hover; on a streamed session it has to cover a round trip
    dwell_ms: int = 40


@dataclass
class SkinOvercap:
    """
    Runs the cursor along a strip with Shift + a hotbar key held down.

    Two different keys, and they must not be confused. `activate_key` is the one
    you press: it belongs to the app and does nothing in the game. Shift and
    `key` are the instruction — the chord the macro itself holds while it
    sweeps, so your hands are free.
    """

    enabled: bool = False
    activate_key: str = "f4"        # yours, to start and stop the macro
    # hold   -> runs while you hold the activation key
    # toggle -> one press starts it, another stops it
    mode: str = "toggle"
    key: str = "2"                  # the hotbar slot the macro holds with Shift
    area: list[int] = field(default_factory=lambda: [0, 0, 0, 0])  # x,y,w,h
    area_resolution: list[int] = field(default_factory=lambda: [0, 0])
    stops: int = 10                 # points across the strip, one per hotbar slot
    dwell_ms: int = 40


@dataclass
class AutoFeed:
    """
    Eats and drinks from the hotbar on a timer, while farming.

    Two slots, because food and water are two items. The keys are hotbar slots
    (1-0) rather than free text: a stray letter here would be a key bound to
    something in ARK, and a stray "i" would open the inventory mid-farm.
    """

    enabled: bool = False
    interval_s: int = 360           # every 6 minutes
    food_key: str = "4"
    water_key: str = "5"
    # between the two presses, so the game does not fold them into one
    gap_ms: int = 350


@dataclass
class StopSign:
    """
    Watches one small patch of screen and stops the macro when it changes to a
    remembered picture.

    An icon appearing is the game saying something that no amount of clicking
    will fix — a broken tool, an encumbered character, a dead dino. The macro
    cannot read the game, but it can be shown the icon once and told to look for
    it. When it sees it, it stops exactly as if the toggle hotkey had been
    pressed, because that is what you would have done.

    `sample` is the remembered picture: a grid of colours read from `area` at
    capture time. Matching is a count of samples still within tolerance, not an
    exact image compare, because a streamed picture never repeats a frame
    exactly and an icon drawn over a moving world never sits on the same
    background twice.
    """

    enabled: bool = False
    area: list[int] = field(default_factory=lambda: [0, 0, 0, 0])   # x,y,w,h
    area_resolution: list[int] = field(default_factory=lambda: [0, 0])
    sample: list[list[int]] = field(default_factory=list)           # [[r,g,b], ...]
    # per-channel slack on one sample. Generous on purpose: video compression
    # moves flat colour around by more than you would think.
    tolerance: int = 34
    # how much of the grid has to still match, as a percentage. Not 100: the icon
    # sits on whatever the world is doing behind it, and its edges bleed.
    match_percent: int = 78
    # how often to look while farming. Cheap — one small blit — but not free.
    poll_ms: int = 400


@dataclass
class App:
    check_updates_on_start: bool = True
    # pull and restart without being asked, so a new commit reaches the running
    # app on its own. Held back while the macro is farming — a restart mid-pass
    # would drop the session on the floor.
    #
    # On by default, which is a real choice: it means whatever is pushed is what
    # you farm with, with no review step. The alternative was a switch nobody
    # can reach without first applying an update by hand.
    auto_update: bool = True


@dataclass
class Config:
    autoclick: AutoClick = field(default_factory=AutoClick)
    drop: DropRoutine = field(default_factory=DropRoutine)
    hotkeys: Hotkeys = field(default_factory=Hotkeys)
    target: Target = field(default_factory=Target)
    anti_afk: AntiAfk = field(default_factory=AntiAfk)
    auto_feed: AutoFeed = field(default_factory=AutoFeed)
    hold_drop: HoldDrop = field(default_factory=HoldDrop)
    skin_overcap: SkinOvercap = field(default_factory=SkinOvercap)
    stop_sign: StopSign = field(default_factory=StopSign)
    app: App = field(default_factory=App)

    # -------------------------------------------------------------- io
    # `path` resolves at call time on purpose: a default argument would freeze
    # CONFIG_PATH at import and silently ignore any override.
    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = Path(path) if path else CONFIG_PATH
        cfg = cls()
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                _merge(cfg, raw)
                _migrate(cfg, raw)
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass  # corrupted file -> fall back to defaults
        _sanitize(cfg)
        return cfg

    def save(self, path: Path | None = None) -> None:
        # write beside the target and rename: a crash mid-write would otherwise
        # leave a truncated config that loses every setting
        path = Path(path) if path else CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name(path.name + ".tmp")
        staged.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        staged.replace(path)


def _migrate(cfg: "Config", raw: dict) -> None:
    """Bring a file written by an older version onto the current shape."""
    drop = raw.get("drop") or {}
    if not isinstance(drop, dict):
        drop = {}
    # a single close key never actually closed anything: the search field ate
    # it and the macro carried on clicking inside the open inventory. Configs
    # written before the fix are moved onto the two-press default.
    if "close_presses" not in drop:
        cfg.drop.close_with = "esc"
        cfg.drop.close_presses = 2
        # a trigger still sitting on the old defaults follows the new one;
        # anything that was actually chosen stays where it was put
        untouched = (drop.get("trigger", "interval") == "interval"
                     and drop.get("interval_s", 180) == 180)
        if untouched:
            cfg.drop.trigger = "clicks"
        if untouched or (drop.get("trigger") == "clicks"
                         and drop.get("every_clicks", 600) == 600):
            cfg.drop.every_clicks = 14

    # a pass that was still resuming after 700 ms was clicking into a panel
    # that had not gone away yet, and fourteen clicks read better than twelve
    if "min_farm_s" not in drop:
        if drop.get("every_clicks", 600) in (12, 600):
            cfg.drop.every_clicks = 14
        if drop.get("close_wait_ms", 700) == 700:
            cfg.drop.close_wait_ms = 2000

    # hold-to-drop used to have no activation key, so its "hold" meant holding
    # the drop key itself. That is "manual" now, and a config written before the
    # split has to keep behaving the way its owner set it up.
    held = raw.get("hold_drop")
    if isinstance(held, dict) and "activate_key" not in held:
        if held.get("mode", "hold") == "hold":
            cfg.hold_drop.mode = "manual"

    legacy = drop.get("keywords")
    if legacy and "templates" not in drop:
        cfg.drop.templates = [
            {"name": str(word).strip().capitalize(), "keyword": str(word).strip(),
             "enabled": True}
            for word in legacy if str(word).strip()
        ]
    # the capture hotkey was renamed
    old_hotkey = (raw.get("hotkeys") or {}).get("capture_point")
    if old_hotkey and "pick_points" not in (raw.get("hotkeys") or {}):
        cfg.hotkeys.pick_points = old_hotkey


def _point(value: Any) -> list[int]:
    """Coerce whatever is in the file into a usable [x, y]."""
    try:
        return [int(value[0]), int(value[1])]
    except (TypeError, ValueError, IndexError, KeyError):
        return [0, 0]


def _rect(value: Any) -> list[int]:
    """Coerce whatever is in the file into a usable [x, y, width, height]."""
    try:
        rect = [int(value[0]), int(value[1]), int(value[2]), int(value[3])]
    except (TypeError, ValueError, IndexError, KeyError):
        return [0, 0, 0, 0]
    # a negative size would run the sweep backwards out of the panel
    return rect if rect[2] >= 0 and rect[3] >= 0 else [0, 0, 0, 0]


def _count(value: Any, fallback: int, low: int, high: int) -> int:
    """Clamp a hand-edited number into the range the engine can act on."""
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return fallback


def _template(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    keyword = str(value.get("keyword", "")).strip()
    if not keyword:
        return None
    return {"name": str(value.get("name") or keyword).strip(),
            "keyword": keyword,
            "enabled": bool(value.get("enabled"))}


def _sanitize(cfg: "Config") -> None:
    """
    Make a hand-edited config safe to run.

    The engine indexes straight into these, on its own thread — a string where
    a point should be would blow up mid-farm instead of at load time.
    """
    drop = cfg.drop
    drop.filter_point = _point(drop.filter_point)
    drop.dropall_point = _point(drop.dropall_point)
    drop.points_resolution = _point(drop.points_resolution)
    # zero presses would leave the inventory open for the rest of the session
    drop.close_presses = _count(drop.close_presses, 2, 1, 5)
    drop.min_farm_s = _count(drop.min_farm_s, 20, 0, 3600)
    # anything that is not plainly off leaves the check on: the failure it
    # guards against costs the whole inventory
    drop.verify_filter = bool(drop.verify_filter)

    # Background delivery is not a mode any more. It posted messages instead of
    # sending real input, which Unreal drops and a streaming client never
    # forwards, and it switched off every check that reads the screen — so a
    # config left on it farmed nothing and refused every drop. A stored one is
    # moved rather than honoured; the app says so, and the engine refuses to arm
    # if a hand-edited file puts it back.
    cfg.target.mode = ("background"
                       if str(cfg.target.mode).strip().lower() == "background"
                       else "foreground")

    feed = cfg.auto_feed
    # a 5 s feed timer would spend the session eating; a hand-edited one is
    # clamped rather than trusted
    feed.interval_s = _count(feed.interval_s, 360, 30, 7200)
    feed.gap_ms = _count(feed.gap_ms, 350, 50, 3000)
    feed.food_key = str(feed.food_key).strip().lower()
    feed.water_key = str(feed.water_key).strip().lower()

    hold = cfg.hold_drop
    hold.area = _rect(hold.area)
    hold.area_resolution = _point(hold.area_resolution)
    # a 40x40 grid would be 1600 slots of nothing; ARK's panels are far smaller
    hold.columns = _count(hold.columns, 6, 1, 20)
    hold.rows = _count(hold.rows, 5, 1, 20)
    hold.dwell_ms = _count(hold.dwell_ms, 40, 5, 1000)
    hold.key = str(hold.key).strip().lower()
    hold.activate_key = str(hold.activate_key).strip().lower()
    # anything unrecognised falls back to manual, the mode where the app sends
    # no keys of its own
    mode = str(hold.mode).strip().lower()
    hold.mode = mode if mode in ("toggle", "hold", "manual") else "manual"

    skin = cfg.skin_overcap
    skin.area = _rect(skin.area)
    skin.area_resolution = _point(skin.area_resolution)
    # two stops is a strip with only its ends; below that there is no sweep
    skin.stops = _count(skin.stops, 10, 2, 40)
    skin.dwell_ms = _count(skin.dwell_ms, 40, 5, 1000)
    skin.key = str(skin.key).strip().lower()
    skin.activate_key = str(skin.activate_key).strip().lower()
    skin.mode = ("hold" if str(skin.mode).strip().lower() == "hold"
                 else "toggle")
    stop = cfg.stop_sign
    stop.area = _rect(stop.area)
    stop.area_resolution = _point(stop.area_resolution)
    stop.tolerance = _count(stop.tolerance, 34, 4, 90)
    stop.match_percent = _count(stop.match_percent, 78, 40, 100)
    stop.poll_ms = _count(stop.poll_ms, 400, 100, 5000)
    # A remembered picture is a list of RGB triples and nothing else. Anything
    # that is not one is dropped rather than repaired: a half-read sample would
    # compare against the wrong points and stop the macro on nothing.
    if isinstance(stop.sample, list):
        clean = []
        for colour in stop.sample:
            if (isinstance(colour, (list, tuple)) and len(colour) == 3
                    and all(isinstance(c, int) and 0 <= c <= 255 for c in colour)):
                clean.append(list(colour))
            else:
                clean = []
                break
        stop.sample = clean
    else:
        stop.sample = []

    if isinstance(drop.templates, list):
        # an empty list is a real choice, so it is kept as-is
        drop.templates = [t for t in (_template(item) for item in drop.templates)
                          if t]
    else:
        drop.templates = default_templates()


def _merge(obj: Any, raw: dict) -> None:
    """Apply a dict onto the dataclass, ignoring unknown keys."""
    if not isinstance(raw, dict):
        return
    for spec in fields(obj):
        if spec.name not in raw:
            continue
        current = getattr(obj, spec.name)
        value = raw[spec.name]
        if is_dataclass(current):
            _merge(current, value)
        else:
            setattr(obj, spec.name, value)
