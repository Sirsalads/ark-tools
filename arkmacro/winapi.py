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
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

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


def _scan(vk: int) -> int:
    return user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)


def key_down(vk: int) -> None:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0)
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, _scan(vk), flags, 0, 0)))


def key_up(vk: int) -> None:
    flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if vk in _EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, _scan(vk), flags, 0, 0)))


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


def find_window(fragment: str) -> int | None:
    """First HWND whose title contains `fragment`, case-insensitive."""
    needle = (fragment or "").lower().strip()
    if not needle:
        return None
    for hwnd, title in list_windows():
        if needle in title.lower():
            return hwnd
    return None


def is_window(hwnd: int) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def is_foreground(hwnd: int) -> bool:
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd


def screen_size() -> tuple[int, int]:
    """Physical resolution of the primary monitor (the process is DPI aware)."""
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


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
