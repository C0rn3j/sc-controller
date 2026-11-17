"""DualShock 4 USB and Bluetooth input and output through Windows HIDAPI."""

from __future__ import annotations

import colorsys
import logging
import time
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import hid

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, ControllerFlags, HapticPos, SCButtons
from scc.controller import Controller

if TYPE_CHECKING:
	from scc.sccdaemon import SCCDaemon

log = logging.getLogger("DS4Windows")
VENDOR_ID = 0x054C
PRODUCT_IDS = (0x05C4, 0x09CC)
SCAN_INTERVAL = 1.0
MAX_REPORTS_PER_TICK = 32


@dataclass
class DS4ControllerInput:
	"""Decoded DS4 state in SCC's coordinate system."""

	buttons: int = 0
	ltrig: int = 0
	rtrig: int = 0
	lstick_x: int = 0
	lstick_y: int = 0
	rstick_x: int = 0
	rstick_y: int = 0
	dpad_x: int = 0
	dpad_y: int = 0
	gpitch: int = 0
	gyaw: int = 0
	groll: int = 0
	accel_x: int = 0
	accel_y: int = 0
	accel_z: int = 0
	q1: int = 0
	q2: int = 0
	q3: int = 0
	q4: int = 0
	cpad_x: int = 0
	cpad_y: int = 0


class WindowsDS4Controller(Controller):
	"""A Sony DS4 v1/v2 opened by its HID interface path."""

	flags = (
		ControllerFlags.EUREL_GYROS
		| ControllerFlags.HAS_RSTICK
		| ControllerFlags.HAS_CPAD
		| ControllerFlags.HAS_DPAD
		| ControllerFlags.SEPARATE_LSTICK
		| ControllerFlags.NO_GRIPS
	)
	_DPAD: ClassVar[tuple[tuple[int, int], ...]] = (
		(0, STICK_PAD_MAX),
		(STICK_PAD_MAX, STICK_PAD_MAX),
		(STICK_PAD_MAX, 0),
		(STICK_PAD_MAX, STICK_PAD_MIN),
		(0, STICK_PAD_MIN),
		(STICK_PAD_MIN, STICK_PAD_MIN),
		(STICK_PAD_MIN, 0),
		(STICK_PAD_MIN, STICK_PAD_MAX),
		(0, 0),
	)

	def __init__(self, driver: DS4WindowsDriver, info: dict) -> None:
		super().__init__()
		self.driver = driver
		self.daemon = driver.daemon
		self.path = info["path"]
		self._closed = False
		self._old_state = DS4ControllerInput()
		self._bluetooth = (
			info.get("bus_type") == getattr(hid, "HID_API_BUS_BLUETOOTH", 2) or "BTH" in str(self.path).upper()
		)
		self._color = (0, 0, 0)
		self._motors = [0, 0]  # Left (large), right (small).
		self._motor_deadlines = [None, None]
		self._motion_available = False
		preferred = str(info.get("serial_number") or "ds4")
		self._id = preferred
		index = 1
		while self._id in self.daemon.get_active_ids():
			self._id = f"{preferred}:{index}"
			index += 1

		self.device = hid.device()
		try:
			self.device.open_path(self.path)
			self.device.set_nonblocking(True)
		except Exception:
			self.device.close()
			raise
		if self._bluetooth:
			# A Bluetooth effects report enables the extended reports carrying IMU/touch data.
			self._write_output()
		self.daemon.add_controller(self)
		log.info("Opened %s DS4 %s at %r", "Bluetooth" if self._bluetooth else "USB", self._id, self.path)

	@staticmethod
	def _stick_axis(value: int, invert: bool = False) -> int:
		ratio = (value - 128) / (127 if value >= 128 else 128)
		if invert:
			ratio = -ratio
		return round(ratio * (STICK_PAD_MAX if ratio >= 0 else -STICK_PAD_MIN))

	@staticmethod
	def _int16(data: bytes, offset: int) -> int:
		return int.from_bytes(data[offset : offset + 2], "little", signed=True)

	def _handle_report(self, report: bytes) -> None:
		if not report:
			return
		if report[0] == 0x01 and len(report) >= 10:
			offset = 0
		elif 0x11 <= report[0] <= 0x19 and len(report) >= 78 and report[1] & 0x80:
			if zlib.crc32(b"\xa1" + report[:74]) != int.from_bytes(report[74:78], "little"):
				return
			offset = 2
			self._bluetooth = True
		else:
			return

		state = DS4ControllerInput()
		state.lstick_x = self._stick_axis(report[1 + offset])
		state.lstick_y = self._stick_axis(report[2 + offset], invert=True)
		state.rstick_x = self._stick_axis(report[3 + offset])
		state.rstick_y = self._stick_axis(report[4 + offset], invert=True)
		state.ltrig, state.rtrig = report[8 + offset : 10 + offset]
		hat = report[5 + offset] & 0x0F
		state.dpad_x, state.dpad_y = self._DPAD[hat if hat < 8 else 8]
		for mask, button in ((0x10, SCButtons.X), (0x20, SCButtons.A), (0x40, SCButtons.B), (0x80, SCButtons.Y)):
			if report[5 + offset] & mask:
				state.buttons |= button
		for mask, button in (
			(0x01, SCButtons.LB),
			(0x02, SCButtons.RB),
			(0x04, SCButtons.LT),
			(0x08, SCButtons.RT),
			(0x10, SCButtons.BACK),
			(0x20, SCButtons.START),
			(0x40, SCButtons.LSTICKPRESS),
			(0x80, SCButtons.RSTICKPRESS),
		):
			if report[6 + offset] & mask:
				state.buttons |= button
		if report[7 + offset] & 1:
			state.buttons |= SCButtons.C
		if report[7 + offset] & 2:
			state.buttons |= SCButtons.CPADPRESS

		# Short Bluetooth 0x01 reports carry only the basic controls.
		self._motion_available = len(report) >= 39 + offset
		if self._motion_available:
			state.gpitch = self._int16(report, 13 + offset)
			state.gyaw = self._int16(report, 15 + offset)
			state.groll = self._int16(report, 17 + offset)
			state.accel_x = self._int16(report, 19 + offset)
			state.accel_y = self._int16(report, 21 + offset)
			state.accel_z = self._int16(report, 23 + offset)
			# Preserve the gravity channels used by the Linux DS4 decoder.
			state.q1, state.q2, state.q3 = -state.accel_z, -state.accel_x, -state.accel_y
			if report[33 + offset]:  # At least one touch sample is present.
				for finger in (35 + offset, 39 + offset):
					if finger + 3 >= len(report) or report[finger] & 0x80:
						continue
					x = report[finger + 1] | ((report[finger + 2] & 0x0F) << 8)
					y = (report[finger + 2] >> 4) | (report[finger + 3] << 4)
					state.cpad_x = max(
						STICK_PAD_MIN, min(STICK_PAD_MAX, round(x * STICK_PAD_MAX / 940 + STICK_PAD_MIN))
					)
					state.cpad_y = max(
						STICK_PAD_MIN, min(STICK_PAD_MAX, round(STICK_PAD_MAX - y * STICK_PAD_MAX / 470))
					)
					state.buttons |= SCButtons.CPADTOUCH
					break
		if self.mapper:
			self.mapper.input(self, self._old_state, state)
		self._old_state = state

	def poll(self) -> None:
		if self._closed:
			return
		now = time.monotonic()
		expired = False
		for motor, deadline in enumerate(self._motor_deadlines):
			if deadline is not None and now >= deadline:
				self._motors[motor] = 0
				self._motor_deadlines[motor] = None
				expired = True
		if expired:
			self._write_output()
		try:
			for _ in range(MAX_REPORTS_PER_TICK):
				report = self.device.read(128)
				if not report:
					break
				self._handle_report(bytes(report))
		except (OSError, ValueError):
			log.exception("DS4 %s read failed", self._id)
			self.close()

	def _write_output(self) -> None:
		if self._closed:
			return
		offset = 2 if self._bluetooth else 0
		report = bytearray(78 if self._bluetooth else 32)
		report[0] = 0x11 if self._bluetooth else 0x05
		if self._bluetooth:
			report[1] = 0xC4
		report[1 + offset] = 0x03  # Update motors and RGB lightbar.
		report[4 + offset], report[5 + offset] = self._motors[1], self._motors[0]
		report[6 + offset : 9 + offset] = bytes(self._color)
		if self._bluetooth:
			report[74:78] = zlib.crc32(b"\xa2" + report[:74]).to_bytes(4, "little")
		try:
			if self.device.write(bytes(report)) != len(report):
				raise OSError("Incomplete DS4 output report")
		except (OSError, ValueError):
			log.exception("DS4 %s output failed", self._id)

	def feedback(self, data) -> None:
		position, amplitude, period, count = data.data
		strength = round(max(0, min(amplitude, 0x8000)) * 255 / 0x8000) if count else 0
		deadline = time.monotonic() + max(float(period) * count / 0x10000, 0.02) if strength else None
		for motor, side in enumerate((HapticPos.LEFT, HapticPos.RIGHT)):
			if position in (side, HapticPos.BOTH):
				self._motors[motor] = strength
				self._motor_deadlines[motor] = deadline
		self._write_output()

	def set_led_color(self, red: int, green: int, blue: int) -> None:
		self._color = (red, green, blue)
		self._write_output()

	def apply_config(self, config) -> None:
		color = colorsys.hsv_to_rgb(
			float(config["led_hue"]) / 360, float(config["led_saturation"]) / 100, float(config["led_level"]) / 100
		)
		self.set_led_color(*(round(channel * 255) for channel in color))

	def get_type(self) -> str:
		return "ds4"

	def get_gui_config_file(self) -> str:
		return "ds4-config.json"

	def is_bluetooth(self) -> bool:
		return self._bluetooth

	def get_gyro_enabled(self) -> bool:
		return self._motion_available

	def close(self, *args) -> None:
		if self._closed:
			return
		if any(self._motors):
			self._motors = [0, 0]
			self._write_output()
		self._closed = True
		self.driver.controllers.pop(self.path, None)
		try:
			self.device.close()
		finally:
			self.daemon.remove_controller(self)


class DS4WindowsDriver:
	"""Discover DS4 HID interfaces and poll controllers from the daemon loop."""

	def __init__(self, daemon: SCCDaemon) -> None:
		self.daemon = daemon
		self.controllers: dict[bytes | str, WindowsDS4Controller] = {}
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
			for product_id in PRODUCT_IDS:
				for info in hid.enumerate(VENDOR_ID, product_id):
					if info.get("usage_page") not in (None, 0, 1) or info.get("usage") not in (None, 0, 4, 5):
						continue
					if info.get("path") is not None:
						found[info["path"]] = info
		except OSError:
			log.exception("Failed to enumerate DS4 HID interfaces")
			return
		for path, info in found.items():
			if path not in self.controllers:
				try:
					self.controllers[path] = WindowsDS4Controller(self, info)
				except (OSError, ValueError):
					log.exception("Failed to open DS4 at %r", path)
		for path in set(self.controllers) - set(found):
			self.controllers[path].close()

	def close(self, *args) -> None:
		for controller in tuple(self.controllers.values()):
			controller.close()


_driver: DS4WindowsDriver | None = None


def init(daemon: SCCDaemon, config: dict) -> bool:
	global _driver
	_driver = DS4WindowsDriver(daemon)
	daemon.add_mainloop(_driver.mainloop)
	daemon.add_on_exit(_driver.close)
	daemon.add_on_rescan(_driver.scan)
	return True


def start(daemon: SCCDaemon) -> None:
	if _driver is not None:
		_driver.start()
