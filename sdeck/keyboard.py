from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QKeyCombination, Qt
from PySide6.QtGui import QKeySequence


ALIASES = {
    "CTRL": "KEY_LEFTCTRL",
    "CONTROL": "KEY_LEFTCTRL",
    "ALT": "KEY_LEFTALT",
    "SHIFT": "KEY_LEFTSHIFT",
    "SUPER": "KEY_LEFTMETA",
    "META": "KEY_LEFTMETA",
    "WIN": "KEY_LEFTMETA",
    "ENTER": "KEY_ENTER",
    "RETURN": "KEY_ENTER",
    "ESC": "KEY_ESC",
    "ESCAPE": "KEY_ESC",
    "SPACE": "KEY_SPACE",
    "TAB": "KEY_TAB",
    "BACKSPACE": "KEY_BACKSPACE",
    "DELETE": "KEY_DELETE",
    "INSERT": "KEY_INSERT",
    "HOME": "KEY_HOME",
    "END": "KEY_END",
    "PAGEUP": "KEY_PAGEUP",
    "PAGEDOWN": "KEY_PAGEDOWN",
    "UP": "KEY_UP",
    "DOWN": "KEY_DOWN",
    "LEFT": "KEY_LEFT",
    "RIGHT": "KEY_RIGHT",
    "VOLUMEUP": "KEY_VOLUMEUP",
    "VOLUMEDOWN": "KEY_VOLUMEDOWN",
    "MUTE": "KEY_MUTE",
    "PLAYPAUSE": "KEY_PLAYPAUSE",
    "STOP": "KEY_STOPCD",
    "NEXT": "KEY_NEXTSONG",
    "PREVIOUS": "KEY_PREVIOUSSONG",
}


class ShortcutError(ValueError):
    pass


MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr,
}


def shortcut_from_qt(key: int, modifiers: Qt.KeyboardModifier) -> str:
    """Return the same portable spelling accepted by ``shortcut_names``."""
    if Qt.Key(key) in MODIFIER_KEYS:
        return ""
    supported = (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.MetaModifier
    )
    combination = QKeyCombination(modifiers & supported, Qt.Key(key))
    return QKeySequence(combination).toString(QKeySequence.SequenceFormat.PortableText)


def shortcut_names(shortcut: str) -> list[str]:
    tokens = [token.strip().upper().replace(" ", "") for token in shortcut.split("+")]
    if not tokens or any(not token for token in tokens):
        raise ShortcutError("The keyboard shortcut is empty")
    result: list[str] = []
    for token in tokens:
        name = ALIASES.get(token, token if token.startswith("KEY_") else f"KEY_{token}")
        if name not in result:
            result.append(name)
    return result


@dataclass
class VirtualKeyboard:
    name: str = "YASDEC Virtual Keyboard"

    def __post_init__(self) -> None:
        self._device = None
        self._ecodes = None

    @property
    def available(self) -> bool:
        try:
            self._ensure_device()
        except (OSError, ImportError):
            return False
        return True

    def send(self, shortcut: str) -> None:
        names = shortcut_names(shortcut)
        self._ensure_device()
        assert self._device is not None and self._ecodes is not None
        codes: list[int] = []
        for name in names:
            code = getattr(self._ecodes, name, None)
            if not isinstance(code, int):
                raise ShortcutError(f"Unknown key: {name.removeprefix('KEY_')}")
            codes.append(code)
        for code in codes:
            self._device.write(self._ecodes.EV_KEY, code, 1)
        self._device.syn()
        for code in reversed(codes):
            self._device.write(self._ecodes.EV_KEY, code, 0)
        self._device.syn()

    def _ensure_device(self) -> None:
        if self._device is not None:
            return
        try:
            from evdev import UInput, ecodes
        except ImportError as exc:
            raise ImportError("python-evdev is not installed") from exc
        key_codes = sorted({
            value for name, value in vars(ecodes).items()
            if name.startswith("KEY_") and name != "KEY_MAX" and isinstance(value, int) and 0 < value < ecodes.KEY_MAX
        })
        self._device = UInput({ecodes.EV_KEY: key_codes}, name=self.name, version=0x1)
        self._ecodes = ecodes

    def close(self) -> None:
        if self._device is not None:
            self._device.close()
            self._device = None
            self._ecodes = None
