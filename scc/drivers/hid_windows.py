"""Generic Windows game-controller input using HIDAPI and gamecontrollerdb."""

from __future__ import annotations

import ctypes
import functools
import logging
import os
import re
import sys
import time
from enum import IntEnum
from typing import TYPE_CHECKING

if sys.platform == "win32":
	import hid
else:
	hid = None

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, ControllerFlags, SCButtons
from scc.controller import Controller
from scc.lib.hidparse import AXES, GenericDesktopPage, GlobalItem, ItemType, LocalItem, MainItem, UsagePage
from scc.lib.hidparse import parse_report_descriptor
from scc.paths import get_share_path
from scc.tools import find_library

if TYPE_CHECKING:
	from scc.sccdaemon import SCCDaemon

log = logging.getLogger("HIDWindows")

AXIS_COUNT = 24
BUTTON_COUNT = 32
SCAN_INTERVAL = 1.0
MAX_REPORTS_PER_TICK = 32
ALLOWED_SIZES = (1, 2, 4, 8, 16, 32)

SKIPPED_DEVICES = {
	(0x045E, 0x028E),  # SCC/ViGEm Xbox 360 output; avoid an input feedback loop
	(0x054C, 0x0CE6),  # DualSense
	(0x054C, 0x0DF2),  # DualSense Edge
}

SDL_BUTTON_NAMES = {
	"a": SCButtons.A,
	"b": SCButtons.B,
	"x": SCButtons.X,
	"y": SCButtons.Y,
	"back": SCButtons.BACK,
	"guide": SCButtons.C,
	"start": SCButtons.START,
	"leftstick": SCButtons.LSTICKPRESS,
	"rightstick": SCButtons.RSTICKPRESS,
	"leftshoulder": SCButtons.LB,
	"rightshoulder": SCButtons.RB,
}

SDL_AXIS_NAMES = {
	"leftx": "lstick_x",
	"lefty": "lstick_y",
	"rightx": "rstick_x",
	"righty": "rstick_y",
	"lefttrigger": "ltrig",
	"righttrigger": "rtrig",
}


class AxisType(IntEnum):
	LSTICK_X = 0
	LSTICK_Y = 1
	RSTICK_X = 2
	RSTICK_Y = 3
	LPAD_X = 4
	LPAD_Y = 5
	RPAD_X = 6
	RPAD_Y = 7
	LTRIG = 8
	RTRIG = 9
	DPAD_X = 22
	DPAD_Y = 23


AXIS_FIELD_INDEX = {
	"lstick_x": AxisType.LSTICK_X,
	"lstick_y": AxisType.LSTICK_Y,
	"rstick_x": AxisType.RSTICK_X,
	"rstick_y": AxisType.RSTICK_Y,
	"ltrig": AxisType.LTRIG,
	"rtrig": AxisType.RTRIG,
	"dpad_x": AxisType.DPAD_X,
	"dpad_y": AxisType.DPAD_Y,
}


class AxisMode(IntEnum):
	DISABLED = 0
	AXIS = 1
	AXIS_NO_SCALE = 2
	DPAD = 3
	HATSWITCH = 4


class AxisModeData(ctypes.Structure):
	_fields_ = [
		("button", ctypes.c_uint32),
		("scale", ctypes.c_float),
		("offset", ctypes.c_float),
		("clamp_min", ctypes.c_int),
		("clamp_max", ctypes.c_int),
		("deadzone", ctypes.c_float),
	]


class DPadModeData(ctypes.Structure):
	_fields_ = [
		("button", ctypes.c_uint32),
		("button1", ctypes.c_uint8),
		("button2", ctypes.c_uint8),
		("min", ctypes.c_int),
		("max", ctypes.c_int),
	]


class HatswitchModeData(ctypes.Structure):
	_fields_ = [("button", ctypes.c_uint32), ("min", ctypes.c_int), ("max", ctypes.c_int)]


class AxisDataUnion(ctypes.Union):
	_fields_ = [("axis", AxisModeData), ("dpad", DPadModeData), ("hatswitch", HatswitchModeData)]


class AxisData(ctypes.Structure):
	_fields_ = [
		("mode", ctypes.c_int),
		("byte_offset", ctypes.c_size_t),
		("bit_offset", ctypes.c_uint8),
		("size", ctypes.c_uint8),
		("data", AxisDataUnion),
	]


class ButtonData(ctypes.Structure):
	_fields_ = [
		("enabled", ctypes.c_bool),
		("byte_offset", ctypes.c_size_t),
		("bit_offset", ctypes.c_uint8),
		("size", ctypes.c_uint8),
		("button_count", ctypes.c_uint8),
		("button_map", ctypes.c_uint8 * BUTTON_COUNT),
	]


class HIDControllerInput(ctypes.Structure):
	_fields_ = [
		("buttons", ctypes.c_uint32),
		("lstick_x", ctypes.c_int32), ("lstick_y", ctypes.c_int32),
		("rstick_x", ctypes.c_int32), ("rstick_y", ctypes.c_int32),
		("lpad_x", ctypes.c_int32), ("lpad_y", ctypes.c_int32),
		("rpad_x", ctypes.c_int32), ("rpad_y", ctypes.c_int32),
		("ltrig", ctypes.c_int32), ("rtrig", ctypes.c_int32),
		("accel_x", ctypes.c_int32), ("accel_y", ctypes.c_int32), ("accel_z", ctypes.c_int32),
		("gpitch", ctypes.c_int32), ("groll", ctypes.c_int32), ("gyaw", ctypes.c_int32),
		("q1", ctypes.c_int32), ("q2", ctypes.c_int32), ("q3", ctypes.c_int32), ("q4", ctypes.c_int32),
		("cpad_x", ctypes.c_int32), ("cpad_y", ctypes.c_int32),
		("dpad_x", ctypes.c_int32), ("dpad_y", ctypes.c_int32),
	]


class HIDDecoder(ctypes.Structure):
	_fields_ = [
		("axes", AxisData * AXIS_COUNT),
		("buttons", ButtonData),
		("packet_size", ctypes.c_size_t),
		("old_state", HIDControllerInput),
		("state", HIDControllerInput),
	]


_lib = find_library("libhiddrv")
_lib.decode.restype = bool
_lib.decode.argtypes = [ctypes.POINTER(HIDDecoder), ctypes.c_char_p]


def _button_bit(button: SCButtons) -> int:
	value = int(button)
	return (value & -value).bit_length() - 1


def _guid_vid_pid(guid: str) -> tuple[int, int] | None:
	"""Extract VID/PID from the SDL Windows GUID byte layout."""
	try:
		data = bytes.fromhex(guid)
	except ValueError:
		return None
	if len(data) != 16:
		return None
	return int.from_bytes(data[4:6], "little"), int.from_bytes(data[8:10], "little")


@functools.lru_cache(maxsize=256)
def load_gamecontroller_mapping(vendor_id: int, product_id: int, product_name: str = "") -> tuple[str, dict] | None:
	"""Find the best Windows gamecontrollerdb entry for a USB VID/PID."""
	filename = os.path.join(get_share_path(), "gamecontrollerdb.txt")
	candidates = []
	with open(filename, encoding="utf-8") as database:
		for raw_line in database:
			line = raw_line.strip()
			if not line or line.startswith("#") or ",platform:Windows," not in line:
				continue
			parts = line.split(",")
			if len(parts) < 3 or _guid_vid_pid(parts[0]) != (vendor_id, product_id):
				continue
			mapping = {}
			for token in parts[2:]:
				if ":" in token:
					key, value = token.split(":", 1)
					mapping[key] = value
			candidates.append((parts[1], mapping))
	if not candidates:
		return None
	if product_name:
		name = product_name.casefold()
		for candidate in candidates:
			if candidate[0].casefold() == name:
				return candidate
	return candidates[0]


class DecoderBuilder:
	"""Translate an HID descriptor plus an SDL mapping into libhiddrv data."""

	def __init__(self, descriptor: bytes, mapping: dict) -> None:
		self.descriptor = descriptor
		self.mapping = mapping
		self.decoder = HIDDecoder()
		self.button_offset: tuple[int, int] | None = None
		self.button_count = 0

	def build(self) -> HIDDecoder:
		report_size = 1
		report_count = 0
		logical_min = 0
		logical_max = 255
		kind = None
		usage_page = None
		total = 0
		axis_number = 0
		hat_number = 0
		is_game_controller = False

		for item in parse_report_descriptor(self.descriptor, True):
			tag = item[0]
			if isinstance(tag, GlobalItem):
				if tag == GlobalItem.ReportSize:
					report_size = item[1]
				elif tag == GlobalItem.ReportCount:
					report_count = item[1]
				elif tag == GlobalItem.LogicalMinimum:
					logical_min = item[1]
				elif tag == GlobalItem.LogicalMaximum:
					logical_max = item[1]
				elif tag == GlobalItem.UsagePage:
					usage_page = item[1]
				elif tag == GlobalItem.ReportID and total == 0:
					# HIDAPI includes the report ID as byte zero in input reports.
					total = 8
			elif isinstance(tag, LocalItem) and tag == LocalItem.Usage:
				kind = item[1]
				if usage_page == UsagePage.GenericDesktopPage and kind in (
					GenericDesktopPage.Joystick,
					GenericDesktopPage.GamePad,
				):
					is_game_controller = True
			elif isinstance(tag, MainItem) and tag == MainItem.Input:
				bits = report_count * report_size
				if item[1] == ItemType.Constant:
					total += bits
				elif item[1] == ItemType.Data:
					if usage_page == UsagePage.ButtonPage:
						self._add_buttons(total, report_size, report_count)
						total += bits
					elif kind in AXES:
						for _ in range(report_count):
							self._add_axis(axis_number, total, report_size, logical_min, logical_max)
							axis_number += 1
							total += report_size
					elif kind == GenericDesktopPage.Hatswitch:
						self._add_hat(hat_number, total, report_size)
						hat_number += 1
						total += bits
					else:
						total += bits

		if not is_game_controller:
			raise ValueError("HID interface is not a joystick or gamepad")
		self.decoder.packet_size = (total + 7) // 8
		self._add_button_axes()
		return self.decoder

	def _add_axis(self, source: int, bit: int, size: int, minimum: int, maximum: int) -> None:
		if size not in ALLOWED_SIZES:
			return
		self._add_dpad_axis(source, bit, size, minimum, maximum)
		for sdl_name, target_name in SDL_AXIS_NAMES.items():
			binding = self.mapping.get(sdl_name, "")
			match = re.fullmatch(r"([+-]?)[aA](\d+)(~?)", binding)
			if match is None or int(match.group(2)) != source:
				continue
			invert = bool(match.group(3)) ^ target_name.endswith("_y")
			lo, hi = minimum, maximum
			center = (minimum + maximum) / 2
			if match.group(1) == "+":
				lo = center
			elif match.group(1) == "-":
				lo, hi = center, minimum
			if invert:
				lo, hi = hi, lo
			is_trigger = target_name in ("ltrig", "rtrig")
			if hi == lo:
				return
			if is_trigger:
				scale = 1.0 / (hi - lo)
				offset = -lo * scale
				clamp_min, clamp_max = 0, 255
			else:
				scale = 2.0 / (hi - lo)
				offset = -1.0 - lo * scale
				clamp_min, clamp_max = STICK_PAD_MIN, STICK_PAD_MAX
			index = int(AXIS_FIELD_INDEX[target_name])
			self.decoder.axes[index] = AxisData(
				mode=AxisMode.AXIS,
				byte_offset=bit // 8,
				bit_offset=bit % 8,
				size=size,
				data=AxisDataUnion(
					axis=AxisModeData(
						button=0,
						scale=scale,
						offset=offset,
						clamp_min=clamp_min,
						clamp_max=clamp_max,
						deadzone=0 if is_trigger else 0.05,
					),
				),
			)

	def _add_dpad_axis(self, source: int, bit: int, size: int, minimum: int, maximum: int) -> None:
		for target_name, negative_name, positive_name in (
			("dpad_x", "dpleft", "dpright"),
			("dpad_y", "dpdown", "dpup"),
		):
			selected = None
			for name, is_positive in ((positive_name, True), (negative_name, False)):
				match = re.fullmatch(r"([+-])[aA](\d+)(~?)", self.mapping.get(name, ""))
				if match is not None and int(match.group(2)) == source:
					selected = match, is_positive
					break
			if selected is None or maximum == minimum:
				continue
			match, is_positive = selected
			raw_positive = match.group(1) == "+"
			invert = (raw_positive != is_positive) ^ bool(match.group(3))
			lo, hi = (maximum, minimum) if invert else (minimum, maximum)
			scale = 2.0 / (hi - lo)
			offset = -1.0 - lo * scale
			index = int(AXIS_FIELD_INDEX[target_name])
			self.decoder.axes[index] = AxisData(
				mode=AxisMode.AXIS,
				byte_offset=bit // 8,
				bit_offset=bit % 8,
				size=size,
				data=AxisDataUnion(
					axis=AxisModeData(
						button=0,
						scale=scale,
						offset=offset,
						clamp_min=STICK_PAD_MIN,
						clamp_max=STICK_PAD_MAX,
						deadzone=0.25,
					),
				),
			)

	def _add_hat(self, source: int, bit: int, size: int) -> None:
		prefix = f"h{source}."
		if not any(value.startswith(prefix) for value in self.mapping.values()):
			return
		index = int(AxisType.DPAD_X)
		self.decoder.axes[index] = AxisData(
			mode=AxisMode.HATSWITCH,
			byte_offset=bit // 8,
			bit_offset=bit % 8,
			size=size,
			data=AxisDataUnion(hatswitch=HatswitchModeData(button=0, min=STICK_PAD_MIN, max=STICK_PAD_MAX)),
		)

	def _add_buttons(self, bit: int, size: int, count: int) -> None:
		if self.button_offset is not None or size != 1:
			return
		self.button_offset = bit // 8, bit % 8
		self.button_count = min(count, BUTTON_COUNT)
		button_map = [BUTTON_COUNT - 1] * BUTTON_COUNT
		for name, button in SDL_BUTTON_NAMES.items():
			match = re.fullmatch(r"b(\d+)", self.mapping.get(name, ""))
			if match and int(match.group(1)) < self.button_count:
				button_map[int(match.group(1))] = _button_bit(button)
		self.decoder.buttons = ButtonData(
			enabled=True,
			byte_offset=bit // 8,
			bit_offset=bit % 8,
			size=8 if count < 8 else 32,
			button_count=self.button_count,
			button_map=(ctypes.c_uint8 * BUTTON_COUNT)(*button_map),
		)

	def _add_button_axes(self) -> None:
		if self.button_offset is None:
			return
		byte_offset, bit_offset = self.button_offset
		for target_name, negative_name, positive_name in (
			("dpad_x", "dpleft", "dpright"),
			("dpad_y", "dpdown", "dpup"),
		):
			negative = self._button_number(self.mapping.get(negative_name, ""))
			positive = self._button_number(self.mapping.get(positive_name, ""))
			if negative is None or positive is None:
				continue
			index = int(AXIS_FIELD_INDEX[target_name])
			self.decoder.axes[index] = AxisData(
				mode=AxisMode.DPAD,
				byte_offset=byte_offset,
				bit_offset=bit_offset,
				size=32,
				data=AxisDataUnion(
					dpad=DPadModeData(button=0, button1=negative, button2=positive, min=STICK_PAD_MIN, max=STICK_PAD_MAX),
				),
			)

		for target_name, button_name, sc_button in (
			("ltrig", "lefttrigger", SCButtons.LT),
			("rtrig", "righttrigger", SCButtons.RT),
		):
			source = self._button_number(self.mapping.get(button_name, ""))
			if source is None:
				continue
			index = int(AXIS_FIELD_INDEX[target_name])
			self.decoder.axes[index] = AxisData(
				mode=AxisMode.DPAD,
				byte_offset=byte_offset,
				bit_offset=bit_offset,
				size=32,
				data=AxisDataUnion(
					dpad=DPadModeData(
						button=int(sc_button), button1=source, button2=source, min=255, max=255,
					),
				),
			)

	def _button_number(self, binding: str) -> int | None:
		match = re.fullmatch(r"b(\d+)", binding)
		if match is None:
			return None
		number = int(match.group(1))
		return number if number < self.button_count else None


class WindowsHIDController(Controller):
	flags = (
		ControllerFlags.HAS_RSTICK
		| ControllerFlags.HAS_DPAD
		| ControllerFlags.SEPARATE_LSTICK
		| ControllerFlags.NO_GRIPS
	)

	def __init__(self, driver: WindowsHIDDriver, info: dict, mapping_name: str, mapping: dict) -> None:
		super().__init__()
		self.driver = driver
		self.daemon = driver.daemon
		self.path = info["path"]
		self._closed = False
		self.device = hid.device()
		self.device.open_path(self.path)
		self.device.set_nonblocking(True)
		try:
			descriptor = bytes(self.device.get_report_descriptor(4096))
		except AttributeError as exc:
			self.device.close()
			raise RuntimeError("This hidapi build does not expose get_report_descriptor()") from exc
		self._decoder = DecoderBuilder(descriptor, mapping).build()
		if not self._decoder.packet_size:
			self.device.close()
			raise ValueError("empty HID input report")

		vendor_id, product_id = int(info["vendor_id"]), int(info["product_id"])
		self._id = self._generate_id(f"hid{vendor_id:04x}:{product_id:04x}")
		self.mapping_name = mapping_name
		self._bluetooth = self._detect_bluetooth(info)
		self.daemon.add_controller(self)
		log.info("Opened %s using gamecontrollerdb mapping '%s'", self._id, mapping_name)

	def _generate_id(self, preferred: str) -> str:
		controller_id = preferred
		index = 1
		while controller_id in self.daemon.get_active_ids():
			controller_id = f"{preferred}:{index}"
			index += 1
		return controller_id

	@staticmethod
	def _detect_bluetooth(info: dict) -> bool:
		bluetooth_bus = getattr(hid, "HID_API_BUS_BLUETOOTH", None)
		return bluetooth_bus is not None and info.get("bus_type") == bluetooth_bus

	def poll(self) -> None:
		try:
			for _ in range(MAX_REPORTS_PER_TICK):
				report = self.device.read(max(64, self._decoder.packet_size))
				if not report:
					break
				data = bytes(report)
				if len(data) < self._decoder.packet_size:
					continue
				if _lib.decode(ctypes.byref(self._decoder), data) and self.mapper:
					self.mapper.input(self, self._decoder.old_state, self._decoder.state)
		except (OSError, ValueError):
			log.exception("Generic HID controller %s read failed", self._id)
			self.close()

	def get_type(self) -> str:
		return "hid"

	def get_gui_config_file(self) -> str:
		return "x360-config.json"

	def is_bluetooth(self) -> bool:
		return self._bluetooth

	def close(self, *args) -> None:
		if self._closed:
			return
		self._closed = True
		self.driver.controllers.pop(self.path, None)
		try:
			self.device.close()
		finally:
			self.daemon.remove_controller(self)


class WindowsHIDDriver:
	def __init__(self, daemon: SCCDaemon) -> None:
		self.daemon = daemon
		self.controllers: dict[bytes | str, WindowsHIDController] = {}
		self._failed_paths: set[bytes | str] = set()
		self._next_scan = 0.0

	def start(self) -> None:
		self.scan()

	def mainloop(self) -> None:
		for controller in tuple(self.controllers.values()):
			controller.poll()
		if time.monotonic() >= self._next_scan:
			self.scan()

	def scan(self) -> None:
		self._next_scan = time.monotonic() + SCAN_INTERVAL
		found = {}
		try:
			for info in hid.enumerate():
				identity = int(info.get("vendor_id", 0)), int(info.get("product_id", 0))
				if identity in SKIPPED_DEVICES:
					continue
				if info.get("usage_page") not in (None, 0, 0x01) or info.get("usage") not in (None, 0, 0x04, 0x05):
					continue
				path = info.get("path")
				if path is None:
					continue
				mapping = load_gamecontroller_mapping(*identity, str(info.get("product_string") or ""))
				if mapping is not None:
					found[path] = (info, mapping)
		except Exception:
			log.exception("Failed to enumerate generic HID controllers")
			return

		for path, (info, (mapping_name, mapping)) in found.items():
			if path in self.controllers or path in self._failed_paths:
				continue
			try:
				self.controllers[path] = WindowsHIDController(self, info, mapping_name, mapping)
			except (OSError, RuntimeError, ValueError):
				log.exception("Failed to open mapped HID controller at %r", path)
				self._failed_paths.add(path)

		self._failed_paths.intersection_update(found)
		for path in set(self.controllers) - set(found):
			controller = self.controllers.get(path)
			if controller is not None:
				controller.close()

	def close(self, *args) -> None:
		controllers, self.controllers = tuple(self.controllers.values()), {}
		for controller in controllers:
			controller.close()


_driver: WindowsHIDDriver | None = None


def init(daemon: SCCDaemon, config: dict) -> bool:
	global _driver
	if sys.platform != "win32":
		return False
	_driver = WindowsHIDDriver(daemon)
	daemon.add_mainloop(_driver.mainloop)
	daemon.add_on_exit(_driver.close)
	return True


def start(daemon: SCCDaemon) -> None:
	if _driver is not None:
		_driver.start()
