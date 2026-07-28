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

print("\nALL WINAPI TESTS PASSED")
