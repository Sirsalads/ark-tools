"""Pure helpers for painting dye stacks and recognising the next dye icon."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import SkinOvercap

CLICKS_PER_STACK = 100
PROBE_OFFSETS = (-6, -3, 0, 3, 6)
SAMPLE_COUNT = len(PROBE_OFFSETS) ** 2
CHANNEL_TOLERANCE = 50
MATCH_PERCENT = 70


def _valid_point(point: Any) -> bool:
    return (isinstance(point, (list, tuple)) and len(point) == 2
            and all(type(value) is int for value in point))


def probe_points(point: list[int] | tuple[int, int]) -> list[tuple[int, int]]:
    """The same 25 screen pixels, in row order, around a dye icon's centre."""
    if not _valid_point(point):
        return []
    x, y = point
    return [(x + dx, y + dy) for dy in PROBE_OFFSETS for dx in PROBE_OFFSETS]


def valid_sample(sample: Any) -> bool:
    """Reject partial reads, malformed RGB values and a completely black read."""
    return (isinstance(sample, (list, tuple)) and len(sample) == SAMPLE_COUNT
            and all(isinstance(colour, (list, tuple)) and len(colour) == 3
                    and all(type(channel) is int and 0 <= channel <= 255
                            for channel in colour)
                    for colour in sample)
            and any(any(colour) for colour in sample))


def match_score(reference: Any, observed: Any) -> int:
    """
    How much of the remembered dye is still there, as a percentage.

    The same arithmetic `matches_dye` decides on, kept apart so a refusal can
    say how close it came. "The dye is absent" and "17 of 25 pixels agreed, one
    short" are the same event, and only one of them can be acted on.
    """
    if not valid_sample(reference) or not valid_sample(observed):
        return 0
    matches = sum(max(abs(a - b) for a, b in zip(before, after))
                  <= CHANNEL_TOLERANCE
                  for before, after in zip(reference, observed))
    return round(100 * matches / SAMPLE_COUNT)


def median_colour(sample: Any) -> tuple[int, int, int] | None:
    """The middle of a reading, per channel — what the patch mostly is.

    Taken channel by channel rather than as whole pixels: it is not one of the
    samples, it is what they agree on, which is the point. A handful of pixels
    landing on a highlight, a border or a changed stack count cannot move it.
    """
    if not valid_sample(sample):
        return None
    middle = len(sample) // 2
    return tuple(sorted(colour[channel] for colour in sample)[middle]
                 for channel in range(3))


def median_apart(reference: Any, observed: Any) -> int:
    """How far the two readings' middles are, on their worst channel."""
    before, after = median_colour(reference), median_colour(observed)
    if before is None or after is None:
        return 255
    return max(abs(a - b) for a, b in zip(before, after))


def dominated(sample: Any) -> bool:
    """
    Whether most of a patch is the same colour as its own middle.

    This is what makes a capture recognisable later. A patch taken from inside
    the icon is nearly all one colour and reads the same every frame. A patch
    taken across the icon's EDGE is part dye and part panel, and every pixel on
    the boundary changes with a highlight, a redraw, or whatever the panel is
    translucent over — measured on a real capture: 3 of its 25 pixels agreed
    with its own middle, and the live check then scored 12%, 32% and 56%
    against a dye that was plainly there.

    Nothing about that is visible when you click, which is why it is worth
    saying at capture time rather than leaving it to be discovered as "the
    macro does not work".
    """
    middle = median_colour(sample)
    if middle is None:
        return False
    alike = sum(max(abs(a - b) for a, b in zip(colour, middle))
                <= CHANNEL_TOLERANCE for colour in sample)
    return alike * 100 >= SAMPLE_COUNT * MATCH_PERCENT


def matches_dye(reference: Any, observed: Any) -> bool:
    """Whether the slot still shows the captured dye.

    Two ways to say yes, because one of them was not enough.

    Pixel for pixel: at least 18 of 25 within 50 per RGB channel. Strict, and
    right when it fires.

    Or the middles agree. A dye icon is mostly its own colour and an empty slot
    is mostly panel, so the middle of the patch separates them on its own — and
    unlike the per-pixel count it does not care that some of the samples moved.
    Measured on a real setup, the per-pixel count came back 12%, 32% and 56%
    against a dye that was plainly sitting in the slot, and painting ran for
    46 minutes with the check switched off because of it. Whatever was moving
    those pixels — a hover highlight, a quantity that changes as the stack goes
    down, the panel's own translucency over a scene that never holds still —
    it does not move what the patch mostly is.

    A second way to say yes can only accept more, never less, so this cannot
    take away a check that was already working.
    """
    if not valid_sample(reference) or not valid_sample(observed):
        return False
    matches = sum(max(abs(a - b) for a, b in zip(before, after))
                  <= CHANNEL_TOLERANCE
                  for before, after in zip(reference, observed))
    if matches * 100 >= SAMPLE_COUNT * MATCH_PERCENT:
        return True
    # The middle only identifies anything when the reference is mostly one
    # colour. A patch captured half on the icon and half on the panel behind it
    # has a middle that belongs to neither, and an emptied slot would go on
    # matching it forever — the check would never stop the run, which is the
    # one job it has. So the second path is offered only to a patch that agrees
    # with itself.
    if not dominated(reference):
        return False
    return median_apart(reference, observed) <= CHANNEL_TOLERANCE


def ready(skin: SkinOvercap) -> bool:
    """Both click targets and a readable dye sample must have been captured."""
    paint = getattr(skin, "paint_point", None)
    dye = getattr(skin, "dye_point", None)
    return (_valid_point(paint) and _valid_point(dye)
            and any(paint) and any(dye) and tuple(paint) != tuple(dye)
            and valid_sample(getattr(skin, "dye_sample", None)))
