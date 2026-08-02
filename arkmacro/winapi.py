"""
Low level Windows input.

Two delivery paths:
  * SendInput   -> real input, indistinguishable from a physical keyboard or
                   mouse. The only path Unreal Engine (ARK) reads reliably,
                   but the game window has to be focused.
  * PostMessage -> messages straight to the HWND, works with the window in the
                   background. Many games ignore it because they read Raw
                   Input, which is why background mode is flagged experimental.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

ULONG_PTR = wintypes.WPARAM

# ---------------------------------------------------------------- structs

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MAPVK_VK_TO_VSC = 0

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.VkKeyScanW.argtypes = (ctypes.c_wchar,)
user32.VkKeyScanW.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
# present from Windows 10 1607; absent on anything older, which dpi_awareness
# reports rather than crashing on
if hasattr(user32, "GetThreadDpiAwarenessContext"):
    user32.GetThreadDpiAwarenessContext.argtypes = ()
    user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.GetAwarenessFromDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
    user32.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int


def _send(*inputs: INPUT) -> None:
    count = len(inputs)
    array = (INPUT * count)(*inputs)
    user32.SendInput(count, array, ctypes.sizeof(INPUT))


# --------------------------------------------------------------- keyboard

# Keys that need the "extended" bit on their scancode.
_EXTENDED = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # pgup/pgdn/end/home/arrows
    0x2D, 0x2E,  # insert / delete
    0x5B, 0x5C, 0x5D,  # win / menu
    0x6F, 0x90, 0xA3, 0xA5,  # numpad /, numlock, right ctrl, right alt
}

VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11,
    "alt": 0x12, "pause": 0x13, "capslock": 0x14, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
    "win": 0x5B, "numlock": 0x90,
}
for _index in range(10):
    VK[str(_index)] = 0x30 + _index
    VK[f"num{_index}"] = 0x60 + _index
for _letter in "abcdefghijklmnopqrstuvwxyz":
    VK[_letter] = ord(_letter.upper())
for _index in range(1, 25):
    VK[f"f{_index}"] = 0x6F + _index


def vk_from_name(name: str) -> int | None:
    """Turn 'f6', 'ctrl', 'i', 'esc' into a virtual-key code."""
    return VK.get((name or "").strip().lower())


def key_is_down(vk: int) -> bool:
    """
    True while the key is physically held.

    This is how hold-to-drop watches ARK's drop key, and it has to be a *read*.
    RegisterHotKey — what the global hotkeys use — consumes the keystroke before
    the foreground window sees it, so binding the drop key that way would stop
    the game from ever receiving it and nothing would drop. GetAsyncKeyState only
    looks.
    """
    return bool(user32.GetAsyncKeyState(int(vk)) & 0x8000)


def _scan(vk: int) -> int:
    return user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)


def key_down(vk: int) -> None:
    # keys with no scancode on this layout (F13-F24, for instance) have to go
    # out as a virtual key, or the event carries scancode 0 and is dropped
    scan = _scan(vk)
    if not scan:
        _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, 0, 0, 0)))
        return
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0)
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, flags, 0, 0)))


def key_up(vk: int) -> None:
    scan = _scan(vk)
    if not scan:
        _send(INPUT(type=INPUT_KEYBOARD,
                    ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)))
        return
    flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if vk in _EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, flags, 0, 0)))


def tap(vk: int, hold: float = 0.035) -> None:
    key_down(vk)
    time.sleep(hold)
    key_up(vk)


def type_text(text: str, delay: float = 0.045, unicode_mode: bool = False) -> None:
    """
    Type `text` one character at a time.

    Scancodes by default, which is what the game sees as a real keyboard.
    `unicode_mode` falls back to KEYEVENTF_UNICODE, useful for accents or if
    the search field ignores scancodes.
    """
    for char in text:
        if unicode_mode:
            code = ord(char)
            _send(INPUT(type=INPUT_KEYBOARD,
                        ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)))
            _send(INPUT(type=INPUT_KEYBOARD,
                        ki=KEYBDINPUT(0, code,
                                      KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)))
        else:
            scanned = user32.VkKeyScanW(ctypes.c_wchar(char))
            if scanned == -1:  # no key for it on this layout -> unicode
                type_text(char, delay=0, unicode_mode=True)
                time.sleep(delay)
                continue
            vk = scanned & 0xFF
            shifted = bool(scanned & 0x100)
            if shifted:
                key_down(VK["shift"])
            tap(vk, hold=0.025)
            if shifted:
                key_up(VK["shift"])
        time.sleep(delay)


# ------------------------------------------------------------------ mouse

_BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def mouse_down(button: str = "left") -> None:
    down, _ = _BUTTON_FLAGS.get(button, _BUTTON_FLAGS["left"])
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, down, 0, 0)))


def mouse_up(button: str = "left") -> None:
    _, up = _BUTTON_FLAGS.get(button, _BUTTON_FLAGS["left"])
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, up, 0, 0)))


def click(button: str = "left", hold: float = 0.03) -> None:
    mouse_down(button)
    time.sleep(hold)
    mouse_up(button)


def get_cursor_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def move_cursor(x: int, y: int) -> None:
    """Absolute cursor move that also covers multi-monitor setups."""
    user32.SetCursorPos(int(x), int(y))
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = max(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), 1)
    vh = max(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN), 1)
    nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
    ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
    flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(nx, ny, 0, flags, 0, 0)))


def click_at(x: int, y: int, button: str = "left",
             hold: float = 0.04, settle: float = 0.06) -> None:
    move_cursor(x, y)
    time.sleep(settle)
    click(button, hold)


# ----------------------------------------------------------- windows/hwnd

WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MOUSEMOVE = 0x0200
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_CHAR = 0x0102
MK_LBUTTON, MK_RBUTTON = 0x0001, 0x0002

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Without explicit signatures ctypes marshals every argument as a C int, which
# truncates a 64-bit HWND. These handles usually fit in 32 bits, so the bug
# would only ever show up on someone else's machine — pin the types instead.
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
user32.ClientToScreen.restype = wintypes.BOOL
user32.ScreenToClient.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
user32.ScreenToClient.restype = wintypes.BOOL
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL
user32.EnumWindows.argtypes = (_ENUM_PROC, wintypes.LPARAM)
user32.EnumWindows.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetDC.argtypes = (wintypes.HWND,)
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.ReleaseDC.restype = ctypes.c_int
gdi32.GetPixel.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
gdi32.GetPixel.restype = wintypes.COLORREF
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                         wintypes.DWORD)
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
gdi32.DeleteDC.restype = wintypes.BOOL

CLR_INVALID = 0xFFFFFFFF
SRCCOPY = 0x00CC0020
# Without this flag the blit skips layered and overlay surfaces — which is most
# of what matters here, because a streaming client's video is exactly that.
CAPTUREBLT = 0x40000000
BI_RGB = 0
DIB_RGB_COLORS = 0
# above this many pixels a single grab is not worth it, and the points get read
# one at a time instead
SAMPLE_AREA_MAX = 2_000_000


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


gdi32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                            wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFO), wintypes.UINT)
gdi32.GetDIBits.restype = ctypes.c_int
user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
user32.PrintWindow.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = (wintypes.POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND

GA_ROOT = 2

# PrintWindow asks the window to draw itself into a DC of our choosing, which is
# the only way to see a window that is not the one in front. CLIENTONLY drops the
# title bar and border so the result is in client coordinates; RENDERFULLCONTENT
# is what makes a DirectX or composited surface come along, and without it a game
# hands back an empty rectangle.
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002


def window_title(hwnd: int) -> str:
    """That window's title, or "" — for naming whatever is covering the game."""
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def list_windows() -> list[tuple[int, str]]:
    """Every visible window that has a title."""
    found: list[tuple[int, str]] = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        found.append((hwnd, buffer.value))
        return True

    user32.EnumWindows(_ENUM_PROC(callback), 0)
    return found


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _scored(fragment: str) -> list[tuple[tuple[int, int], int, str]]:
    """((rank, client area), hwnd, title) for every window that matches."""
    needle = (fragment or "").lower().strip()
    if not needle:
        return []
    own = os.getpid()
    found = []
    for hwnd, title in list_windows():
        lowered = title.lower()
        if needle not in lowered or window_pid(hwnd) == own:
            continue
        rank = 3 if lowered == needle else 2 if lowered.startswith(needle) else 1
        rect = client_rect(hwnd)
        found.append(((rank, rect[2] * rect[3] if rect else 0), hwnd, title))
    return found


def tied_windows(fragment: str) -> list[str]:
    """
    Titles of the windows that score highest, when more than one does.

    A tie at the top means the score has run out of ways to choose and the
    winner falls out of enumeration order, i.e. out of which window is in
    front. That is worth saying out loud rather than picking quietly: two ARK
    windows — one installed, one streamed — tie exactly.
    """
    scored = _scored(fragment)
    if not scored:
        return []
    top = max(score for score, _hwnd, _title in scored)
    return [title for score, _hwnd, title in scored if score == top]


def find_window(fragment: str) -> int | None:
    """
    Best window whose title contains `fragment`, case-insensitive.

    "First match" was too naive: a folder called ark-farm-macro open in
    Explorer outranked the game and the macro happily aimed at it. Candidates
    are now scored — an exact title beats a prefix beats a substring, and the
    larger client area breaks ties, because a game window is the big one.
    Our own windows never qualify.
    """
    needle = (fragment or "").lower().strip()
    if not needle:
        return None

    own = os.getpid()
    best: int | None = None
    best_score = (-1, -1)
    for hwnd, title in list_windows():
        lowered = title.lower()
        if needle not in lowered:
            continue
        if window_pid(hwnd) == own:
            continue
        rank = 3 if lowered == needle else 2 if lowered.startswith(needle) else 1
        rect = client_rect(hwnd)
        area = rect[2] * rect[3] if rect else 0
        if (rank, area) > best_score:
            best_score = (rank, area)
            best = hwnd
    return best


def is_window(hwnd: int) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def is_foreground(hwnd: int) -> bool:
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd


def dpi_awareness() -> str:
    """
    How Windows is reporting coordinates to this process, in plain words.

    Everything the app stores is a physical screen pixel, and Windows only hands
    those to an aware process. On anything but "per-monitor" a scaled display
    silently reports something else, so this is worth being able to read out
    rather than assume.
    """
    try:
        context = user32.GetThreadDpiAwarenessContext()
        awareness = user32.GetAwarenessFromDpiAwarenessContext(context)
    except (AttributeError, OSError):
        return "unknown (Windows older than 10 1607)"
    return {0: "unaware — coordinates will be virtualised",
            1: "system",
            2: "per-monitor",
            3: "per-monitor v2"}.get(awareness, f"unrecognised ({awareness})")


def screen_size() -> tuple[int, int]:
    """Physical resolution of the primary monitor (the process is DPI aware)."""
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def screen_region(x: int, y: int, width: int,
                  height: int) -> list[tuple[int, int, int]] | None:
    """
    Row-major RGB of a screen rectangle, or None when it cannot be read.

    Blitting the rectangle into a bitmap and reading that is not the obvious way
    to get a few pixels — GetPixel is one call. It is the way that works. A
    streaming client (GeForce NOW, Moonlight) and a game in borderless both put
    their picture on a layered or overlay surface, and GetPixel on the desktop DC
    does not see those at all: it hands back CLR_INVALID, the caller reads that
    as "this screen cannot be read", and every check that depends on the screen
    quietly stops working. CAPTUREBLT is what includes those surfaces, and it is
    the same path the area picker's screenshot takes — which is why picking an
    area worked on machines where the probes were blind.
    """
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        return None
    screen = user32.GetDC(None)
    if not screen:
        return None
    memory = bitmap = None
    pixels = None
    try:
        memory = gdi32.CreateCompatibleDC(screen)
        if not memory:
            return None
        bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
        if not bitmap:
            return None
        previous = gdi32.SelectObject(memory, bitmap)
        copied = gdi32.BitBlt(memory, 0, 0, width, height, screen,
                              int(x), int(y), SRCCOPY | CAPTUREBLT)
        if copied:
            info = BITMAPINFO()
            info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height        # negative: rows top-down
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = BI_RGB
            buffer = (ctypes.c_ubyte * (width * height * 4))()
            if gdi32.GetDIBits(memory, bitmap, 0, height, buffer,
                               ctypes.byref(info), DIB_RGB_COLORS) == height:
                pixels = buffer
        gdi32.SelectObject(memory, previous)
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
    if pixels is None:
        return None
    return [(pixels[i + 2], pixels[i + 1], pixels[i])
            for i in range(0, len(pixels), 4)]


def screen_pixel(x: int, y: int) -> tuple[int, int, int] | None:
    """
    Colour on screen at (x, y), or None when it cannot be read.

    This is how the engine tells an open inventory from a closed one: no way to
    ask the game, but the panel is right there on screen. Exclusive fullscreen
    hands back nothing, which is one more reason the app asks for borderless.
    """
    region = screen_region(x, y, 1, 1)
    if region:
        return region[0]
    # The blit could not run at all. GetPixel sees less, but less is not none.
    hdc = user32.GetDC(None)
    if not hdc:
        return None
    try:
        value = gdi32.GetPixel(hdc, int(x), int(y))
    finally:
        user32.ReleaseDC(None, hdc)
    if value == CLR_INVALID:
        return None
    return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF


def screen_samples(points) -> list[tuple[int, int, int]] | None:
    """
    Colours at several screen points, read in one grab where that is sensible.

    The probes ask for a few dozen points inside a small box. Reading them one
    at a time is a few dozen blits of the whole desktop; reading the box once
    and picking the points out of it is one.
    """
    spots = [(int(x), int(y)) for x, y in points]
    if not spots:
        return []
    left = min(x for x, _ in spots)
    top = min(y for _, y in spots)
    width = max(x for x, _ in spots) - left + 1
    height = max(y for _, y in spots) - top + 1
    if width * height <= SAMPLE_AREA_MAX:
        region = screen_region(left, top, width, height)
        if region is not None and len(region) == width * height:
            return [region[(y - top) * width + (x - left)] for x, y in spots]
    read = []
    for x, y in spots:
        colour = screen_pixel(x, y)
        if colour is None:
            return None
        read.append(colour)
    return read


def root_of(hwnd: int) -> int:
    """The top-level window a handle belongs to, or 0."""
    if not hwnd:
        return 0
    return int(user32.GetAncestor(int(hwnd), GA_ROOT) or hwnd)


def window_at(x: int, y: int) -> int:
    """The top-level window actually drawn at that screen point, or 0."""
    top = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if not top:
        return 0
    return root_of(top)


def visible_at(hwnd: int, points) -> bool:
    """
    Whether `hwnd` is what is on screen at every one of those points.

    Not focused is not the same as not visible, and conflating the two is what
    made background delivery blind. A second monitor is the ordinary case: the
    game sits in plain sight on one screen while you work or play on the other,
    nothing covering it, and the desktop pixels there *are* the game. Asking
    Windows what is drawn at the point settles it without guessing.
    """
    if not hwnd:
        return False
    return all(window_at(x, y) == int(hwnd) for x, y in points)


def window_shot(hwnd: int) -> tuple[list[tuple[int, int, int]], int, int] | None:
    """
    The window's own client area as pixels, even when it is behind others.

    (colours, width, height), row-major from the client top-left. None when the
    window will not draw itself.

    Reading the *screen* is no use to a macro playing a game in the background:
    those coordinates belong to whatever is actually in front. But a window can
    be asked to paint itself into a bitmap regardless of who has focus, which is
    what PrintWindow does, and RENDERFULLCONTENT is what makes it work for a
    game rather than returning an empty rectangle.

    It is not guaranteed. A window rendering through a swapchain it never
    presents to the DWM has nothing to hand over, and exclusive fullscreen has
    nothing at all — those come back None, and the caller treats that the same
    way it treats an unreadable screen.
    """
    rect = client_rect(hwnd)
    if not rect:
        return None
    _x, _y, width, height = rect
    if width <= 0 or height <= 0 or width * height > SAMPLE_AREA_MAX:
        return None
    screen = user32.GetDC(None)
    if not screen:
        return None
    memory = bitmap = None
    pixels = None
    try:
        memory = gdi32.CreateCompatibleDC(screen)
        if not memory:
            return None
        bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
        if not bitmap:
            return None
        previous = gdi32.SelectObject(memory, bitmap)
        drawn = user32.PrintWindow(hwnd, memory,
                                   PW_CLIENTONLY | PW_RENDERFULLCONTENT)
        if drawn:
            info = BITMAPINFO()
            info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = BI_RGB
            buffer = (ctypes.c_ubyte * (width * height * 4))()
            if gdi32.GetDIBits(memory, bitmap, 0, height, buffer,
                               ctypes.byref(info), DIB_RGB_COLORS) == height:
                pixels = buffer
        gdi32.SelectObject(memory, previous)
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
    if pixels is None:
        return None
    return ([(pixels[i + 2], pixels[i + 1], pixels[i])
             for i in range(0, len(pixels), 4)], width, height)


def window_samples(hwnd: int, points) -> list[tuple[int, int, int]] | None:
    """
    Those SCREEN points read out of the window itself.

    The points were captured while the game was in front, so they are screen
    coordinates; the window may have moved since, and in the background it is
    behind something else entirely. Converting each one through the window's
    current position is what keeps a stored point pointing at the same button —
    the same conversion the posted clicks already go through.
    """
    shot = window_shot(hwnd)
    if shot is None:
        return None
    pixels, width, height = shot
    read = []
    for x, y in points:
        local_x, local_y = screen_to_client(hwnd, int(x), int(y))
        if not (0 <= local_x < width and 0 <= local_y < height):
            return None
        read.append(pixels[local_y * width + local_x])
    return read


def client_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """(x, y, width, height) of the client area, in screen coordinates."""
    if not is_window(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    return origin.x, origin.y, width, height


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = wintypes.POINT(int(x), int(y))
    user32.ScreenToClient(hwnd, ctypes.byref(point))
    return point.x, point.y


def _lparam(x: int, y: int) -> int:
    return (int(y) << 16) | (int(x) & 0xFFFF)


# --------------------------------------------------------- background send

def post_click(hwnd: int, x: int, y: int, button: str = "left",
               hold: float = 0.03) -> None:
    """PostMessage click, in CLIENT coordinates of the window."""
    packed = _lparam(x, y)
    if button == "right":
        down, up, flag = WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON
    else:
        down, up, flag = WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, packed)
    user32.PostMessageW(hwnd, down, flag, packed)
    time.sleep(hold)
    user32.PostMessageW(hwnd, up, 0, packed)


def post_key(hwnd: int, vk: int, hold: float = 0.03) -> None:
    scan = _scan(vk)
    down_param = 1 | (scan << 16)
    up_param = down_param | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, down_param)
    time.sleep(hold)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, up_param)


def post_text(hwnd: int, text: str, delay: float = 0.03) -> None:
    for char in text:
        user32.PostMessageW(hwnd, WM_CHAR, ord(char), 1)
        time.sleep(delay)
