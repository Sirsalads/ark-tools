"""
Recognising one small mark on screen, so the macro can stop when it appears.

The game has no way to tell the app that a dino is capped or a tool broke — but
it says so on screen, with an icon, every time. So the app is shown the icon
once and watches for it.

What it remembers is NOT a photograph. That was the first version and it did not
work, for a reason the screenshot makes obvious: an ARK HUD icon is drawn over
the live 3D scene. Half the samples in any box around it land on rock, sky and
water that change every frame, so a colour-for-colour comparison drifts with the
weather and never scores.

What actually holds still is the *shape*: a cluster of very dark pixels in a
particular arrangement, standing out from whatever is behind it. So capture
records which samples are the mark and which way they stand out — darker or
lighter than the middle of the box — and matching asks whether those same
samples still stand out that way, measured against the box's own middle *now*.
The background is not compared at all. It is allowed to be anything.

Nothing in here touches the screen or the game: it is the arithmetic, so it can
be tested without either.
"""
from __future__ import annotations

# Fewer samples than this and a match means very little; the grid is capped too,
# because this is read several times a second and every sample is a pixel.
GRID_MIN = 4
GRID_MAX = 12
# below this many standing-out samples there is no mark to look for, and the
# likeliest reason is a box captured while the icon was not showing
MARKS_MIN = 4


def grid(area: list[int], across: int = 8) -> list[tuple[int, int]]:
    """
    Points spread over `area`, the same ones every time for the same rectangle.

    Both capture and matching call this, which is the whole contract: a
    remembered mark is only comparable to a fresh reading if they are the same
    points in the same order.
    """
    x, y, width, height = (int(value) for value in area)
    if width <= 0 or height <= 0:
        return []
    across = max(GRID_MIN, min(int(across), GRID_MAX))
    # inset by half a cell so no sample sits on the box's outer edge, where a
    # single pixel of whatever is behind it changes the answer
    return [
        (round(x + width * (column + 0.5) / across),
         round(y + height * (row + 0.5) / across))
        for row in range(across)
        for column in range(across)
    ]


def _luma(colour) -> float:
    """Perceived brightness, so "darker" and "lighter" mean something."""
    red, green, blue = (colour[0], colour[1], colour[2])
    return 0.299 * red + 0.587 * green + 0.114 * blue


def _middle(samples) -> float:
    """The box's own middle brightness, recomputed for every reading.

    Taking it from the reading being judged is what makes the whole measure
    survive a scene that is darker at night and brighter at noon: the mark is
    always compared to what is around it *at that moment*, never to what was
    around it at capture time.
    """
    values = sorted(_luma(colour) for colour in samples)
    return values[len(values) // 2]


def signature(sample, tolerance: int) -> list[tuple[int, int]]:
    """
    (index, direction) for every sample that stands out from the box's middle.

    Direction is +1 for lighter, -1 for darker. This is the mark: the samples
    the icon is drawn on. Everything else is background and never looked at
    again.
    """
    if not sample:
        return []
    middle = _middle(sample)
    marks = []
    for index, colour in enumerate(sample):
        delta = _luma(colour) - middle
        if abs(delta) > tolerance:
            marks.append((index, 1 if delta > 0 else -1))
    return marks


def contrast(sample, tolerance: int) -> int:
    """How far the mark stands out, on average — the margin a dial has to clear."""
    marks = signature(sample, tolerance)
    if not marks:
        return 0
    middle = _middle(sample)
    return round(sum(abs(_luma(sample[index]) - middle) for index, _d in marks)
                 / len(marks))


def _hits(marks, fresh, tolerance: int) -> int:
    """How many of the remembered marks still stand out the same way."""
    middle = _middle(fresh)
    return sum(1 for index, direction in marks
               if (_luma(fresh[index]) - middle) * direction > tolerance)


def seen(sample, fresh, tolerance: int, match_percent: int) -> bool:
    """Whether `fresh` shows the remembered mark."""
    marks = signature(sample, tolerance)
    if len(marks) < MARKS_MIN or not fresh or len(fresh) != len(sample):
        return False
    needed = max(1, round(len(marks) * max(0, min(int(match_percent), 100)) / 100))
    return _hits(marks, fresh, tolerance) >= needed


def score(sample, fresh, tolerance: int) -> int:
    """How much of the mark is there, as a percentage, for saying how close."""
    marks = signature(sample, tolerance)
    if not marks or not fresh or len(fresh) != len(sample):
        return 0
    return round(100 * _hits(marks, fresh, tolerance) / len(marks))
