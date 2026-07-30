"""
Hold-to-drop: the path the cursor takes across a block of inventory slots.

ARK drops the stack under the cursor while its drop key is held, so emptying a
rectangle of slots is a matter of visiting every slot centre while that key is
down. The app never presses the key — the player holds it, and the app moves the
mouse. Pressing it would mean registering it as a hotkey, and a registered hotkey
is swallowed before the game sees it, which is the one thing that must not happen
here.

The path is a **serpentine**, not the circle it looks like on screen. A circle
only touches the slots on its own ring and leaves every slot inside untouched;
row by row, reversing direction each row, visits all of them and never jumps back
across the grid.
"""
from __future__ import annotations

# below this a rectangle is a stray click, not a selection
MIN_SIDE = 24


def _centres(start: float, span: float, count: int) -> list[int]:
    """Centres of `count` equal cells along one axis."""
    if count <= 1:
        return [round(start + span / 2)]
    pitch = span / count
    return [round(start + pitch * (index + 0.5)) for index in range(count)]


def serpentine(area: list[int], columns: int, rows: int) -> list[tuple[int, int]]:
    """
    Every slot centre of a `columns` x `rows` grid inside `area`, in sweep order.

    `area` is [x, y, width, height] in screen pixels. Rows alternate direction,
    so the cursor leaves each row where the next one starts and the path has no
    long jump in it — a jump would cross slots that are not part of the grid,
    and while the drop key is held it would drop those too.
    """
    x, y, width, height = (int(value) for value in area)
    columns, rows = max(int(columns), 1), max(int(rows), 1)
    if width < MIN_SIDE or height < MIN_SIDE:
        return []
    xs = _centres(x, width, columns)
    ys = _centres(y, height, rows)
    path: list[tuple[int, int]] = []
    for index, row_y in enumerate(ys):
        order = xs if index % 2 == 0 else list(reversed(xs))
        path.extend((column_x, row_y) for column_x in order)
    return path


def normalise(x1: int, y1: int, x2: int, y2: int) -> list[int]:
    """Two dragged corners -> [x, y, width, height], whichever way it was drawn."""
    left, right = sorted((int(x1), int(x2)))
    top, bottom = sorted((int(y1), int(y2)))
    return [left, top, right - left, bottom - top]


def usable(area: list[int]) -> bool:
    """Whether an area is big enough to sweep."""
    try:
        return int(area[2]) >= MIN_SIDE and int(area[3]) >= MIN_SIDE
    except (TypeError, ValueError, IndexError):
        return False


def rescale(area: list[int], src: list[int], dst: list[int]) -> list[int]:
    """
    Convert an area captured at `src` resolution to `dst`.

    Same model as a picked point: ARK anchors its UI to the centre of the screen
    and scales it with height, so the corner moves with the centre and the size
    scales with height alone.
    """
    src_w, src_h = src
    dst_w, dst_h = dst
    if not src_w or not src_h or not dst_w or not dst_h:
        return list(area)
    x, y, width, height = area
    scale = dst_h / src_h
    return [round(dst_w / 2 + (x - src_w / 2) * scale),
            round(dst_h / 2 + (y - src_h / 2) * scale),
            round(width * scale),
            round(height * scale)]
