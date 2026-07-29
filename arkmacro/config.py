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
    clear_backspaces: int = 24
    after_type_wait_ms: int = 500   # let the filter settle
    after_drop_wait_ms: int = 450   # let the drop go through
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
class App:
    check_updates_on_start: bool = True


@dataclass
class Config:
    autoclick: AutoClick = field(default_factory=AutoClick)
    drop: DropRoutine = field(default_factory=DropRoutine)
    hotkeys: Hotkeys = field(default_factory=Hotkeys)
    target: Target = field(default_factory=Target)
    anti_afk: AntiAfk = field(default_factory=AntiAfk)
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
