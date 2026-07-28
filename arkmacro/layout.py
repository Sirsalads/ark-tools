"""
Geometric model of ARK's inventory HUD.

ARK anchors its UI to the CENTRE of the screen and scales it with HEIGHT — on
ultrawide the panels do not stretch, they stay centred. So a point is better
described as an offset from the centre measured in screen-height units than as
an absolute pixel pair.

The offsets below were measured on the left panel (the survivor inventory) with
a container open. They are a STARTING GUESS: the layout shifts depending on
what is open (inventory alone, storage box, dino) and on the HUD scale, so the
picked points still have to be verified.
"""
from __future__ import annotations

# (dx, dy) from the screen centre, in screen-height units
SEARCH_OFFSET = (-0.6321, -0.3213)    # search field (magnifier), panel top
DROPALL_OFFSET = (-0.4655, -0.3213)   # 2nd icon of the row, next to the arrows


def _from_offset(offset: tuple[float, float], width: int, height: int,
                 origin: tuple[int, int]) -> list[int]:
    return [round(origin[0] + width / 2 + offset[0] * height),
            round(origin[1] + height / 2 + offset[1] * height)]


def suggest(width: int, height: int,
            origin: tuple[int, int] = (0, 0)) -> tuple[list[int], list[int]]:
    """
    Starting guess for (filter field, Drop All button).

    `origin` is the top-left corner of the game area in screen coordinates:
    0,0 in fullscreen, the window corner in windowed mode.
    """
    return (_from_offset(SEARCH_OFFSET, width, height, origin),
            _from_offset(DROPALL_OFFSET, width, height, origin))


def rescale(point: list[int], src: list[int], dst: list[int]) -> list[int]:
    """Convert a point captured at `src` resolution to `dst`."""
    src_w, src_h = src
    dst_w, dst_h = dst
    if not src_w or not src_h or not dst_w or not dst_h:
        return list(point)
    offset_x = (point[0] - src_w / 2) / src_h
    offset_y = (point[1] - src_h / 2) / src_h
    return [round(dst_w / 2 + offset_x * dst_h),
            round(dst_h / 2 + offset_y * dst_h)]
