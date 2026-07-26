"""SC Controller - Steam Controller Wireless Receiver (aka Dongle) Driver.

Called and used when Dongle is detected on USB bus.
Handles one or multiple controllers connected to dongle.
"""

from __future__ import annotations

import logging
import os
import struct
import time
from collections import namedtuple
from enum import IntEnum
from math import asin, atan2, cos, sin, sqrt
from math import pi as PI
from typing import TYPE_CHECKING

from scc.config import Config
from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, ControllerFlags, SCButtons
from scc.controller import Controller
from scc.drivers.usb import SCUSBDevice, register_hotplug_device
from scc.tools import quat2euler

if TYPE_CHECKING:
	from usb1 import USBDevice, USBDeviceHandle

	from scc.drivers.sc2 import SC2Device
	from scc.drivers.sc_by_bt import SCByBt
	from scc.drivers.sc_by_cable import SCByCable
	from scc.drivers.steamdeck import Deck
	from scc.sccdaemon import SCCDaemon

_EUREL_SCALE = 32768.0 / PI  # radians -> the 2**15/PI fixed point EUREL_GYROS wants


def _quat_to_eurel(q1: int, q2: int, q3: int, q4: int) -> tuple[int, int, int]:
	"""Convert the SC1 hardware quaternion (q1=w q2=x q3=y q4=z, unit * 32767)
	to DS4/SC2-convention EUREL euler angles (pitch, yaw, roll) in 2**15/PI fixed
	point. Measured from held poses: the SC1 and SC2 use the identical quaternion
	convention -- x=pitch (nose-up +), y=roll (roll-right +), z=yaw (yaw-left +) --
	so this is byte-for-byte the sc2.parse_input mapping. Feeding these to the
	mapper (with EUREL_GYROS set) puts SC1 on the same single gyro code path as
	the DS4/SC2, where all the axis/sign conventions are hardware-verified."""
	w, x, y, z = q1 / 32767.0, q2 / 32767.0, q3 / 32767.0, q4 / 32767.0
	pitch = atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
	roll = asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
	yaw = atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
	return (
		int(-pitch * _EUREL_SCALE),
		int(-yaw * _EUREL_SCALE),
		int(roll * _EUREL_SCALE),
	)

VENDOR_ID = 0x28DE
PRODUCT_ID = 0x1142
FIRST_ENDPOINT = 2
FIRST_CONTROLIDX = 1
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
ControllerInput = namedtuple("ControllerInput", " ".join([x for x in NAMES if not x.startswith("ukn_")]))
SCI_NULL = ControllerInput._make(struct.unpack("<" + "".join(FORMATS), b"\x00" * 64))
STICKPRESS = 0b1000000000000000000000000000000


log = logging.getLogger("SCDongle")
_CALIB = bool(os.environ.get("SCC_GYRO_CALIB"))
if _CALIB:
	# The daemon leaves the root logger at WARNING; opt this logger into INFO so
	# the IMU-calibration dump is visible.
	log.setLevel(logging.INFO)
_calib_last_t = 0.0


def _log_imu_calib(idata) -> None:
	"""Throttled IMU dump for Steam Controller v1 gyro calibration (gate: env
	SCC_GYRO_CALIB=1). Logs the accel gravity vector, the raw hardware
	quaternion, what quat2euler currently makes of it, and the raw rates -- so
	held poses reveal the quaternion's real axis/sign convention vs the
	EUREL convention the DS4/SC2 use."""
	global _calib_last_t
	now = time.time()
	if now - _calib_last_t < 0.25:
		return
	_calib_last_t = now
	ax, ay, az = idata.accel_x, idata.accel_y, idata.accel_z
	mag = sqrt(ax * ax + ay * ay + az * az) or 1.0
	q = (idata.q1 / 32767.0, idata.q2 / 32767.0, idata.q3 / 32767.0, idata.q4 / 32767.0)
	qnorm = sqrt(sum(c * c for c in q)) * 32767.0
	e = quat2euler(*q)
	deg = 180.0 / PI
	log.info(
		"IMU-CALIB  accel unit=(% .2f % .2f % .2f) |a|=%6.0f  |  quat=(% 6d % 6d % 6d % 6d) |q|=%6.0f  |  "
		"quat2euler deg=(% 6.1f % 6.1f % 6.1f)  |  rates(gpitch,groll,gyaw)=(% 5d % 5d % 5d)",
		ax / mag, ay / mag, az / mag, mag,
		idata.q1, idata.q2, idata.q3, idata.q4, qnorm,
		e[0] * deg, e[1] * deg, e[2] * deg,
		idata.gpitch, idata.groll, idata.gyaw,
	)

class Dongle(SCUSBDevice):
	MAX_ENDPOINTS = 4
	_available_serials = set()  # used only is ignore_serials option is enabled

	def __init__(self, device: USBDevice, handle: USBDeviceHandle, daemon: SCCDaemon) -> None:
		self.daemon: SCCDaemon = daemon
		SCUSBDevice.__init__(self, device, handle)

		self.claim_by(klass=3, subclass=0, protocol=0)
		self._controllers: dict[int, SCController] = {}
		self._no_serial = []
		for i in range(Dongle.MAX_ENDPOINTS):
			# Steam dongle apparently can do only 4 controllers at once
			self.set_input_interrupt(FIRST_ENDPOINT + i, 64, self._on_input)

	def close(self) -> None:
		# Called when dongle is removed
		for c in self._controllers.values():
			self.daemon.remove_controller(c)
		self._controllers = {}
		SCUSBDevice.close(self)

	def _add_controller(self, endpoint: int) -> None:
		"""Called when new controller is detected either by HOTPLUG message or by receiving first input event."""
		ccidx: int = FIRST_CONTROLIDX + endpoint - FIRST_ENDPOINT
		c = SCController(self, ccidx, endpoint)
		c.configure()
		c.read_serial()
		self._controllers[endpoint] = c

	def _on_input(self, endpoint: int, data) -> None:
		tup = ControllerInput._make(struct.unpack(TUP_FORMAT, data))
		if tup.status == SCStatus.HOTPLUG:
			# Most of INPUT_FORMAT doesn't apply here
			# data[4] is the connect flag (2 == connected)
			if data[4] == 2:
				# Controller connected
				if endpoint not in self._controllers:
					self._add_controller(endpoint)
			# Controller disconnected
			elif endpoint in self._controllers:
				self.daemon.remove_controller(self._controllers[endpoint])
				self._controllers[endpoint].disconnected()
				del self._controllers[endpoint]
		elif tup.status == SCStatus.INPUT:
			if endpoint not in self._controllers:
				self._add_controller(endpoint)
			elif len(self._no_serial):
				for x in self._no_serial:
					x.read_serial()
				self._no_serial = []
			else:
				self._controllers[endpoint].input(tup)


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
	# The SC1 quaternion is converted to euler host-side (input()) and handed to
	# the mapper in q1-q3 as EUREL angles, so SC1 shares the DS4/SC2 gyro path.
	flags = ControllerFlags.EUREL_GYROS

	def __init__(self, driver: Deck | Dongle | SCByBt | SCByCable | SC2Device, ccidx: int, endpoint: int) -> None:
		Controller.__init__(self)
		self._driver: Deck | Dongle | SCByBt | SCByCable | SC2Device = driver
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

	def get_gui_config_file(self) -> str:
		# Steam Controller (v1): GUI-only config that puts the Steam logo on the
		# C button (image + side icon). Inherited by SCByCable / SCByBt.
		return "sc-config.json"

	def __repr__(self) -> str:
		return f"<SCWireless {self.get_id()}>"

	def input(self, idata: ControllerInput) -> None:
		old_state, self._old_state = self._old_state, idata
		if self.mapper:
			# if idata.buttons & SCButtons.LPAD:
			# # STICKPRESS button may signalize pressing stick instead
			# if (idata.buttons & STICKPRESS) and not (idata.buttons & STICKTILT):
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
					idata.type,
					idata.status,
					idata.seq,
					idata.buttons,
					idata.ltrig,
					idata.rtrig,
					lx,
					ly,
					rx,
					ry,
					idata.accel_x,
					idata.accel_y,
					idata.accel_z,
					idata.gpitch,
					idata.groll,
					idata.gyaw,
					idata.q1,
					idata.q2,
					idata.q3,
					idata.q4,
				)

			if _CALIB:
				_log_imu_calib(idata)  # logs the RAW quaternion, before conversion
			# Convert the hardware quaternion (q1-q4) to EUREL euler angles in
			# q1-q3 (q4 unused) so the mapper's gyro paths -- absolute, tilt,
			# lean-to-turn -- match the DS4/SC2 exactly. Only when the gyro is
			# streaming (a nonzero quaternion); disabled, q1-q4 are 0.
			if idata.q1 or idata.q2 or idata.q3 or idata.q4:
				p, y, r = _quat_to_eurel(idata.q1, idata.q2, idata.q3, idata.q4)
				idata = idata._replace(q1=p, q2=y, q3=r, q4=0)
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

	def read_serial(self) -> None:
		"""Requests and reads serial number from controller"""
		if Config()["ignore_serials"]:
			# Special exception for cases when controller drops instead of
			# sending serial number. See issue #103
			self.generate_serial()
			self.on_serial_got()
			return

		def cb(rawserial) -> None:
			size, serial = struct.unpack(">xBx12s49x", rawserial)
			if size > 1:
				serial = serial.strip(b" \x00").decode("ASCII")
				self._serial = serial
				self.on_serial_got()
			else:
				self._driver._no_serial.append(self)

		self._driver.make_request(
			self._ccidx, cb, struct.pack(">BBB61x", SCPacketType.GET_SERIAL, SCPacketLength.GET_SERIAL, 0x01),
			on_giveup=self._on_serial_giveup,
		)

	def _on_serial_giveup(self) -> None:
		"""Called when the GET_SERIAL request kept stalling. Add the controller
		with a generated id anyway, so it still appears (it just won't have a
		stable serial-based identity)."""
		log.warning("GET_SERIAL kept stalling for SC on endpoint %s; using a generated id", self._endpoint)
		self.generate_serial()
		self.on_serial_got()

	def generate_serial(self) -> None:
		"""Called only if ignore_serials is enabled"""
		if len(self._driver._available_serials) > 0:
			self._serial = self._driver._available_serials.pop()
		else:
			self._serial = self.get_id()
		log.debug("Not requesting serial number for SC %s", self._serial)

	def on_serial_got(self) -> None:
		try:
			log.debug("Got wireless SC with serial %s", self._serial)
		except UnicodeDecodeError:
			log.debug("Failed to decode wireless SC serial")
			self._serial = self._driver._available_serials.pop()
		serial = str(self._serial).strip()
		if not serial or serial in self._driver.daemon.get_active_ids():
			# A blank or already-used id would make two controllers collapse into
			# one in the GUI (it keys controllers by id). Keep them distinct by
			# falling back to a generated positional id.
			serial = self._generate_id()
		self._id = serial
		self._driver.daemon.add_controller(self)

	def apply_config(self, config: dict) -> None:
		self.configure(idle_timeout=int(config["idle_timeout"]), led_level=float(config["led_level"]))
		self._input_rotation_l = float(config["input_rotation_l"]) * PI / -180.0
		self._input_rotation_r = float(config["input_rotation_r"]) * PI / -180.0

	def disconnected(self) -> None:
		# If ignore_serials config option is enabled, fake serial used by this
		# controller is stored away and reused when next controller is connected
		if Config()["ignore_serials"]:
			self._driver._available_serials.add(self._serial)

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


def init(daemon: SCCDaemon, config: dict) -> Dongle | bool:
	"""Registers hotplug callback for controller dongle"""

	def cb(device: USBDevice, handle: USBDeviceHandle) -> Dongle:
		return Dongle(device, handle, daemon)

	register_hotplug_device(cb, VENDOR_ID, PRODUCT_ID)
	return True
