"""
Window matching, with the OS calls faked.

    python tests/test_winapi.py
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from arkmacro import winapi as w  # noqa: E402

EXPLORER = 101   # a folder called ark-farm-macro, open in Explorer
GAME = 102       # the actual game
BROWSER = 103
OWN = 104        # one of our own windows

TITLES = {
    EXPLORER: "ark-farm-macro - File Explorer",
    GAME: "ArkAscended",
    BROWSER: "ark wiki - Chrome",
    OWN: "A.N.S Tools — ark",
}
RECTS = {
    EXPLORER: (8, 0, 891, 994),
    GAME: (0, 0, 1920, 1080),
    BROWSER: (0, 0, 1600, 900),
    OWN: (0, 0, 1060, 760),
}


def install(visible: list[int]) -> None:
    w.list_windows = lambda: [(hwnd, TITLES[hwnd]) for hwnd in visible]
    w.client_rect = lambda hwnd: RECTS.get(hwnd)
    w.window_pid = lambda hwnd: os.getpid() if hwnd == OWN else 4321


# ------------------------------------------- 1) the game beats a folder window
install([EXPLORER, GAME, BROWSER])
assert w.find_window("ark") == GAME, "a substring match outranked the game"
print("OK  a prefix match beats a mere substring")

# ------------------------------------------- 2) size breaks a rank tie
install([EXPLORER, BROWSER])
assert w.find_window("ark") == BROWSER, "the smaller window won the tie"
print("OK  among equal ranks the larger client area wins")

# ------------------------------------------- 3) our own windows never qualify
install([OWN])
assert w.find_window("ark") is None, "the macro targeted itself"
print("OK  our own windows are never a target")

# ------------------------------------------- 4) exact titles win outright
install([EXPLORER, GAME])
assert w.find_window("ArkAscended") == GAME
assert w.find_window("arkascended") == GAME, "matching must ignore case"
print("OK  an exact title wins outright, case-insensitively")

# ------------------------------------------- 5) nothing to match
install([EXPLORER, GAME, BROWSER])
assert w.find_window("nothing-like-this") is None
assert w.find_window("") is None and w.find_window("   ") is None
print("OK  no match and an empty fragment both return nothing")

# ------------------------------------------- 6) a window with no client rect
install([GAME])
w.client_rect = lambda hwnd: None
assert w.find_window("ark") == GAME, "a missing rect must not disqualify"
print("OK  a window with no readable rect is still a candidate")

# -------------------------------- 7) reading pixels, in one grab or many
# The engine asks for a few dozen points inside a small box every time it checks
# whether a keyword landed. Reading them out of one blit is the fast path; the
# point-by-point path is what has to answer when the blit cannot run, and it is
# the one that used to be the only path — through GetPixel, which cannot see a
# streaming client's picture and reported the whole screen unreadable because
# of it.
# First against the real thing, which only means anything on Windows. The blit
# is a chain of six GDI calls through ctypes, and a wrong signature in any of
# them is a crash or a garbage answer that no amount of mocking would show.
real = w.screen_region(0, 0, 4, 3)
if real is None:
    print("..  screen_region read nothing here (expected off Windows)")
else:
    assert len(real) == 12, f"asked for 4x3, got {len(real)} pixels"
    assert all(len(px) == 3 and all(0 <= c <= 255 for c in px) for px in real), \
        real[:4]
    assert w.screen_pixel(0, 0) == real[0], "the single read disagrees with the grab"
    for _ in range(200):                    # a leak here would exhaust GDI handles
        assert w.screen_region(0, 0, 4, 3) is not None
    print("..  screen_region reads the real desktop, 200 grabs without leaking")

GRID = {(x, y): (x % 256, y % 256, (x + y) % 256)
        for x in range(100, 140) for y in range(50, 60)}

w.screen_region = lambda x, y, width, height: [
    GRID[(px, py)] for py in range(y, y + height) for px in range(x, x + width)
]
spots = [(101, 51), (137, 58), (120, 55)]
assert w.screen_samples(spots) == [GRID[spot] for spot in spots], \
    "the batched read picked the wrong pixels out of the grab"
assert w.screen_samples([]) == []
assert w.screen_samples([(110, 52)]) == [GRID[(110, 52)]]

# a grab that cannot run falls back to reading the points one at a time
w.screen_region = lambda *_args: None
w.screen_pixel = lambda x, y: GRID.get((int(x), int(y)))
assert w.screen_samples(spots) == [GRID[spot] for spot in spots], \
    "the fallback did not answer"
# and one unreadable point makes the whole reading unreadable, because a probe
# with a hole in it is not a probe
assert w.screen_samples(spots + [(999, 999)]) is None
print("OK  pixels come back from one grab, or one at a time when it fails")

# ------------------ 8) reading a window that is not the one in front
# Background delivery farms a game while something else has focus, so the screen
# at those coordinates belongs to whatever is in front. The window can be asked
# to paint itself instead — and where it will not, that has to come back None
# rather than as a rectangle of black that reads like a real answer.
w.client_rect = lambda hwnd: None
assert w.window_shot(12345) is None, "a window with no rect handed back pixels"
assert w.window_samples(12345, [(0, 0)]) is None

# a window that paints: the points are SCREEN coordinates and have to go through
# its current position, or a stored point stops meaning the button it was on
w.client_rect = lambda hwnd: (100, 50, 4, 3)
w.screen_to_client = lambda hwnd, x, y: (x - 100, y - 50)
PAINTED = [(i, i, i) for i in range(12)]
w.window_shot = lambda hwnd: (PAINTED, 4, 3)
assert w.window_samples(1, [(100, 50)]) == [PAINTED[0]], "top-left came out wrong"
assert w.window_samples(1, [(103, 52)]) == [PAINTED[11]], "bottom-right wrong"
assert w.window_samples(1, [(101, 51)]) == [PAINTED[5]]
# a point that has fallen outside the window is not a reading, it is a hole
assert w.window_samples(1, [(100, 50), (999, 999)]) is None
print("OK  a window can be read from behind, in its own coordinates")

# ------------------ 9) visible is not the same question as focused
# Conflating the two is what made background delivery blind for three sessions.
# A game sitting uncovered on a second monitor has no focus and is perfectly
# readable; the only thing that stops a screen read being the game is something
# drawn on top of it.
GAME, OTHER = 4242, 777
w.window_at = lambda x, y: OTHER if x > 500 else GAME

assert w.visible_at(GAME, [(10, 10), (200, 40)]), \
    "an uncovered window read as covered — this is the second-monitor case"
assert not w.visible_at(GAME, [(10, 10), (900, 40)]), \
    "one covered point is enough: those pixels belong to somebody else"
assert not w.visible_at(GAME, [(900, 40)])
assert w.visible_at(OTHER, [(900, 40)])
# no window is not the game
assert not w.visible_at(0, [(10, 10)])
print("OK  visible is asked of Windows, not inferred from focus")

print("\nALL WINAPI TESTS PASSED")
