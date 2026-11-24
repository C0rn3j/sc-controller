"""Steam Controller (2015) HIDAPI transports.

The USB input layout and SCController behavior are copied from the original
Linux sc_dongle driver, which remains unchanged. Bluetooth input implements
the partial-report protocol from sc_by_bt.c without requiring a file descriptor.
"""
from __future__ import annotations

import logging
import struct
import sys
import time
from concurrent.futures import Future
from enum import IntEnum
from math import cos, sin
from math import pi as PI
from threading import Thread
from typing import NamedTuple

try:
	import hid
except ImportError:
	hid = None

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, ControllerFlags, SCButtons
from scc.controller import Controller

log = logging.getLogger("SCHIDAPI")

class ControllerInput(NamedTuple):
	"""Based on INPUT_FORMAT except anything starting with "ukn_"""

	type: int
	status: int
	seq: int
	buttons: SCButtons
	ltrig: int
	rtrig: int
	lpad_x: int
	lpad_y: int
	rpad_x: int
	rpad_y: int
	accel_x: int
	accel_y: int
	accel_z: int
	gpitch: int
	groll: int
	gyaw: int
	q1: int
	q2: int
	q3: int
	q4: int

INPUT_FORMAT = [
	("b", "type"),
	("x", "ukn_01"),
	("B", "status"),
	("x", "ukn_02"),
	("H", "seq"),
	("x", "ukn_03"),
	("I", "buttons"),
	("B", "ltrig"),
	("B", "rtrig"),
	("x", "ukn_04"),
	("x", "ukn_05"),
	("x", "ukn_06"),
	("h", "lpad_x"),
	("h", "lpad_y"),
	("h", "rpad_x"),
	("h", "rpad_y"),
	("4x", "ukn_06"),
	("h", "accel_x"),
	("h", "accel_y"),
	("h", "accel_z"),
	("h", "gpitch"),
	("h", "groll"),
	("h", "gyaw"),
	("h", "q1"),
	("h", "q2"),
	("h", "q3"),
	("h", "q4"),
	("16x", "ukn_07"),
]

FORMATS, NAMES = zip(*INPUT_FORMAT)

TUP_FORMAT = "<" + "".join(FORMATS)

SCI_NULL = ControllerInput._make(struct.unpack("<" + "".join(FORMATS), b"\x00" * 64))

LSTICKPRESS = 0b1000000000000000000000000000000

class SCStatus(IntEnum):
	IDLE = 0x04
	INPUT = 0x01
	HOTPLUG = 0x03

class SCPacketType(IntEnum):
	OFF = 0x9F
	AUDIO = 0xB6
	CLEAR_MAPPINGS = 0x81
	CONFIGURE = 0x87
	LED = 0x87
	CALIBRATE_JOYSTICK = 0xBF
	CALIBRATE_TRACKPAD = 0xA7
	SET_AUDIO_INDICES = 0xC1
	LIZARD_MODE = 0x8E
	FEEDBACK = 0x8F
	RESET = 0x95
	GET_SERIAL = 0xAE

class SCPacketLength(IntEnum):
	LED = 0x03
	OFF = 0x04
	FEEDBACK = 0x07
	CONFIGURE = 0x15
	CONFIGURE_BT = 0x0F
	GET_SERIAL = 0x15

class SCConfigType(IntEnum):
	LED = 0x2D
	CONFIGURE = 0x32
	CONFIGURE_BT = 0x18

class SCController(Controller):
	flags: int = ControllerFlags.LPAD_RPAD_IS_CIRCLE

	def __init__(self, driver: HIDSlot, ccidx: int, endpoint: int) -> None:
		Controller.__init__(self)
		self._driver: HIDSlot = driver
		self._endpoint: int = endpoint
		self._idle_timeout: int = 600
		self._enable_gyros: bool = False
		self._input_rotation_l = 0
		self._input_rotation_r = 0
		self._led_level: int = 10
		# TODO: Is serial really used anywhere?
		self._serial: str = "0000000000"
		self._id: str = self._generate_id() if driver else "-"
		self._old_state: ControllerInput = SCI_NULL
		self._ccidx: int = ccidx

	def get_type(self) -> str:
		return "sc"

	def __repr__(self) -> str:
		return f"<SCWireless {self.get_id()}>"

	def input(self, idata: ControllerInput) -> None:
		old_state, self._old_state = self._old_state, idata
		if self.mapper:
			# if idata.buttons & SCButtons.LPAD:
			# # LSTICKPRESS button may signalize pressing stick instead
			# if (idata.buttons & LSTICKPRESS) and not (idata.buttons & LSTICKTILT):
			# idata = ControllerInput.replace(buttons=idata.buttons & ~SCButtons.LPAD)

			if self._input_rotation_l or self._input_rotation_r:
				lx, ly = idata.lpad_x, idata.lpad_y
				rx, ry = idata.rpad_x, idata.rpad_y

				if self._input_rotation_l and idata.buttons & SCButtons.LPADTOUCH:
					s, c = sin(self._input_rotation_l), cos(self._input_rotation_l)
					# Adjust LX for rotation and clamp
					value = int(idata.lpad_x * c - idata.lpad_y * s)
					lx = max(STICK_PAD_MIN, min(STICK_PAD_MAX, value))

					# Adjust LY for rotation and clamp
					value = int(idata.lpad_x * s + idata.lpad_y * c)
					ly = max(STICK_PAD_MIN, min(STICK_PAD_MAX, value))

				if self._input_rotation_r and idata.buttons & SCButtons.RPADTOUCH:
					s, c = sin(self._input_rotation_r), cos(self._input_rotation_r)

					# Adjust RX for rotation and clamp
					value = int(idata.rpad_x * c - idata.rpad_y * s)
					rx = max(STICK_PAD_MIN, min(STICK_PAD_MAX, value))

					# Adjust RY for rotation and clamp
					value = int(idata.rpad_x * s + idata.rpad_y * c)
					ry = max(STICK_PAD_MIN, min(STICK_PAD_MAX, value))

				# TODO: This is awful :(
				idata = ControllerInput(
					type=idata.type,
					status=idata.status,
					seq=idata.seq,
					buttons=idata.buttons,
					ltrig=idata.ltrig,
					rtrig=idata.rtrig,
					lpad_x=lx,
					lpad_y=ly,
					rpad_x=rx,
					rpad_y=ry,
					accel_x=idata.accel_x,
					accel_y=idata.accel_y,
					accel_z=idata.accel_z,
					gpitch=idata.gpitch,
					groll=idata.groll,
					gyaw=idata.gyaw,
					q1=idata.q1,
					q2=idata.q2,
					q3=idata.q3,
					q4=idata.q4,
				)

			self.mapper.input(self, old_state, idata)

	def _generate_id(self) -> str:
		"""ID is generated as 'scX' where where 'X' starts as 0 and increases as more controllers are connected.

		This is used only when reading serial numbers from device is disabled.
		sc_by_cable generates ids in scBUS:PORT format.
		"""
		magic_number = 1
		tp = self.get_type()
		controller_id = None
		while controller_id is None or controller_id in self._driver.daemon.get_active_ids():
			controller_id = f"{tp}{magic_number}"
			magic_number += 1
		return controller_id

	def apply_config(self, config: dict) -> None:
		self.configure(idle_timeout=int(config["idle_timeout"]), led_level=float(config["led_level"]))
		self._input_rotation_l = float(config["input_rotation_l"]) * PI / -180.0
		self._input_rotation_r = float(config["input_rotation_r"]) * PI / -180.0

	FORMAT1 = b">BBBBB13sB2s43x"
	# Has to be overriden in sc_by_cable
	FORMAT2 = b">BBBB59x"

	def configure(
		self, idle_timeout: int | None = None, enable_gyros: bool | None = None, led_level: int | None = None,
	) -> None:
		"""Sets and, if possible, sends configuration to controller.

		Only value that is provided is changed.
		'idle_timeout' is in seconds.
		'led_level' is precent (0-100)
		"""
		# ------
		"""
		packet format:
		 - uint8_t type - SCPacketType.CONFIGURE
		 - uint8_t size - SCPacketLength.CONFIGURE or SCPacketLength.LED
		 - uint8_t config_type - SCConfigType.CONFIGURE or SCConfigType.LED
		 - 61B data

		Format for data when configuring controller:
		 - uint16	timeout
		 - 13B		unknown1 - (0x18, 0x00, 0x00, 0x31, 0x02, 0x00, 0x08, 0x07, 0x00, 0x07, 0x07, 0x00, 0x30)
		 - uint8	enable gyro sensor - 0x14 enables, 0x00 disables
		 - 2B		unknown2 - (0x00, 0x2e)
		 - 43B		unused

		Format for data when configuring led:
		 - uint8	led
		 - 60B		unused
		"""

		if idle_timeout is not None:
			self._idle_timeout = idle_timeout
		if enable_gyros is not None:
			self._enable_gyros = enable_gyros
		if led_level is not None:
			self._led_level = led_level

		unknown1 = b"\x18\x00\x00\x31\x02\x00\x08\x07\x00\x07\x07\x00\x30"
		unknown2 = b"\x00\x2e"
		timeout1 = self._idle_timeout & 0x00FF
		timeout2 = (self._idle_timeout & 0xFF00) >> 8

		# Timeout & Gyros
		self._driver.overwrite_control(
			self._ccidx,
			struct.pack(
				self.FORMAT1,
				SCPacketType.CONFIGURE,
				SCPacketLength.CONFIGURE,
				SCConfigType.CONFIGURE,
				timeout1,
				timeout2,
				unknown1,
				# 0x10 (Gyro) | 0x08 (Accel) | 0x04 (Quat)
				0x1C if self._enable_gyros else 0,
				unknown2,
			),
		)

		# LED
		self._driver.overwrite_control(
			self._ccidx,
			struct.pack(
				self.FORMAT2, SCPacketType.CONFIGURE, SCPacketLength.LED, SCConfigType.LED, int(self._led_level),
			),
		)

	def set_led_level(self, level: int) -> None:
		level = min(100, int(level)) & 0xFF
		if self._led_level != level:
			self._led_level = level
			self._driver.overwrite_control(
				self._ccidx, struct.pack(">BBBB59x", SCPacketType.CONFIGURE, 0x03, SCConfigType.LED, self._led_level),
			)

	def set_gyro_enabled(self, enabled: bool) -> None:
		self.configure(enable_gyros=enabled)

	def turnoff(self) -> None:
		log.debug("Turning off the controller...")

		# Mercilessly stolen from scraw library
		self._driver.send_control(self._ccidx, struct.pack("<BBBBBB", SCPacketType.OFF, 0x04, 0x6F, 0x66, 0x66, 0x21))

	def get_gyro_enabled(self) -> bool:
		"""Returns True if gyroscope input is currently enabled"""
		return self._enable_gyros

	def feedback(self, data) -> None:
		self._feedback(*data.data)

	def _feedback(self, position: int, amplitude: int = 128, period: int = 0, count: int = 1) -> None:
		"""Add haptic feedback to be send on next usb tick.

		@param int position		haptic to use 1 for left 0 for right
		@param int amplitude	signal amplitude from 0 to 65535
		@param int period		signal period from 0 to 65535
		@param int count		number of period to play
		"""
		if amplitude >= 0:
			self._driver.send_control(
				self._ccidx, struct.pack("<BBBHHH", SCPacketType.FEEDBACK, 0x07, position, amplitude, period, count),
			)


BT_FIELDS = (
	"type", "buttons", "ltrig", "rtrig", "lstick_x", "lstick_y", "lpad_x", "lpad_y",
	"rpad_x", "rpad_y", "accel_x", "accel_y", "accel_z", "gpitch", "groll", "gyaw", "q1", "q2", "q3", "q4",
)
BTInput = NamedTuple("BTInput", [(field, int) for field in BT_FIELDS])
BT_NULL = BTInput(*([0] * len(BT_FIELDS)))
BT_BUTTONS = (
	SCButtons.RT, SCButtons.LT, SCButtons.RB, SCButtons.LB,
	SCButtons.Y, SCButtons.B, SCButtons.X, SCButtons.A,
	0, 0, 0, 0, SCButtons.BACK, SCButtons.C, SCButtons.START,
	SCButtons.LGRIP, SCButtons.RGRIP, SCButtons.LPAD, SCButtons.RPAD,
	SCButtons.LPADTOUCH, SCButtons.RPADTOUCH, 0, SCButtons.LSTICKPRESS,
)


class BluetoothDecoder:
	"""Assemble 20-byte BLE reports and retain fields absent from updates."""

	def __init__(self) -> None:
		self.state = BT_NULL
		self._payload = bytearray()
		self._next_segment = 0

	def feed(self, report: bytes) -> BTInput | None:
		if len(report) != 20 or report[0] != 0x03:
			self._payload.clear()
			return None
		header = report[1]
		segment = header & 0x0F
		if segment == 0:
			self._payload = bytearray(report[2:])
		elif self._payload and segment == self._next_segment and len(self._payload) + 18 <= 254:
			self._payload.extend(report[2:])
		else:
			self._payload.clear()
			return None
		self._next_segment = segment + 1
		if not header & 0x40:
			return None
		payload, self._payload = bytes(self._payload), bytearray()
		kind = int.from_bytes(payload[:2], "little")
		if kind & 0x5000 == 0x5000:
			return None  # keepalive
		updates = {"type": kind}
		offset = 2
		try:
			if kind & 0x10:
				if len(payload) < offset + 3:
					return None
				raw = int.from_bytes(payload[offset:offset + 3], "little")
				updates["buttons"] = sum(int(button) for bit, button in enumerate(BT_BUTTONS) if raw & (1 << bit))
				offset += 3
			if kind & 0x20:
				updates["ltrig"], updates["rtrig"] = struct.unpack_from("BB", payload, offset)
				offset += 2
			for mask, names in ((0x80, ("lstick_x", "lstick_y")), (0x100, ("lpad_x", "lpad_y")), (0x200, ("rpad_x", "rpad_y"))):
				if kind & mask:
					updates.update(zip(names, struct.unpack_from("<hh", payload, offset)))
					offset += 4
			if kind & 0x1800 == 0x1800:
				updates.update(zip(BT_FIELDS[10:], struct.unpack_from("<10h", payload, offset)))
		except struct.error:
			return None  # incomplete payload; do not partially mutate state
		if len(updates) == 1:
			return None
		self.state = self.state._replace(**updates)
		return self.state


class HIDController(SCController):
	def __init__(self, slot: HIDSlot) -> None:
		self.slot = slot
		super().__init__(slot, slot.info.get("interface_number", 0), 0)
		self._old_state = BT_NULL if slot.driver.bluetooth else SCI_NULL
		self._closed = False
		if slot.driver.bluetooth:
			self.flags |= ControllerFlags.SEPARATE_LSTICK
			self._led_level = 30

	def get_type(self) -> str:
		return "scbt" if self.slot.driver.bluetooth else "sc"

	def set_led_level(self, level: int) -> None:
		if not self.slot.driver.bluetooth:
			return super().set_led_level(level)
		level = min(100, int(level)) & 0xFF
		if level != self._led_level:
			self._led_level = level
			self.slot.send_control(0, bytes((0x87, 3, 0x2D, level)))

	def is_bluetooth(self) -> bool:
		return self.slot.driver.bluetooth

	def read_serial(self) -> None:
		if self.slot.driver.bluetooth:
			serial = self.slot.info.get("serial_number") or str(self.slot.path)
			self._serial = str(serial).replace(":", "")
			self.on_serial_got()
		elif self.slot.driver.ignore_serials:
			self._serial = str(self.slot.path)
			self.on_serial_got()
		else:
			def got_serial(raw: bytes) -> None:
				if len(raw) >= 15 and raw[1] > 1:
					self._serial = raw[3:15].strip(b" \x00").decode("ascii")
					self.on_serial_got()
			self.slot.make_request(0, got_serial, b"\xae\x15\x01".ljust(64, b"\x00"))

	def on_serial_got(self) -> None:
		preferred = f"sc{self._serial}" if self.slot.driver.wired else str(self._serial)
		self._id = preferred
		index = 1
		while self._id in self.slot.daemon.get_active_ids():
			self._id = f"{preferred}:{index}"
			index += 1
		self.slot.register(self)

	def configure(self, idle_timeout=None, enable_gyros=None, led_level=None) -> None:
		if not self.slot.driver.bluetooth:
			return super().configure(idle_timeout, enable_gyros, led_level)
		if enable_gyros is not None:
			self._enable_gyros = enable_gyros
		if led_level is not None:
			self._led_level = int(led_level)
		self.slot.send_control(0, struct.pack(
			">BBB12sB2s", 0x87, 0x0F, 0x18,
			bytes.fromhex("00 00 31 02 00 08 07 00 07 07 00 30"),
			0x1C if self._enable_gyros else 0, b"\x00\x2e",
		))
		self.slot.send_control(0, bytes((0x87, 3, 0x2D, int(self._led_level))))

	def input(self, state) -> None:
		# Retain the firmware's raw coordinates for the next partial BT update.
		# Rotate only fields carried by this update, matching the Linux driver.
		if not self.slot.driver.bluetooth:
			return super().input(state)
		updates = {}
		for mask, prefix, angle in ((0x100, "lpad", self._input_rotation_l), (0x200, "rpad", self._input_rotation_r)):
			if not state.type & mask:
				updates[prefix + "_x"] = getattr(self._old_state, prefix + "_x")
				updates[prefix + "_y"] = getattr(self._old_state, prefix + "_y")
			elif angle:
				x, y = getattr(state, prefix + "_x"), getattr(state, prefix + "_y")
				updates[prefix + "_x"] = max(STICK_PAD_MIN, min(STICK_PAD_MAX, int(x * cos(angle) - y * sin(angle))))
				updates[prefix + "_y"] = max(STICK_PAD_MIN, min(STICK_PAD_MAX, int(x * sin(angle) + y * cos(angle))))
		mapped = state._replace(**updates)
		if self.mapper:
			self.mapper.input(self, self._old_state, mapped)
		self._old_state = mapped

	def turnoff(self) -> None:
		if self.slot.driver.wired:
			log.warning("Ignoring request to turn off wired controller")
			return
		super().turnoff()
		self.slot._suppressed_at = time.monotonic()
		self.close()

	def close(self, *args) -> None:
		if self._closed:
			return
		self._closed = True
		if self.slot.controller is self:
			self.slot.controller = None
			self.slot._last_input = None
			self.slot._decoder = BluetoothDecoder()
		if self.slot._registered:
			self.slot._registered = False
			self.slot.daemon.remove_controller(self)


class HIDSlot:
	"""One HID path per receiver slot, cable, or Bluetooth controller."""

	def __init__(self, driver: HIDDriver, info: dict) -> None:
		self.driver = driver
		self.daemon = driver.daemon
		self.info = info
		self.path = info["path"]
		self.controller: HIDController | None = None
		self._registered = False
		self._closed = False
		self._suppressed_at = None
		self._last_input = None
		self._next_timer = 0.0
		self._decoder = BluetoothDecoder()
		self.device = hid.device()
		try:
			self.device.open_path(self.path)
			self.device.set_nonblocking(True)
			if driver.bluetooth:
				self._connect()
		except Exception:
			self.device.close()
			raise

	def send_control(self, index: int, data: bytes) -> None:
		if self.driver.bluetooth:
			report = b"\x03" + (b"\xc0" + data).ljust(20, b"\x00")
		else:
			# Unnumbered USB feature report: HIDAPI needs a leading zero ID.
			report = b"\x00" + data.ljust(64, b"\x00")
		written = self.device.send_feature_report(report)
		if written != len(report):
			raise OSError(f"Incomplete SC feature report: {written}/{len(report)}")

	def overwrite_control(self, index: int, data: bytes) -> None:
		self.send_control(index, data)

	def make_request(self, index: int, callback, data: bytes, size=64) -> None:
		self.send_control(index, data)
		reply = bytes(self.device.get_feature_report(0, size + 1))
		if reply and reply[0] == 0:
			callback(reply[1:])

	def register(self, controller: HIDController) -> None:
		if not self._registered:
			self._registered = True
			self.daemon.add_controller(controller)
			log.info("Connected %s %s at %r", controller.get_type(), controller.get_id(), self.path)

	def _connect(self) -> None:
		controller = self.controller = HIDController(self)
		try:
			controller.configure()
			controller.read_serial()
		except Exception:
			controller.close()
			raise

	def _on_input(self, report: bytes) -> None:
		if self._suppressed_at is not None:
			now = time.monotonic()
			if now - self._suppressed_at < 0.5:
				self._suppressed_at = now
				return
			self._suppressed_at = None
		if self.driver.bluetooth:
			state = self._decoder.feed(report)
			if state is not None:
				if self.controller is None:
					self._connect()
				self.controller.input(state)
			return
		if len(report) != 64:
			return
		state = ControllerInput._make(struct.unpack(TUP_FORMAT, report))
		if state.status == SCStatus.HOTPLUG:
			if report[4] == 2 and self.controller is None:
				self._connect()
			elif report[4] != 2 and self.controller:
				self.controller.close()
		elif state.status == SCStatus.INPUT:
			if self.controller is None:
				self._connect()
			elif not self._registered:
				self.controller.read_serial()
			if self._registered:
				if self.driver.wired:
					self._last_input = state
				else:
					self.controller.input(state)

	def _timer(self) -> None:
		# Keep the cable backend's 10 ms event/feedback timer, including ticks
		# when the controller has not supplied another input report.
		if not self.driver.wired or not self.controller or not self._registered:
			return
		now = time.monotonic()
		if now < self._next_timer:
			return
		self._next_timer = now + 0.01
		if self._last_input is not None:
			self.controller.input(self._last_input)
			self._last_input = None
		elif self.controller.mapper:
			self.controller.mapper.generate_events()
			self.controller.mapper.generate_feedback()

	def poll(self) -> None:
		if self._closed:
			return
		try:
			for _ in range(32):
				report = self.device.read(64)
				if not report:
					break
				self._on_input(bytes(report))
			self._timer()
		except (OSError, ValueError):
			log.exception("Steam Controller communication failed at %r", self.path)
			self.close()

	def close(self, *args) -> None:
		if self._closed:
			return
		self._closed = True
		self.driver.slots.pop(self.path, None)
		try:
			self.device.close()
		finally:
			if self.controller:
				self.controller.close()


class HIDDriver:
	def __init__(self, daemon, product: int, interfaces: tuple[int, ...], *, bluetooth=False, wired=False, ignore_serials=False) -> None:
		self.daemon = daemon
		self.product = product
		self.interfaces = interfaces
		self.bluetooth = bluetooth
		self.wired = wired
		self.ignore_serials = ignore_serials
		self.slots = {}
		self._next_scan = 0.0
		self._scan_result: Future | None = None

	def _enumerate(self) -> dict | None:
		try:
			return {
				info["path"]: info for info in hid.enumerate(0x28DE, self.product)
				if info.get("path") is not None
				and (self.bluetooth or info.get("interface_number") in self.interfaces)
				and info.get("usage_page") not in (0x01, 0x07, 0x0C)
			}
		except Exception:
			log.exception("Failed to enumerate Steam Controller HID interfaces")
			return None

	def _apply_scan(self, found: dict) -> None:
		for path, info in found.items():
			if path not in self.slots:
				try:
					self.slots[path] = HIDSlot(self, info)
				except (OSError, ValueError):
					log.exception("Failed to open Steam Controller at %r", path)
		for path in set(self.slots) - set(found):
			self.slots[path].close()

	def scan(self) -> None:
		self._next_scan = time.monotonic() + 1.0
		if self._scan_result is None:
			found = self._enumerate()
			if found is not None:
				self._apply_scan(found)

	def mainloop(self) -> None:
		for slot in tuple(self.slots.values()):
			slot.poll()
		if self._scan_result is not None and self._scan_result.done():
			result, self._scan_result = self._scan_result, None
			found = result.result()
			if found is not None:
				self._apply_scan(found)
		if time.monotonic() >= self._next_scan and self._scan_result is None:
			self._next_scan = time.monotonic() + 1.0
			result = self._scan_result = Future()

			def enumerate_devices() -> None:
				result.set_result(self._enumerate())

			Thread(target=enumerate_devices, name="sc-hidapi-discovery", daemon=True).start()

	def close(self, *args) -> None:
		for slot in tuple(self.slots.values()):
			slot.close()


def init_driver(daemon, config, legacy: str, product: int, interfaces: tuple[int, ...], **options) -> HIDDriver | None:
	if sys.platform not in ("linux", "win32", "darwin"):
		return None
	if sys.platform == "linux" and config.get("drivers", {}).get(legacy, True):
		log.error("Disable %s before enabling %s_hidapi", legacy, legacy)
		return None
	if hid is None:
		log.error("Install sccontroller[hidapi] to enable the Steam Controller HIDAPI drivers")
		return None
	driver = HIDDriver(daemon, product, interfaces, ignore_serials=config.get("ignore_serials", False), **options)
	daemon.add_mainloop(driver.mainloop)
	daemon.add_on_exit(driver.close)
	daemon.add_on_rescan(driver.scan)
	return driver
