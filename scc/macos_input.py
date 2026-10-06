"""macOS keyboard and mouse output through Quartz, without Linux uinput."""

from __future__ import annotations

import ctypes
import logging

from scc.uinput import Keyboard, Keys, Mouse, Rels

log = logging.getLogger("macos_input")


class CGPoint(ctypes.Structure):
	_fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
_cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")


def _bind(lib, name, result, *args):
	function = getattr(lib, name)
	function.restype = result
	function.argtypes = args
	return function


_ptr = ctypes.c_void_p
_create = _bind(_cg, "CGEventCreate", _ptr, _ptr)
_location = _bind(_cg, "CGEventGetLocation", CGPoint, _ptr)
_keyboard = _bind(_cg, "CGEventCreateKeyboardEvent", _ptr, _ptr, ctypes.c_uint16, ctypes.c_bool)
_mouse = _bind(_cg, "CGEventCreateMouseEvent", _ptr, _ptr, ctypes.c_uint32, CGPoint, ctypes.c_uint32)
_scroll = _bind(_cg, "CGEventCreateScrollWheelEvent", _ptr, _ptr, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32)
_flags = _bind(_cg, "CGEventSetFlags", None, _ptr, ctypes.c_uint64)
_integer = _bind(_cg, "CGEventSetIntegerValueField", None, _ptr, ctypes.c_uint32, ctypes.c_int64)
_post = _bind(_cg, "CGEventPost", None, ctypes.c_uint32, _ptr)
_release = _bind(_cf, "CFRelease", None, _ptr)
_access = _bind(_cg, "CGPreflightPostEventAccess", ctypes.c_bool)


def _check_access() -> None:
	if not _access():
		log.warning("macOS input output requires Accessibility permission for the application launching scc-daemon in System Settings > Privacy & Security")


def _send(event) -> None:
	if not event:
		log.warning("Quartz could not create an input event")
		return
	try:
		_post(0, event)
	finally:
		_release(event)


def _position():
	event = _create(None)
	if not event:
		return None
	try:
		return _location(event)
	finally:
		_release(event)


# Physical macOS virtual key codes (independent of the active keyboard layout).
_CODES = {
	"A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6, "X": 7,
	"C": 8, "V": 9, "B": 11, "Q": 12, "W": 13, "E": 14, "R": 15,
	"Y": 16, "T": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
	"5": 23, "EQUAL": 24, "9": 25, "7": 26, "MINUS": 27, "8": 28,
	"0": 29, "RIGHTBRACE": 30, "O": 31, "U": 32, "LEFTBRACE": 33,
	"I": 34, "P": 35, "ENTER": 36, "L": 37, "J": 38, "APOSTROPHE": 39,
	"K": 40, "SEMICOLON": 41, "BACKSLASH": 42, "COMMA": 43, "SLASH": 44,
	"N": 45, "M": 46, "DOT": 47, "TAB": 48, "SPACE": 49, "GRAVE": 50,
	"BACKSPACE": 51, "ESC": 53, "RIGHTMETA": 54, "LEFTMETA": 55,
	"LEFTSHIFT": 56, "CAPSLOCK": 57, "LEFTALT": 58, "LEFTCTRL": 59,
	"RIGHTSHIFT": 60, "RIGHTALT": 61, "RIGHTCTRL": 62, "102ND": 10,
	"KPDOT": 65, "KPASTERISK": 67, "KPPLUS": 69, "NUMLOCK": 71,
	"KPSLASH": 75, "KPENTER": 76, "KPMINUS": 78, "KPEQUAL": 81,
	"KP0": 82, "KP1": 83, "KP2": 84, "KP3": 85, "KP4": 86, "KP5": 87,
	"KP6": 88, "KP7": 89, "KP8": 91, "KP9": 92,
	"F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96, "F6": 97,
	"F7": 98, "F8": 100, "F9": 101, "F10": 109, "F11": 103, "F12": 111,
	"F13": 105, "F14": 107, "F15": 113, "F16": 106, "F17": 64,
	"F18": 79, "F19": 80, "F20": 90, "INSERT": 114, "HOME": 115,
	"PAGEUP": 116, "DELETE": 117, "END": 119, "PAGEDOWN": 121,
	"LEFT": 123, "RIGHT": 124, "DOWN": 125, "UP": 126,
}
_KEYCODES = {Keys["KEY_" + name]: code for name, code in _CODES.items()}
_MODIFIERS = {
	Keys.KEY_LEFTSHIFT: 1 << 17, Keys.KEY_RIGHTSHIFT: 1 << 17,
	Keys.KEY_LEFTCTRL: 1 << 18, Keys.KEY_RIGHTCTRL: 1 << 18,
	Keys.KEY_LEFTALT: 1 << 19, Keys.KEY_RIGHTALT: 1 << 19,
	Keys.KEY_LEFTMETA: 1 << 20, Keys.KEY_RIGHTMETA: 1 << 20,
}


class MacOSKeyboard(Keyboard):
	def __init__(self, name=None) -> None:
		self.name = name
		self._pressed = set()
		self._modifiers = set()
		self._warned = set()
		_check_access()

	def keyEvent(self, key, val) -> None:
		code = _KEYCODES.get(key)
		if code is None:
			if key not in self._warned:
				log.warning("No macOS key mapping for %r", key)
				self._warned.add(key)
			return
		if val:
			self._modifiers.add(key)
		else:
			self._modifiers.discard(key)
		event = _keyboard(None, code, bool(val))
		if event:
			flags = 0
			for modifier in self._modifiers:
				flags |= _MODIFIERS.get(modifier, 0)
			_flags(event, flags)
		_send(event)

	def keyManaged(self, key) -> bool:
		return key in _KEYCODES

	def scanEvent(self, *args):
		pass

	def synEvent(self):
		pass

	def __del__(self):
		pass


_BUTTONS = {Keys.BTN_LEFT: 0, Keys.BTN_RIGHT: 1, Keys.BTN_MIDDLE: 2, Keys.BTN_SIDE: 3, Keys.BTN_EXTRA: 4}


class MacOSMouse(Mouse):
	def __init__(self, name=None) -> None:
		self.name = name
		self._buttons = set()
		self.updateParams()
		self.updateScrollParams()
		self.reset()
		_check_access()

	def reset(self) -> None:
		super().reset()
		self._pending = {rel: 0 for rel in (Rels.REL_X, Rels.REL_Y, Rels.REL_WHEEL, Rels.REL_HWHEEL)}

	def keyEvent(self, key, val) -> None:
		button = _BUTTONS.get(key)
		position = _position() if button is not None else None
		if position is None:
			return
		if val:
			self._buttons.add(button)
		else:
			self._buttons.discard(button)
		down, up = (1, 2) if button == 0 else (3, 4) if button == 1 else (25, 26)
		_send(_mouse(None, down if val else up, position, button))

	def relEvent(self, rel, val) -> None:
		if rel in self._pending:
			self._pending[rel] += int(val)

	def synEvent(self) -> None:
		x, y = self._pending[Rels.REL_X], self._pending[Rels.REL_Y]
		if x or y:
			position = _position()
			if position is not None:
				position.x += x
				position.y += y
				button = min(self._buttons) if self._buttons else 0
				type_ = (6 if button == 0 else 7 if button == 1 else 27) if self._buttons else 5
				event = _mouse(None, type_, position, button)
				if event:
					_integer(event, 4, x)  # kCGMouseEventDeltaX
					_integer(event, 5, y)  # kCGMouseEventDeltaY
				_send(event)
		vertical, horizontal = self._pending[Rels.REL_WHEEL], self._pending[Rels.REL_HWHEEL]
		if vertical or horizontal:
			# Variadic arguments must have explicit types on Apple Silicon.
			_send(_scroll(None, 1, 2, vertical, ctypes.c_int32(horizontal)))
		for rel in self._pending:
			self._pending[rel] = 0

	def keyManaged(self, key) -> bool:
		return key in _BUTTONS

	def relManaged(self, rel) -> bool:
		return rel in self._pending

	def __del__(self):
		pass
