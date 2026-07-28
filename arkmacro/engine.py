"""
Macro engine: one worker thread alternating between two states.

  FARM  -> continuous autoclick, jittered so it is not metronomic
  DROP  -> open the inventory, filter by keyword, hit Drop All for every
           enabled template, clear the filter, close, resume farming

The drop pass fires on a timer, on a click count, or on demand via hotkey.
"""
from __future__ import annotations

import random
import time

from PySide6.QtCore import QObject, QThread, Signal

from . import winapi as w
from .config import Config


class MacroEngine(QThread):
    log = Signal(str, str)            # message, level (info|ok|warn|err)
    state_changed = Signal(str)       # idle | farming | dropping | waiting
    stats_changed = Signal(int, int)  # clicks, completed drop passes
    shot_requested = Signal(str)      # dry run: capture the filtered screen

    def __init__(self, cfg: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._running = False
        self._drop_requested = False
        self.clicks = 0
        self.drops = 0
        self._hwnd: int | None = None

    # --------------------------------------------------------------- api
    def request_stop(self) -> None:
        self._running = False

    def request_drop(self) -> None:
        self._drop_requested = True

    # ----------------------------------------------------------- helpers
    def _wait(self, milliseconds: int) -> bool:
        """A drop-routine wait, plus the streaming round trip if there is one."""
        return self._sleep((milliseconds + self.cfg.target.stream_latency_ms)
                           / 1000.0)

    def _sleep(self, seconds: float) -> bool:
        """Sleep in slices. Returns False if a stop was requested midway."""
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            if not self._running:
                return False
            time.sleep(min(0.02, max(end - time.perf_counter(), 0)))
        return self._running

    def _resolve_window(self) -> bool:
        """(Re)find the game window; handles the game being restarted."""
        if self._hwnd and w.is_window(self._hwnd):
            return True
        self._hwnd = w.find_window(self.cfg.target.window_title)
        return bool(self._hwnd)

    def _focus_ok(self) -> tuple[bool, str]:
        """(can act now, reason when it cannot)."""
        if self.cfg.target.mode == "background":
            return (True, "") if self._resolve_window() else (False, "no window")
        if not self.cfg.target.require_focus:
            return True, ""
        if not self._resolve_window():
            return False, "no window"
        return (True, "") if w.is_foreground(self._hwnd) else (False, "unfocused")

    # -------------------------------------------------------- input acts
    def _click(self, button: str) -> None:
        hold = random.uniform(self.cfg.autoclick.hold_min_ms,
                              self.cfg.autoclick.hold_max_ms) / 1000.0
        if self.cfg.target.mode == "background" and self._hwnd:
            # aim at the crosshair, i.e. the middle of the client area
            rect = w.client_rect(self._hwnd)
            cx, cy = (rect[2] // 2, rect[3] // 2) if rect else (0, 0)
            w.post_click(self._hwnd, cx, cy, button, hold)
        else:
            w.click(button, hold)

    def _click_point(self, point: list[int], label: str) -> None:
        x, y = int(point[0]), int(point[1])
        if self.cfg.target.mode == "background" and self._hwnd:
            cx, cy = w.screen_to_client(self._hwnd, x, y)
            w.post_click(self._hwnd, cx, cy, "left", 0.04)
        else:
            w.click_at(x, y, "left", hold=0.05, settle=0.08)
        self.log.emit(f"clicked {label} at ({x}, {y})", "info")

    def _tap_key(self, name: str) -> None:
        vk = w.vk_from_name(name)
        if vk is None:
            self.log.emit(f"unknown key: {name}", "err")
            return
        if self.cfg.target.mode == "background" and self._hwnd:
            w.post_key(self._hwnd, vk, 0.04)
        else:
            w.tap(vk, hold=0.05)

    def _type(self, text: str) -> None:
        if self.cfg.target.mode == "background" and self._hwnd:
            w.post_text(self._hwnd, text, delay=0.03)
        else:
            w.type_text(text, delay=0.05,
                        unicode_mode=self.cfg.drop.unicode_typing)

    def _backspaces(self, count: int) -> None:
        vk = w.vk_from_name("backspace")
        for _ in range(count):
            if not self._running:
                return
            if self.cfg.target.mode == "background" and self._hwnd:
                w.post_key(self._hwnd, vk, 0.01)
            else:
                w.tap(vk, hold=0.015)
            time.sleep(0.02)

    # ------------------------------------------------------- drop routine
    def _run_drop(self) -> None:
        d = self.cfg.drop
        if not any(d.filter_point) or (not d.dry_run and not any(d.dropall_point)):
            self.log.emit("drop pass cancelled: capture the filter and Drop All "
                          "points on the Points tab first", "err")
            return

        templates = d.active_templates()
        if not templates:
            self.log.emit("no template checked on the Templates tab", "warn")
            return

        self.state_changed.emit("dropping")
        names = ", ".join(str(t.get("name") or t["keyword"]) for t in templates)
        self.log.emit(f"--- drop pass: {names} ---", "warn")
        if d.dry_run:
            self.log.emit("DRY RUN on — filtering and capturing, no Drop All "
                          "click", "warn")

        # 1) open the inventory
        self._tap_key(d.inventory_key)
        if not self._wait(d.open_wait_ms):
            return

        for template in templates:
            if not self._running:
                return
            keyword = str(template["keyword"]).strip()

            # 2) focus the filter field and wipe whatever was there
            self._click_point(d.filter_point, "filter field")
            if not self._wait(200):
                return
            self._backspaces(d.clear_backspaces)

            # 3) type the keyword and let the list settle
            self._type(keyword)
            self.log.emit(f'filtering "{keyword}"', "info")
            if not self._wait(d.after_type_wait_ms):
                return

            # 4) Drop All — with the filter on, only what is listed falls
            if d.dry_run:
                self.shot_requested.emit(keyword)
                self.log.emit(f'dry run: captured "{keyword}", Drop All not '
                              "clicked", "warn")
                if not self._sleep(0.6):
                    return
            else:
                self._click_point(d.dropall_point, "Drop All")
                if not self._wait(d.after_drop_wait_ms):
                    return

        # 5) clear the filter so the inventory is not left masked
        self._click_point(d.filter_point, "filter field")
        if not self._wait(200):
            return
        self._backspaces(d.clear_backspaces)

        # 6) close the inventory
        if not self._wait(250):
            return
        self._tap_key("esc" if d.close_with == "esc" else d.inventory_key)
        if not self._wait(d.close_wait_ms):
            return

        self.drops += 1
        self.stats_changed.emit(self.clicks, self.drops)
        self.log.emit("--- drop pass done, back to farming ---", "ok")

    # ----------------------------------------------------------- main loop
    def run(self) -> None:
        self._running = True
        self.clicks = 0
        self.drops = 0
        self._drop_requested = False
        cfg = self.cfg

        if not self._resolve_window():
            title = cfg.target.window_title
            if cfg.target.mode == "background":
                self.log.emit(f'window "{title}" not found — background mode '
                              "needs it", "err")
                self.state_changed.emit("idle")
                self._running = False
                return
            if cfg.target.require_focus:
                self.log.emit(f'window "{title}" not found — waiting for it',
                              "warn")

        if cfg.target.start_delay_s > 0:
            self.state_changed.emit("waiting")
            self.log.emit(f"starting in {cfg.target.start_delay_s:g}s — "
                          "bring ARK to the front", "warn")
            if not self._sleep(cfg.target.start_delay_s):
                self.state_changed.emit("idle")
                return

        self.state_changed.emit("farming")
        self.log.emit("macro armed", "ok")

        last_drop = time.perf_counter()
        clicks_since_drop = 0
        paused_reason = ""

        while self._running:
            d = cfg.drop
            due = False
            if self._drop_requested:
                due = True
                self._drop_requested = False
            elif d.enabled:
                if d.trigger == "interval":
                    due = (time.perf_counter() - last_drop) >= d.interval_s
                elif d.trigger == "clicks":
                    due = clicks_since_drop >= max(d.every_clicks, 1)

            ready, reason = self._focus_ok()

            if due:
                if ready:
                    self._run_drop()
                    last_drop = time.perf_counter()
                    clicks_since_drop = 0
                    if not self._running:
                        break
                    self.state_changed.emit("farming")
                else:
                    self._drop_requested = True  # retry once we can act

            if not ready:
                if paused_reason != reason:
                    paused_reason = reason
                    self.state_changed.emit("waiting")
                    self.log.emit(
                        f'window "{cfg.target.window_title}" not found — paused'
                        if reason == "no window" else "ARK lost focus — paused",
                        "warn")
                time.sleep(0.2)
                continue
            if paused_reason:
                paused_reason = ""
                self.log.emit("target back — resuming", "ok")
                self.state_changed.emit("farming")

            # autoclick
            started = time.perf_counter()
            self._click(cfg.autoclick.button)
            self.clicks += 1
            clicks_since_drop += 1
            if self.clicks % 10 == 0:
                self.stats_changed.emit(self.clicks, self.drops)

            ac = cfg.autoclick
            if ac.micro_pause_every and self.clicks % ac.micro_pause_every == 0:
                self._sleep(ac.micro_pause_ms / 1000.0 * random.uniform(0.8, 1.3))
                started = time.perf_counter()

            # the hold time counts towards the period, otherwise the real cps
            # lands well below what was configured
            cps = random.uniform(min(ac.cps_min, ac.cps_max),
                                 max(ac.cps_min, ac.cps_max))
            interval = 1.0 / max(cps, 0.1)
            self._sleep(max(interval - (time.perf_counter() - started), 0.002))

        self.stats_changed.emit(self.clicks, self.drops)
        self.state_changed.emit("idle")
        self.log.emit("macro stopped", "warn")
