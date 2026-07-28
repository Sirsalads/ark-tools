"""
Global hotkeys through RegisterHotKey.

RegisterHotKey delivers WM_HOTKEY to the thread that registered it, so both the
registration and the message loop live on this dedicated thread. The UI only
receives the signal.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

from .winapi import vk_from_name

user32 = ctypes.WinDLL("user32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_APP_REGISTER = 0x8000 + 1
WM_APP_QUIT = 0x8000 + 2

_MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT, "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN,
}


def parse(combo: str) -> tuple[int, int] | None:
    """'Ctrl+Shift+F6' -> (modifiers, vk). None when invalid."""
    if not combo:
        return None
    modifiers = 0
    vk = None
    for part in combo.replace(" ", "").split("+"):
        lowered = part.lower()
        if lowered in _MODIFIERS:
            modifiers |= _MODIFIERS[lowered]
        else:
            vk = vk_from_name(lowered)
    if vk is None:
        return None
    return modifiers | MOD_NOREPEAT, vk


class HotkeyManager(QObject):
    """Registers combinations and emits `triggered(name)` when pressed."""

    triggered = Signal(str)
    failed = Signal(str, str)  # name, combo

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._ready = threading.Event()
        self._pending: dict[str, str] = {}
        self._ids: dict[int, str] = {}
        self._lock = threading.Lock()

    # -------------------------------------------------------------- api
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="hotkeys")
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_APP_QUIT, 0, 0)

    def apply(self, mapping: dict[str, str]) -> None:
        """Replace every registration with the {name: combo} map."""
        with self._lock:
            self._pending = dict(mapping)
        already_running = bool(self._thread and self._thread.is_alive())
        self.start()
        if already_running and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_APP_REGISTER, 0, 0)

    # ---------------------------------------------------------- internal
    def _unregister_all(self) -> None:
        for hotkey_id in list(self._ids):
            user32.UnregisterHotKey(None, hotkey_id)
        self._ids.clear()

    def _register_pending(self) -> None:
        self._unregister_all()
        with self._lock:
            mapping = dict(self._pending)
        for index, (name, combo) in enumerate(mapping.items(), start=1):
            parsed = parse(combo)
            if not parsed:
                self.failed.emit(name, combo)
                continue
            modifiers, vk = parsed
            if user32.RegisterHotKey(None, index, modifiers, vk):
                self._ids[index] = name
            else:
                self.failed.emit(name, combo)

    def _run(self) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        # force the thread message queue into existence
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self._register_pending()
        self._ready.set()

        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result in (0, -1):  # WM_QUIT or error
                break
            if message.message == WM_HOTKEY:
                name = self._ids.get(message.wParam)
                if name:
                    self.triggered.emit(name)
            elif message.message == WM_APP_REGISTER:
                self._register_pending()
            elif message.message == WM_APP_QUIT:
                break
        self._unregister_all()
