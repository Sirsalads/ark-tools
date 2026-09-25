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


def matches_dye(reference: Any, observed: Any) -> bool:
    """Allow small lighting/streaming changes while rejecting an empty slot.

    At least 18 of 25 pixels must agree, within 50 per RGB channel. The central
    patch avoids the changing stack count and the selected slot's border.
    """
    if not valid_sample(reference) or not valid_sample(observed):
        return False
    matches = sum(max(abs(a - b) for a, b in zip(before, after))
                  <= CHANNEL_TOLERANCE
                  for before, after in zip(reference, observed))
    return matches * 100 >= SAMPLE_COUNT * MATCH_PERCENT


def ready(skin: SkinOvercap) -> bool:
    """Both click targets and a readable dye sample must have been captured."""
    paint = getattr(skin, "paint_point", None)
    dye = getattr(skin, "dye_point", None)
    return (_valid_point(paint) and _valid_point(dye)
            and any(paint) and any(dye) and tuple(paint) != tuple(dye)
            and valid_sample(getattr(skin, "dye_sample", None)))
