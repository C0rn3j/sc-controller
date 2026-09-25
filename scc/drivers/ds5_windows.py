"""DualSense HIDAPI driver for non-Linux platforms."""

from __future__ import annotations

import ctypes
import logging
import time
from typing import TYPE_CHECKING, ClassVar

import hid

from scc.constants import (
	DUALSENSE_CPAD_X_MAX,
	DUALSENSE_CPAD_Y_MAX,
	STICK_PAD_MAX,
	STICK_PAD_MIN,
	STICK_PAD_RES,
	ControllerFlags,
	SCButtons,
)
from scc.controller import Controller

if TYPE_CHECKING:
	from scc.sccdaemon import SCCDaemon


log = logging.getLogger("DS5Windows")

VENDOR_ID = 0x054C
PRODUCT_IDS = (0x0CE6, 0x0DF2)
SCAN_INTERVAL = 1.0
MAX_REPORTS_PER_TICK = 32


class DualSenseControllerInput(ctypes.Structure):
	"""Mapper-compatible decoded DualSense state."""

	_fields_ = [
		("type", ctypes.c_uint16),
		("buttons", ctypes.c_uint32),
		("ltrig", ctypes.c_uint8),
		("rtrig", ctypes.c_uint8),
		("lstick_x", ctypes.c_int32),
		("lstick_y", ctypes.c_int32),
		("rstick_x", ctypes.c_int32),
		("rstick_y", ctypes.c_int32),
		("dpad_x", ctypes.c_int32),
		("dpad_y", ctypes.c_int32),
		("accel_x", ctypes.c_int32),
		("accel_y", ctypes.c_int32),
		("accel_z", ctypes.c_int32),
		("gpitch", ctypes.c_int32),
		("groll", ctypes.c_int32),
		("gyaw", ctypes.c_int32),
		("q1", ctypes.c_int32),
		("q2", ctypes.c_int32),
		("q3", ctypes.c_int32),
		("q4", ctypes.c_int32),
		("cpad_x", ctypes.c_int32),
		("cpad_y", ctypes.c_int32),
	]


class WindowsDualSenseController(Controller):
	"""A DualSense opened through HIDAPI's native platform backend."""

	flags = (
		ControllerFlags.EUREL_GYROS
		| ControllerFlags.HAS_RSTICK
		| ControllerFlags.HAS_CPAD
		| ControllerFlags.HAS_DPAD
		| ControllerFlags.SEPARATE_LSTICK
		| ControllerFlags.NO_GRIPS
	)

	_DPAD: ClassVar[dict[int, tuple[int, int]]] = {
		0: (0, STICK_PAD_MAX),
		1: (STICK_PAD_MAX, STICK_PAD_MAX),
		2: (STICK_PAD_MAX, 0),
		3: (STICK_PAD_MAX, STICK_PAD_MIN),
		4: (0, STICK_PAD_MIN),
		5: (STICK_PAD_MIN, STICK_PAD_MIN),
		6: (STICK_PAD_MIN, 0),
		7: (STICK_PAD_MIN, STICK_PAD_MAX),
		8: (0, 0),
	}

	def __init__(self, driver: DualSenseWindowsDriver, info: dict) -> None:
		super().__init__()
		self.driver = driver
		self.daemon = driver.daemon
		self.path = info["path"]
		self._closed = False
		self._old_state = DualSenseControllerInput()
		self._bluetooth = self._detect_bluetooth(info)

		self.device = hid.device()
		self.device.open_path(self.path)
		self.device.set_nonblocking(True)

		serial = info.get("serial_number")
		self._id = self._generate_id(str(serial) if serial else "ds5")
		self.daemon.add_controller(self)
		log.info(
			"Opened %s DualSense %s at %r",
			"Bluetooth" if self._bluetooth else "USB",
			self._id,
			self.path,
		)

	@staticmethod
	def _detect_bluetooth(info: dict) -> bool:
		bus_type = info.get("bus_type")
		bluetooth_bus = getattr(hid, "HID_API_BUS_BLUETOOTH", None)
		if bluetooth_bus is not None and bus_type is not None:
			return bus_type == bluetooth_bus
		return "BTH" in str(info.get("path", "")).upper()

	def _generate_id(self, preferred: str) -> str:
		controller_id = preferred
		index = 1
		while controller_id in self.daemon.get_active_ids():
			controller_id = f"{preferred}:{index}"
			index += 1
		return controller_id

	def poll(self) -> None:
		if self._closed:
			return
		try:
			for _ in range(MAX_REPORTS_PER_TICK):
				report = self.device.read(128)
				if not report:
					break
				self._handle_report(bytes(report))
		except (OSError, ValueError):
			log.exception("DualSense %s read failed", self._id)
			self.close()

	def _handle_report(self, report: bytes) -> None:
		if not report:
			return
		if report[0] == 0x31:
			offset = 1
			self._bluetooth = True
		elif report[0] == 0x01:
			offset = 0
		else:
			return
		if len(report) < 38 + offset:
			return

		state = self._decode_report(report, offset)
		if self.mapper:
			self.mapper.input(self, self._old_state, state)
		self._old_state = state

	def _decode_report(self, data: bytes, offset: int) -> DualSenseControllerInput:
		state = DualSenseControllerInput()
		state.lstick_x = self._stick_axis_scale(data[1 + offset])
		state.lstick_y = self._stick_axis_scale(data[2 + offset], invert=True)
		state.rstick_x = self._stick_axis_scale(data[3 + offset])
		state.rstick_y = self._stick_axis_scale(data[4 + offset], invert=True)
		state.ltrig = data[5 + offset]
		state.rtrig = data[6 + offset]

		buttons = data[8 + offset]
		if buttons & 0x80:
			state.buttons |= SCButtons.Y
		if buttons & 0x40:
			state.buttons |= SCButtons.B
		if buttons & 0x20:
			state.buttons |= SCButtons.A
		if buttons & 0x10:
			state.buttons |= SCButtons.X
		state.dpad_x, state.dpad_y = self._DPAD.get(buttons & 0x0F, (0, 0))

		buttons = data[9 + offset]
		button_map = (
			(0x80, SCButtons.RSTICKPRESS),
			(0x40, SCButtons.LSTICKPRESS),
			(0x20, SCButtons.START),
			(0x10, SCButtons.BACK),
			(0x08, SCButtons.RT),
			(0x04, SCButtons.LT),
			(0x02, SCButtons.RB),
			(0x01, SCButtons.LB),
		)
		for mask, button in button_map:
			if buttons & mask:
				state.buttons |= button

		buttons = data[10 + offset]
		if buttons & 0x01:
			state.buttons |= SCButtons.C
		if buttons & 0x02:
			state.buttons |= SCButtons.CPADPRESS

		state.gpitch = self._int16(data, 16 + offset)
		state.gyaw = self._int16(data, 18 + offset)
		state.groll = self._int16(data, 20 + offset)
		state.accel_x = self._int16(data, 22 + offset) * 2
		state.accel_z = self._int16(data, 24 + offset) * 2
		state.accel_y = self._int16(data, 26 + offset) * -2

		if not data[33 + offset] & 0x80:
			state.buttons |= SCButtons.CPADTOUCH
		raw_cpad_x = ((data[35 + offset] & 0x0F) << 8) | data[34 + offset]
		raw_cpad_y = (data[36 + offset] << 4) | (data[35 + offset] >> 4)
		state.cpad_x = self._cpad_axis_scale(raw_cpad_x, DUALSENSE_CPAD_X_MAX)
		state.cpad_y = self._cpad_axis_scale(raw_cpad_y, DUALSENSE_CPAD_Y_MAX, invert=True)
		return state

	@staticmethod
	def _int16(data: bytes, offset: int) -> int:
		return ctypes.c_int16(data[offset] | data[offset + 1] << 8).value

	@staticmethod
	def _stick_axis_scale(value: int, invert: bool = False) -> int:
		ratio = (value - 128) / (127.0 if value >= 128 else 128.0)
		if invert:
			ratio = -ratio
		return int(((ratio + 1.0) * 0.5) * STICK_PAD_RES + STICK_PAD_MIN)

	@staticmethod
	def _cpad_axis_scale(value: int, maximum: int, invert: bool = False) -> int:
		value = max(0, min(value, maximum))
		scaled = int(value * STICK_PAD_RES / maximum)
		return STICK_PAD_MAX - scaled if invert else STICK_PAD_MIN + scaled

	def is_bluetooth(self) -> bool:
		return self._bluetooth

	def get_type(self) -> str:
		return "ds5"

	def get_gui_config_file(self) -> str:
		return "ds5-config.json"

	def get_gyro_enabled(self) -> bool:
		return True

	def feedback(self, data) -> None:
		# HID output reports will be added after input is validated on hardware.
		return

	def close(self, *args) -> None:
		if self._closed:
			return
		self._closed = True
		self.driver.controllers.pop(self.path, None)
		try:
			self.device.close()
		finally:
			self.daemon.remove_controller(self)


class DualSenseWindowsDriver:
	def __init__(self, daemon: SCCDaemon) -> None:
		self.daemon = daemon
		self.controllers: dict[bytes | str, WindowsDualSenseController] = {}
		self._next_scan = 0.0

	def start(self) -> None:
		self.scan()

	def mainloop(self) -> None:
		for controller in tuple(self.controllers.values()):
			controller.poll()
		now = time.monotonic()
		if now >= self._next_scan:
			self.scan()

	def scan(self) -> None:
		self._next_scan = time.monotonic() + SCAN_INTERVAL
		found = {}
		try:
			for product_id in PRODUCT_IDS:
				for info in hid.enumerate(VENDOR_ID, product_id):
					usage_page = info.get("usage_page")
					usage = info.get("usage")
					if usage_page not in (None, 0x01) or usage not in (None, 0x04, 0x05):
						continue
					path = info.get("path")
					if path is not None:
						found[path] = info
		except Exception:
			log.exception("Failed to enumerate DualSense HID devices")
			return

		for path, info in found.items():
			if path in self.controllers:
				continue
			try:
				self.controllers[path] = WindowsDualSenseController(self, info)
			except (OSError, ValueError):
				log.exception("Failed to open DualSense at %r", path)

		for path in set(self.controllers) - set(found):
			controller = self.controllers.get(path)
			if controller is None:
				continue
			controller.close()

	def close(self, *args) -> None:
		controllers, self.controllers = tuple(self.controllers.values()), {}
		for controller in controllers:
			controller.close()


_driver: DualSenseWindowsDriver | None = None


def init(daemon: SCCDaemon, config: dict) -> bool:
	global _driver
	_driver = DualSenseWindowsDriver(daemon)
	daemon.add_mainloop(_driver.mainloop)
	daemon.add_on_exit(_driver.close)
	return True


def start(daemon: SCCDaemon) -> None:
	if _driver is not None:
		_driver.start()
