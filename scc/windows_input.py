"""Native Windows keyboard and mouse output using Win32 SendInput."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from scc.uinput import Keys, Mouse, Rels

if sys.platform != "win32":
	raise ImportError("scc.windows_input is only available on Windows")

log = logging.getLogger("windows_input")

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002
WHEEL_DELTA = 120


class MOUSEINPUT(ctypes.Structure):
	_fields_ = [
		("dx", wintypes.LONG),
		("dy", wintypes.LONG),
		("mouseData", wintypes.DWORD),
		("dwFlags", wintypes.DWORD),
		("time", wintypes.DWORD),
		("dwExtraInfo", ctypes.c_size_t),
	]


class KEYBDINPUT(ctypes.Structure):
	_fields_ = [
		("wVk", wintypes.WORD),
		("wScan", wintypes.WORD),
		("dwFlags", wintypes.DWORD),
		("time", wintypes.DWORD),
		("dwExtraInfo", ctypes.c_size_t),
	]


class HARDWAREINPUT(ctypes.Structure):
	_fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
	_fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
	_anonymous_ = ("data",)
	_fields_ = [("type", wintypes.DWORD), ("data", _INPUTUNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT


def _send(*events: INPUT) -> None:
	if not events:
		return
	array = (INPUT * len(events))(*events)
	sent = _user32.SendInput(len(array), array, ctypes.sizeof(INPUT))
	if sent != len(array):
		error = ctypes.get_last_error()
		log.error("SendInput sent %d of %d events (Windows error %d)", sent, len(array), error)


def _keyboard_input(vk: int, pressed: bool) -> INPUT:
	return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, 0 if pressed else KEYEVENTF_KEYUP, 0, 0))


def _mouse_input(flags: int, data: int = 0, dx: int = 0, dy: int = 0) -> INPUT:
	return INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx, dy, ctypes.c_uint32(data).value, flags, 0, 0))


# Linux input key names to Windows virtual-key codes. Letters, digits and F-keys
# are handled algorithmically below.
_VK = {
	"KEY_ESC": 0x1B, "KEY_TAB": 0x09, "KEY_ENTER": 0x0D, "KEY_BACKSPACE": 0x08, "KEY_SPACE": 0x20,
	"KEY_INSERT": 0x2D, "KEY_DELETE": 0x2E, "KEY_HOME": 0x24, "KEY_END": 0x23,
	"KEY_PAGEUP": 0x21, "KEY_PAGEDOWN": 0x22, "KEY_LEFT": 0x25, "KEY_UP": 0x26,
	"KEY_RIGHT": 0x27, "KEY_DOWN": 0x28, "KEY_CAPSLOCK": 0x14, "KEY_NUMLOCK": 0x90,
	"KEY_SCROLLLOCK": 0x91, "KEY_PAUSE": 0x13, "KEY_SYSRQ": 0x2C,
	"KEY_LEFTSHIFT": 0xA0, "KEY_RIGHTSHIFT": 0xA1, "KEY_LEFTCTRL": 0xA2, "KEY_RIGHTCTRL": 0xA3,
	"KEY_LEFTALT": 0xA4, "KEY_RIGHTALT": 0xA5, "KEY_LEFTMETA": 0x5B, "KEY_RIGHTMETA": 0x5C,
	"KEY_GRAVE": 0xC0, "KEY_MINUS": 0xBD, "KEY_EQUAL": 0xBB, "KEY_LEFTBRACE": 0xDB,
	"KEY_RIGHTBRACE": 0xDD, "KEY_BACKSLASH": 0xDC, "KEY_SEMICOLON": 0xBA,
	"KEY_APOSTROPHE": 0xDE, "KEY_COMMA": 0xBC, "KEY_DOT": 0xBE, "KEY_SLASH": 0xBF,
	"KEY_102ND": 0xE2, "KEY_COMPOSE": 0x5D,
	"KEY_KP0": 0x60, "KEY_KP1": 0x61, "KEY_KP2": 0x62, "KEY_KP3": 0x63, "KEY_KP4": 0x64,
	"KEY_KP5": 0x65, "KEY_KP6": 0x66, "KEY_KP7": 0x67, "KEY_KP8": 0x68, "KEY_KP9": 0x69,
	"KEY_KPASTERISK": 0x6A, "KEY_KPPLUS": 0x6B, "KEY_KPMINUS": 0x6D, "KEY_KPDOT": 0x6E,
	"KEY_KPSLASH": 0x6F, "KEY_KPENTER": 0x0D,
	"KEY_MUTE": 0xAD, "KEY_VOLUMEDOWN": 0xAE, "KEY_VOLUMEUP": 0xAF,
	"KEY_NEXTSONG": 0xB0, "KEY_PREVIOUSSONG": 0xB1, "KEY_PLAYPAUSE": 0xB3,
	"KEY_BACK": 0xA6, "KEY_FORWARD": 0xA7, "KEY_HOMEPAGE": 0xAC,
}


def _virtual_key(key: int) -> int | None:
	try:
		name = Keys(key).name
	except ValueError:
		return None
	if len(name) == 5 and name.startswith("KEY_") and name[-1].isalpha():
		return ord(name[-1])
	if len(name) == 5 and name.startswith("KEY_") and name[-1].isdigit():
		return ord(name[-1])
	if name.startswith("KEY_F") and name[5:].isdigit():
		number = int(name[5:])
		if 1 <= number <= 24:
			return 0x6F + number
	return _VK.get(name)


class WindowsKeyboard:
	"""Keyboard output compatible with the mapper's uinput Keyboard API."""

	def __init__(self, name=None) -> None:
		self.name = name
		self._pressed: set[int] = set()
		self._warned: set[int] = set()

	def _event(self, key: int, pressed: bool) -> INPUT | None:
		vk = _virtual_key(key)
		if vk is None:
			if key not in self._warned:
				log.warning("No Windows key mapping for %r", key)
				self._warned.add(key)
			return None
		return _keyboard_input(vk, pressed)

	def pressEvent(self, keys: list) -> None:
		new = [key for key in keys if key not in self._pressed]
		_send(*(event for key in new if (event := self._event(key, True)) is not None))
		self._pressed.update(new)

	def releaseEvent(self, keys: list | None = None) -> None:
		rem = [key for key in keys if key in self._pressed] if keys else list(self._pressed)
		_send(*(event for key in rem if (event := self._event(key, False)) is not None))
		self._pressed.difference_update(rem)

	def keyEvent(self, key: int, val: int) -> None:
		event = self._event(key, bool(val))
		if event is not None:
			_send(event)

	def keyManaged(self, key: int) -> bool:
		return _virtual_key(key) is not None

	def synEvent(self) -> None:
		pass


_MOUSE_BUTTONS = {
	Keys.BTN_LEFT: (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, 0),
	Keys.BTN_RIGHT: (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, 0),
	Keys.BTN_MIDDLE: (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, 0),
	Keys.BTN_SIDE: (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, XBUTTON1),
	Keys.BTN_EXTRA: (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, XBUTTON2),
}


class WindowsMouse(Mouse):
	"""Mouse output retaining SCC's existing movement and scroll scaling."""

	def __init__(self, name=None) -> None:
		self.name = name
		self.updateParams()
		self.updateScrollParams()
		self.reset()

	def reset(self) -> None:
		super().reset()
		self._pending_x = 0
		self._pending_y = 0
		self._pending_wheel = 0
		self._pending_hwheel = 0

	def keyEvent(self, key: int, val: int) -> None:
		button = _MOUSE_BUTTONS.get(key)
		if button is not None:
			down, up, data = button
			_send(_mouse_input(down if val else up, data=data))

	def relEvent(self, rel: int, val: int) -> None:
		if rel == Rels.REL_X:
			self._pending_x += val
		elif rel == Rels.REL_Y:
			self._pending_y += val
		elif rel == Rels.REL_WHEEL:
			self._pending_wheel += val * WHEEL_DELTA
		elif rel == Rels.REL_HWHEEL:
			self._pending_hwheel += val * WHEEL_DELTA

	def synEvent(self) -> None:
		events = []
		if self._pending_x or self._pending_y:
			events.append(_mouse_input(MOUSEEVENTF_MOVE, dx=self._pending_x, dy=self._pending_y))
		if self._pending_wheel:
			events.append(_mouse_input(MOUSEEVENTF_WHEEL, data=self._pending_wheel))
		if self._pending_hwheel:
			events.append(_mouse_input(MOUSEEVENTF_HWHEEL, data=self._pending_hwheel))
		self._pending_x = self._pending_y = self._pending_wheel = self._pending_hwheel = 0
		_send(*events)

	def keyManaged(self, key: int) -> bool:
		return key in _MOUSE_BUTTONS

	def relManaged(self, rel: int) -> bool:
		return rel in (Rels.REL_X, Rels.REL_Y, Rels.REL_WHEEL, Rels.REL_HWHEEL)
