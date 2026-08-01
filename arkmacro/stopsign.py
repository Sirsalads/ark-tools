"""
Recognising one small picture on screen, so the macro can stop when it appears.

The game has no way to tell the app that a tool broke or the character is
overloaded — but it says so on screen, with an icon, every time. So the app is
shown the icon once and remembers it as a grid of colours; while farming it
re-reads that same grid and counts how many samples still match.

A count, not an exact compare, and the reason is the two things that are always
true of this picture. It is drawn over a moving world, so its transparent parts
and its edges are never the same twice; and on a streamed session the whole
frame is lossy, so even flat colour arrives a few values off. An exact compare
would never match. A count with slack matches the icon and nothing else, because
the alternative to the icon is not a slightly different icon — it is a different
part of the screen entirely, which misses on almost every sample.

Nothing in here touches the screen or the game: it is the arithmetic, so it can
be tested without either.
"""
from __future__ import annotations

# Fewer samples than this and a match means very little; the grid is capped too,
# because this is read several times a second and every sample is a pixel.
GRID_MIN = 4
GRID_MAX = 12


def grid(area: list[int], across: int = 8) -> list[tuple[int, int]]:
    """
    Points spread over `area`, the same ones every time for the same rectangle.

    Both capture and matching call this, which is the whole contract: a
    remembered sample is only comparable to a fresh one if they are the same
    points in the same order.
    """
    x, y, width, height = (int(value) for value in area)
    if width <= 0 or height <= 0:
        return []
    across = max(GRID_MIN, min(int(across), GRID_MAX))
    # inset by half a cell so no sample sits on the icon's outer edge, where a
    # single pixel of the background behind it changes the answer
    return [
        (round(x + width * (column + 0.5) / across),
         round(y + height * (row + 0.5) / across))
        for row in range(across)
        for column in range(across)
    ]


def matches(sample, fresh, tolerance: int) -> int:
    """How many of `fresh` are within `tolerance` of `sample`, channel by channel."""
    if not sample or not fresh or len(sample) != len(fresh):
        return 0
    return sum(
        1 for remembered, now in zip(sample, fresh)
        if len(remembered) == len(now)
        and all(abs(a - b) <= tolerance for a, b in zip(remembered, now))
    )


def seen(sample, fresh, tolerance: int, match_percent: int) -> bool:
    """Whether `fresh` is the remembered picture."""
    if not sample or not fresh or len(sample) != len(fresh):
        return False
    needed = max(1, round(len(sample) * max(0, min(int(match_percent), 100)) / 100))
    return matches(sample, fresh, tolerance) >= needed


def score(sample, fresh, tolerance: int) -> int:
    """The match as a percentage, for saying how close a look was."""
    if not sample or not fresh or len(sample) != len(fresh):
        return 0
    return round(100 * matches(sample, fresh, tolerance) / len(sample))


def distinct(sample, tolerance: int) -> int:
    """
    How many different colours the remembered picture has, roughly.

    A patch of flat colour matches half the screen, so a stop sign captured off
    an empty bit of HUD would stop the macro at random. This is what lets the app
    say so at capture time instead of leaving it to be discovered mid-farm.
    """
    seen_colours: list[tuple] = []
    for colour in sample or []:
        if not any(all(abs(a - b) <= tolerance for a, b in zip(colour, other))
                   for other in seen_colours):
            seen_colours.append(tuple(colour))
    return len(seen_colours)
