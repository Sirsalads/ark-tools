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

from . import stopsign
from . import sweep
from . import winapi as w
from .config import Config

# after a close press: long enough for the panel to be gone before the screen
# is read, and for the game not to fold two presses into one keystroke
CLOSE_GAP_MS = 400
# the close presses are held longer than a normal tap — a 50 ms Esc is easy for
# the game to miss on the frame it is redrawing the panel
CLOSE_HOLD = 0.09
# never sit in the close loop forever; each attempt costs CLOSE_GAP_MS
CLOSE_ATTEMPTS = 4
# Where to look to tell an open inventory from a closed one: fractions along the
# line from the filter field to Drop All, which crosses the panel's icon row.
# Both ends are avoided — the cursor rests on the filter field and a tooltip
# there would sit on top of the very pixels being read.
PANEL_PROBES = (0.25, 0.4, 0.5, 0.6, 0.75)
# the panel is flat UI, but video streaming and dithering move a channel or two
PROBE_TOLERANCE = 16
# how far apart the two points have to be before the probes mean anything
PROBE_MIN_SPAN = 40

# The panel has to be up before a single key is typed. A fixed wait cannot
# promise that: under lag the inventory can still be coming up when the wait
# expires, and then the filter click, the keyword and the Drop All click all go
# out against whatever is on screen instead. So the wait is a floor and the
# screen is what says when to go on.
PANEL_SETTLE_POLL_MS = 60
PANEL_OPEN_BUDGET_MS = 2500
# consecutive readings that have to stop looking like the world before the panel
# counts as up — one is a flicker, three is 180ms of inventory
PANEL_OPEN_CONFIRMATIONS = 3

# Reading the search box, to tell an empty one from one holding a keyword.
# The box is sampled on a horizontal band around the filter point: how wide is
# derived from the distance to Drop All, which is the only ruler there is for
# how large the HUD is drawn on this screen.
FILTER_PROBE_REACH = 0.3          # of the filter -> Drop All distance, each way
FILTER_PROBE_STEPS = 15           # samples across the band
FILTER_PROBE_ROWS = (-4, 0, 4)    # and on three rows, to catch the glyph bodies
# A typed keyword moves a FEW of those samples. That is the whole signature, and
# both ends of it are load-bearing.
#
# Too few is nothing typed — one or two is the caret, which blinks and sits
# exactly where the first letter goes. Too many is not a keyword at all: it is
# the panel arriving between the two readings, which repaints every sample while
# the search box is still empty. Requiring a count inside a band says yes to a
# word and no to both failures, and it does it sample by sample, so a band that
# runs off the search box onto the panel behind it still works — those samples
# simply never change and never vote.
FILTER_CHANGED_MIN = 3
FILTER_CHANGED_MAX = 0.70         # of the samples; above this the scene changed
# A wipe of the search box. The game clears the filter itself when Drop All
# fires, so this is only for the boxes it has not cleared: the first template of
# a pass (a human may have left something in there), a dry run, and the template
# after a drop that was skipped. Longer than any sane keyword.
CLEAR_KEYS = 24



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

    def _tap_key(self, name: str, hold: float = 0.05) -> None:
        vk = w.vk_from_name(name)
        if vk is None:
            self.log.emit(f"unknown key: {name}", "err")
            return
        if self.cfg.target.mode == "background" and self._hwnd:
            w.post_key(self._hwnd, vk, hold)
        else:
            w.tap(vk, hold=hold)

    def _type(self, text: str) -> None:
        if self.cfg.target.mode == "background" and self._hwnd:
            w.post_text(self._hwnd, text, delay=0.03)
        else:
            w.type_text(text, delay=0.05,
                        unicode_mode=self.cfg.drop.unicode_typing)

    def _clear_field(self, count: int = CLEAR_KEYS) -> None:
        vk = w.vk_from_name("backspace")
        for _ in range(count):
            if not self._running:
                return
            if self.cfg.target.mode == "background" and self._hwnd:
                w.post_key(self._hwnd, vk, 0.01)
            else:
                w.tap(vk, hold=0.015)
            time.sleep(0.02)

    # ------------------------------------------- did the keyword get in there
    def _read(self, points) -> list[tuple[int, int, int]] | None:
        """
        Colours at those screen points, from wherever the game actually is.

        Foreground reads the screen, which is the game, because it is in front.
        Background cannot: those coordinates belong to whatever IS in front, and
        for a long time this simply gave up there — which switched off the check
        that holds back an unverified Drop All, the panel wait and the stop sign,
        all three, silently. Someone farming an installed ARK in the background
        while using GeForce NOW in front got a session where every drop pass
        refused for want of a readable screen, and the setting was doing exactly
        what it was written to do.

        A window can be asked to paint itself no matter who has focus, so that
        is what background does now. The points stay screen coordinates — they
        go through the window's current position, the same way the posted clicks
        already do.
        """
        if self.cfg.target.mode != "background":
            return w.screen_samples(points)
        if not self._resolve_window():
            return None
        return w.window_samples(self._hwnd, points)

    def _probe_filter(self) -> list[tuple[int, int, int]] | None:
        """
        Colours across the search box, or None when it cannot be read.

        Read twice — before and after typing — these say whether anything
        actually landed in the box.

        The band is wider than the search box on most HUDs, because its width
        comes from the distance to Drop All and not from the box. That is fine
        and deliberate: the reading is compared sample against itself, so the
        ones that landed on the panel instead of the box hold still and take no
        part in the answer. The mouse cursor is parked on the filter point for
        both readings for the same reason — whatever it covers, it covers
        identically twice.
        """
        d = self.cfg.drop
        start, end = d.filter_point, d.dropall_point
        span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
        if not any(start) or not any(end) or span < PROBE_MIN_SPAN:
            return None
        reach = max(round(span * FILTER_PROBE_REACH), 12)
        spots = [
            (round(start[0] - reach + 2 * reach * step / (FILTER_PROBE_STEPS - 1)),
             start[1] + row)
            for row in FILTER_PROBE_ROWS
            for step in range(FILTER_PROBE_STEPS)
        ]
        return self._read(spots)

    @staticmethod
    def _moved(before, after) -> int:
        """How many samples changed colour between two readings of the band."""
        return sum(1 for a, b in zip(before, after)
                   if any(abs(x - y) > PROBE_TOLERANCE for x, y in zip(a, b)))

    @staticmethod
    def _word_range(count: int) -> tuple[int, int]:
        """How many moved samples count as a keyword, for a band of `count`."""
        return FILTER_CHANGED_MIN, max(FILTER_CHANGED_MIN,
                                       round(count * FILTER_CHANGED_MAX))

    def _unreadable_reason(self) -> str:
        """
        Why the screen cannot be read, as far as this can actually be told.

        The old message asserted exclusive fullscreen. It was a guess dressed as
        a finding, and on a streamed session it was simply wrong — the screen was
        readable and the app was using a call that cannot see a streaming
        client's picture. Guessing loudly sent someone looking at the one setting
        that was not the problem, so this only says what it knows.
        """
        d = self.cfg.drop
        start, end = d.filter_point, d.dropall_point
        if not any(start) or not any(end):
            return "the filter and Drop All points are not both captured"
        if self.cfg.target.mode == "background":
            if not self._resolve_window():
                return (f'no window called "{self.cfg.target.window_title}" — '
                        "background delivery reads the game's own window, so it "
                        "has to find it first")
            return ("the game's window will not paint itself for the app. That "
                    "is exclusive fullscreen, or a driver overlay — run ARK "
                    "BORDERLESS and it can be read from behind. Foreground "
                    "delivery would also work, at the cost of the window "
                    "having to be in front")
        span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
        if span < PROBE_MIN_SPAN:
            return (f"the two captured points are only {span}px apart, too close "
                    "to measure the panel with — recapture them")
        if w.screen_pixel(*start) is None:
            return ("Windows hands back nothing for that pixel. ARK in "
                    "EXCLUSIVE FULLSCREEN does this — try borderless")
        return (f"the points read fine on their own but the strip between "
                f"({start[0]}, {start[1]}) and ({end[0]}, {end[1]}) did not — "
                "report this line")

    def _box_reading(self, before, after) -> tuple[bool | None, str]:
        """
        Did a word appear in the box, and the numbers it was decided on.

        Sample by sample, and a count inside a band. Two earlier measures each
        failed on a real machine and both failures are worth keeping in view.

        Counting *changed* samples alone said yes when the panel arrived between
        the readings — the band went from moving world to flat chrome, every
        sample moved, and Drop All fired on an empty filter. Counting how far
        the reading sat from its own most common colour fixed that and broke
        something else: the band is a fixed width derived from the distance to
        Drop All, so it usually covers the search box AND the panel around it,
        and against two flat regions adding a word to one of them barely moves
        the total. That refused every keyword on a correctly configured machine.

        Both are answered by asking a smaller question. Compare each sample to
        itself, and require the count of movers to be enough for a word but too
        few for a repaint. Samples that fell outside the box never change, so
        they cost nothing; a repaint moves all of them at once and is over the
        ceiling; a keyword moves a handful and lands in between.

        The numbers travel with the verdict, because "Drop All skipped" alone is
        a dead end for anyone working out why nothing ever drops.
        """
        if before is None or after is None or len(before) != len(after):
            return None, "the screen could not be read"
        moved = self._moved(before, after)
        low, high = self._word_range(len(after))
        return (low <= moved <= high,
                f"{moved} of {len(after)} samples changed, "
                f"a keyword is {low}-{high}")

    # ------------------------------------------------ is the panel still up
    def _probe_panel(self) -> list[tuple[int, int, int]] | None:
        """
        Colours across the inventory panel, or None when it cannot be read.
        """
        d = self.cfg.drop
        start, end = d.filter_point, d.dropall_point
        span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
        if not any(end) or span < PROBE_MIN_SPAN:
            return None
        return self._read([
            (round(start[0] + (end[0] - start[0]) * fraction),
             round(start[1] + (end[1] - start[1]) * fraction))
            for fraction in PANEL_PROBES
        ])

    @staticmethod
    def _alike(one, other) -> bool:
        """Whether two panel readings show the same thing. False if either is None."""
        if one is None or other is None or len(one) != len(other):
            return False
        same = sum(
            1 for before, after in zip(one, other)
            if all(abs(a - b) <= PROBE_TOLERANCE for a, b in zip(before, after))
        )
        return same * 2 > len(one)

    def _panel_still_up(self, reference) -> bool | None:
        """
        True while the panel looks like it did before the close press.

        None means the question could not be answered — no reference, or the
        screen stopped reading — and the caller falls back to counting presses.
        """
        if reference is None:
            return None
        now = self._probe_panel()
        if now is None or len(now) != len(reference):
            return None
        return self._alike(reference, now)

    def _panel_opened(self, world) -> bool | None:
        """
        Wait until the inventory is actually up. None when it cannot be seen.

        `world` is the same strip read before the inventory key went out, so
        "still the world" and "up and holding still" are both answerable. The
        second half matters as much as the first: a panel caught mid-fade is a
        panel whose search box does not have the keyboard yet, and typing into
        that moment is how a pass ends up clicking Drop All on an empty filter.
        """
        if world is None:
            return None
        deadline = time.perf_counter() + PANEL_OPEN_BUDGET_MS / 1000.0
        previous = None
        covered = 0                         # consecutive readings that are not the world
        while time.perf_counter() < deadline:
            now = self._probe_panel()
            if now is None:
                return None
            if self._alike(now, world):
                covered, previous = 0, None  # nothing has come up yet
            else:
                covered += 1
                if covered >= PANEL_OPEN_CONFIRMATIONS and self._alike(now, previous):
                    return True             # up, and holding still
                previous = now
            if not self._sleep(PANEL_SETTLE_POLL_MS / 1000.0):
                return None
        # Out of budget. Whether that is a refusal depends on which half failed:
        # a strip that stopped looking like the world is an open panel, even if
        # something on it never sat perfectly still. Refusing those would refuse
        # every pass on such a screen, which is a worse bug than the one this
        # method exists to prevent.
        if covered >= PANEL_OPEN_CONFIRMATIONS:
            self.log.emit("the inventory is up but never settles — dropping "
                          "anyway. Move the two points onto quieter parts of "
                          "the panel if this pass goes wrong", "warn")
            return True
        return False

    def _close_inventory(self, reference) -> bool:
        """
        Press until the panel is gone. Returns False if a stop came in.

        Counting presses cannot win here: one press too few leaves the macro
        clicking inside the inventory, one too many sends an Esc into the game
        and opens the pause menu instead. So each press is checked, and the
        loop stops the moment the panel goes away.
        """
        d = self.cfg.drop
        close_key = "esc" if d.close_with == "esc" else d.inventory_key
        blind = max(d.close_presses, 1)
        if reference is None:
            self.log.emit(f"closing the inventory — {blind}x {close_key}, "
                          "unchecked", "info")
        sent = 0
        while True:
            self._tap_key(close_key, hold=CLOSE_HOLD)
            sent += 1
            if not self._wait(CLOSE_GAP_MS):
                return False
            still_up = self._panel_still_up(reference)
            if still_up is None:            # cannot see the screen: just count
                if sent >= blind:
                    return True
                continue
            if not still_up:
                self.log.emit(f"inventory closed after {sent}x {close_key}", "ok")
                return True
            if sent >= CLOSE_ATTEMPTS:
                break
            self.log.emit(f"inventory still up after {sent}x {close_key} — "
                          "pressing again", "warn")

        # the configured key is not doing it: the other one is worth one try
        other = d.inventory_key if close_key == "esc" else "esc"
        self.log.emit(f"{close_key} did not close the inventory — trying "
                      f"{other}", "warn")
        self._tap_key(other, hold=CLOSE_HOLD)
        if not self._wait(CLOSE_GAP_MS):
            return False
        # three outcomes, not two: None is "the screen stopped reading", and
        # reporting that as a clean close would be claiming something this
        # cannot see
        settled = self._panel_still_up(reference)
        if settled:
            self.log.emit("the inventory is still open — check the two points "
                          "on the Farm page, and that ARK is in front", "err")
        elif settled is None:
            self.log.emit(f"sent {other} as well; the screen stopped reading, "
                          "so whether the inventory closed is unknown", "warn")
        else:
            self.log.emit(f"inventory closed with {other}", "ok")
        return True

    # --------------------------------------------------------- auto feeding
    def _feed_problem(self) -> str:
        """Why auto-feed cannot run, or "" when it can."""
        f = self.cfg.auto_feed
        for label, key in (("food", f.food_key), ("water", f.water_key)):
            if w.vk_from_name(key) is None:
                return f'the {label} key "{key}" is not a key name'
        if f.food_key == f.water_key:
            return (f'food and water are both on slot "{f.food_key}" — the '
                    "second press would eat again instead of drinking")
        # a feed key that is also the inventory key would open the panel in the
        # middle of a farming stretch, and the macro would carry on clicking
        # inside it
        if self.cfg.drop.inventory_key in (f.food_key, f.water_key):
            return (f'"{self.cfg.drop.inventory_key}" is the inventory key — '
                    "pick different hotbar slots for food and water")
        return ""

    def _feed(self) -> bool:
        """
        One press for food, one for water. False if a stop came in between.

        Only ever called from the main loop, between two clicks and never inside
        a drop pass: a hotbar key sent while the search field has the keyboard
        would land in the filter as a digit instead of reaching the hotbar.
        """
        f = self.cfg.auto_feed
        self.log.emit(f"auto-feed: slot {f.food_key} then slot {f.water_key}",
                      "info")
        self._tap_key(f.food_key)
        if not self._wait(f.gap_ms):
            return False
        self._tap_key(f.water_key)
        return self._wait(f.gap_ms)

    # ---------------------------------------------------------- stop sign
    def _stop_sign_problem(self) -> str:
        """Why the stop sign cannot run, or "" when it can."""
        s = self.cfg.stop_sign
        if not sweep.usable(s.area):
            return "no icon has been captured yet — pick one on the Farm page"
        if len(s.sample) != len(stopsign.grid(s.area)):
            return ("the captured icon does not match its area any more — "
                    "capture it again")
        return ""

    def _stop_sign_seen(self) -> bool:
        """
        True when the watched patch has turned back into the captured icon.

        A read that fails is not a sighting. The screen going unreadable is its
        own problem and it is loud elsewhere; treating it as the icon here would
        stop the macro for a reason that has nothing to do with the game.
        """
        s = self.cfg.stop_sign
        fresh = self._read(stopsign.grid(s.area))
        if fresh is None:
            return False
        if not stopsign.seen(s.sample, fresh, s.tolerance, s.match_percent):
            return False
        near = stopsign.score(s.sample, fresh, s.tolerance)
        self.log.emit(f"stop sign spotted ({near}% match) — stopping, same as "
                      "pressing the toggle key", "err")
        self._running = False
        return True

    # ------------------------------------------------------- drop routine
    def _run_drop(self) -> None:
        d = self.cfg.drop
        if not any(d.filter_point) or (not d.dry_run and not any(d.dropall_point)):
            self.log.emit("drop pass cancelled: capture the filter and Drop All "
                          "points on the Farm page first", "err")
            return

        templates = d.active_templates()
        if not templates:
            self.log.emit("no template checked on the Farm page", "warn")
            return

        self.state_changed.emit("dropping")
        names = ", ".join(str(t.get("name") or t["keyword"]) for t in templates)
        self.log.emit(f"--- drop pass: {names} ---", "warn")
        if d.dry_run:
            self.log.emit("DRY RUN on — filtering and capturing, no Drop All "
                          "click", "warn")

        # 1) open the inventory, and do not take the game's word for it. The
        #    configured wait is a floor; the screen says when the panel is
        #    really there. Everything after this step assumes an open panel with
        #    a search field ready to take the keyboard, and every one of those
        #    assumptions is wrong at once if the inventory is still on its way.
        world = self._probe_panel() if d.verify_filter else None
        self._tap_key(d.inventory_key)
        if not self._wait(d.open_wait_ms):
            return
        # A panel this could not confirm is a warning, not a veto. It used to
        # abort the pass, and that was a mistake: it is a second opinion on a
        # question the search box already answers — nothing typed into a panel
        # that is not there puts no ink in the box, and that check refuses on its
        # own. Wrong here costs every drop of every pass, so the wrong answer it
        # is allowed to give is the harmless one.
        if self._panel_opened(world) is False:
            self.log.emit(
                f"could not confirm the inventory came up after "
                f"{d.inventory_key} — carrying on, the search-box check still "
                "has to pass before anything drops. If nothing ever drops, the "
                "two captured points are the thing to move", "warn")

        # ARK empties the search box itself when Drop All fires, so the macro
        # only wipes it where the game has not: the first template of the pass,
        # because a human may have left a word in there, and after any template
        # whose drop was skipped.
        stale_box = True
        unreadable_logged = False
        dropped = 0

        for template in templates:
            if not self._running:
                return
            keyword = str(template["keyword"]).strip()

            # 2) focus the filter field
            self._click_point(d.filter_point, "filter field")
            if not self._wait(200):
                return
            if stale_box or d.dry_run:
                self._clear_field()
                stale_box = False

            # 3) read the box while it is still empty, then type the keyword
            empty_box = self._probe_filter()
            self._type(keyword)
            self.log.emit(f'filtering "{keyword}"', "info")
            if not self._wait(d.after_type_wait_ms):
                return
            took, reading = self._box_reading(empty_box, self._probe_filter())

            # 4) the keyword has to be visibly in the box before anything is
            #    dropped. An unfocused field, a swallowed burst of keys, a
            #    stutter in the stream — any of them leaves the box empty, and
            #    Drop All on an unfiltered inventory empties the whole bag. That
            #    is the one failure of this routine nobody can walk back, so it
            #    is checked instead of waited out.
            # A dry run is exempt from both refusals below: it never clicks Drop
            # All, so there is nothing to hold back, and a capture of a filter
            # that did not take is exactly the evidence someone ran it for.
            if took is False and d.verify_filter and not d.dry_run:
                stale_box = True
                self.log.emit(
                    f'"{keyword}" never reached the search field — Drop All '
                    f"skipped, the bag keeps this one ({reading}). Check that "
                    "ARK is in front and that the filter point sits on the "
                    "search box", "err")
                continue
            # A screen that cannot be read is not a pass — it is the check
            # switched off without anyone deciding to switch it off. Dropping
            # anyway is what turns one bad frame into an empty inventory, so the
            # unreadable case now refuses exactly like a failed one.
            if took is None and d.verify_filter and not d.dry_run:
                stale_box = True
                if not unreadable_logged:
                    unreadable_logged = True
                    reason = self._unreadable_reason()
                    self.log.emit(
                        "the screen cannot be read, so the keyword cannot be "
                        f"confirmed and Drop All is being held back. {reason}. "
                        "Run Settings - Display check: it now says whether "
                        "pixels can be read at all. To drop without the check, "
                        "turn off Farm - Before every Drop All and accept the "
                        "risk", "err")
                continue
            if took is False:
                self.log.emit(f'the search box still looks empty after typing '
                              f'"{keyword}" ({reading}) — dropping anyway, the '
                              "check is off", "warn")
            elif took is None and not unreadable_logged:
                unreadable_logged = True
                self.log.emit("the screen cannot be read — Drop All goes out "
                              "unverified, because the check is off", "warn")
            elif took:
                # said out loud on the way through, not only when refusing: a log
                # from a session that worked is the only thing that makes a log
                # from a session that did not mean anything
                self.log.emit(f'"{keyword}" is in the box ({reading})', "info")

            # 5) Drop All — with the filter on, only what is listed falls
            if d.dry_run:
                self.shot_requested.emit(keyword)
                self.log.emit(f'dry run: captured "{keyword}", Drop All not '
                              "clicked", "warn")
                if not self._sleep(0.6):
                    return
            else:
                self._click_point(d.dropall_point, "Drop All")
                dropped += 1
                if not self._wait(d.after_drop_wait_ms):
                    return

        # 6) a dry run never clicked Drop All, and neither did a skipped
        #    template, so nothing cleared the filter — leaving the inventory
        #    masked behind the last keyword
        if d.dry_run or stale_box:
            self._click_point(d.filter_point, "filter field")
            if not self._wait(200):
                return
            self._clear_field()

        # 7) close the inventory. Typing in the filter leaves the search field
        #    holding the keyboard, so the first press only steps out of it and
        #    the panel is still up. How many it takes is not something to
        #    guess: read the panel now, while it is certainly open, and press
        #    until those pixels change.
        if not self._wait(250):
            return
        panel = self._probe_panel()
        if not self._close_inventory(panel):
            return
        # and stay off the mouse while the panel animates away, or the first
        # swings of the next stretch land on an inventory that is still up
        if not self._wait(d.close_wait_ms):
            return

        # a pass where every drop was skipped is not a pass done: the weight is
        # still climbing, and the counter on the dashboard must not say otherwise
        if not dropped and not d.dry_run:
            self.log.emit("--- drop pass dropped nothing: the keyword never "
                          "reached the search field. Bring ARK to the front, or "
                          "recapture the filter point ---", "err")
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

        # Posted messages cannot reach a streamed session: the GeForce NOW
        # client grabs real input and forwards it over the network, and a
        # WM_KEYDOWN handed to its window is not real input. Nothing would
        # arrive in game and every wait would still be paid, so say so and stop
        # instead of farming into the void.
        if cfg.target.mode == "background" and cfg.target.platform == "geforce_now":
            self.log.emit("background delivery cannot reach a GeForce NOW "
                          "session — the client only forwards real input. "
                          "Switch Delivery mode to foreground", "err")
            self.state_changed.emit("idle")
            self._running = False
            return

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

        feed_ok = cfg.auto_feed.enabled
        if feed_ok:
            problem = self._feed_problem()
            if problem:
                feed_ok = False
                self.log.emit(f"auto-feed off for this run: {problem}", "err")
            else:
                self.log.emit(
                    f"auto-feed armed: slots {cfg.auto_feed.food_key} and "
                    f"{cfg.auto_feed.water_key} every "
                    f"{cfg.auto_feed.interval_s}s", "ok")

        self.state_changed.emit("farming")
        self.log.emit("macro armed", "ok")

        stop_ok = cfg.stop_sign.enabled
        if stop_ok:
            problem = self._stop_sign_problem()
            if problem:
                stop_ok = False
                self.log.emit(f"stop sign off for this run: {problem}", "err")
            else:
                self.log.emit("stop sign armed — the macro stops on its own if "
                              "that icon shows up", "ok")

        last_drop = time.perf_counter()
        last_feed = time.perf_counter()
        last_look = time.perf_counter()
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
                    # the count alone is not a measure of swings: a dino with
                    # its own attack cooldown eats fourteen clicks in two
                    # seconds and lands three hits, so a minimum stretch of
                    # farming has to pass as well
                    farmed = time.perf_counter() - last_drop
                    due = (clicks_since_drop >= max(d.every_clicks, 1)
                           and farmed >= d.min_farm_s)

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

            # Feeding sits here on purpose, and nowhere else: past the focus
            # gate, so the keys cannot land in another window, and outside the
            # drop pass above, which runs to completion before this line is ever
            # reached. A timer on the UI thread could fire while the filter has
            # the keyboard and type a digit into the search box.
            if feed_ok and (time.perf_counter() - last_feed
                            >= cfg.auto_feed.interval_s):
                if not self._feed():
                    break
                last_feed = time.perf_counter()

            # The stop sign sits here for the same reason feeding does: past the
            # focus gate, and never inside a drop pass. Checked before the click
            # rather than after, so the click that would have followed the icon
            # appearing is the one that does not happen.
            if (stop_ok and time.perf_counter() - last_look
                    >= cfg.stop_sign.poll_ms / 1000.0):
                last_look = time.perf_counter()
                if self._stop_sign_seen():
                    break

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
