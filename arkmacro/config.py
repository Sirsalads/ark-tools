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
    trigger: str = "interval"      # interval | clicks | manual
    interval_s: int = 180
    every_clicks: int = 600
    inventory_key: str = "i"
    close_with: str = "same"       # same | esc
    open_wait_ms: int = 1100
    close_wait_ms: int = 700
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
    window_title: str = "ARK"       # fragment of the game window title
    require_focus: bool = True      # only click while the game is focused
    start_delay_s: float = 2.0      # grace period before the first click


@dataclass
class Config:
    autoclick: AutoClick = field(default_factory=AutoClick)
    drop: DropRoutine = field(default_factory=DropRoutine)
    hotkeys: Hotkeys = field(default_factory=Hotkeys)
    target: Target = field(default_factory=Target)

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
            except (json.JSONDecodeError, OSError, TypeError):
                pass  # corrupted file -> fall back to defaults
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = Path(path) if path else CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _migrate(cfg: "Config", raw: dict) -> None:
    """Turn the flat keyword list of older versions into templates."""
    drop = raw.get("drop") or {}
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
