"""SC Controller - Dualshock 4 Driver.

Extends HID driver with DS4-specific options.
"""
from __future__ import annotations

import ctypes
import logging
import os
import struct
import sys
import zlib
from typing import TYPE_CHECKING, BinaryIO

import usb1
from evdev import ff
from hidraw import HIDRaw

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, ControllerFlags, HapticPos, SCButtons
from scc.controller import Controller
from scc.drivers.evdevdrv import (
	HAVE_EVDEV,
	EvdevController,
	get_axes,
	get_evdev_devices_from_syspath,
	make_new_device,
)
from scc.drivers.hiddrv import (
	BUTTON_COUNT,
	AxisData,
	AxisDataUnion,
	AxisMode,
	AxisModeData,
	AxisType,
	ButtonData,
	HatswitchModeData,
	HIDController,
	HIDDecoder,
	_lib,
	button_to_bit,
	hiddrv_test,
)
from scc.drivers.usb import USBDevice, register_hotplug_device
from scc.tools import init_logging, set_logging_level

if TYPE_CHECKING:
	from evdev import InputDevice

	from scc.sccdaemon import SCCDaemon

log = logging.getLogger("DS4")

VENDOR_ID = 0x054C
PRODUCT_ID = 0x09CC
DS4_V1_PRODUCT_ID = 0x05C4

# CUH-ZCT2x exposes endpoint 0x03 as isochronous audio output and the HID
# interrupt output endpoint as 0x02.
DS4_USB_OUTPUT_ENDPOINT = 2
DS4_USB_OUTPUT_REPORT_SIZE = 32
DS4_USB_OUTPUT_REPORT_ID = 0x05
DS4_USB_OUTPUT_VALID_MOTOR = 0x01
DS4_BT_OUTPUT_REPORT_SIZE = 78
DS4_BT_OUTPUT_REPORT_ID = 0x11
DS4_BT_OUTPUT_HW_CONTROL = 0xC4
DS4_BT_OUTPUT_VALID_MOTOR = 0x01
DS4_BT_OUTPUT_CRC_SEED = 0xA2


class DS4Controller(Controller):
	# Most of axes are the same
	BUTTON_MAP = (
		SCButtons.X,
		SCButtons.A,
		SCButtons.B,
		SCButtons.Y,
		SCButtons.LB,
		SCButtons.RB,
		1 << 64,
		1 << 64,
		SCButtons.BACK,
		SCButtons.START,
		SCButtons.STICKPRESS,
		SCButtons.RPAD,
		SCButtons.C,
		SCButtons.CPADPRESS,
	)

	flags = (
		ControllerFlags.EUREL_GYROS
		| ControllerFlags.HAS_RSTICK
		| ControllerFlags.HAS_CPAD
		| ControllerFlags.HAS_DPAD
		| ControllerFlags.SEPARATE_STICK
		| ControllerFlags.NO_GRIPS
	)

	def __init__(self, daemon: SCCDaemon) -> None:
		self.daemon: SCCDaemon = daemon
		Controller.__init__(self)

	def _load_hid_descriptor(self, config, max_size, vid, pid, test_mode):
		# Overrided and hardcoded
		self._decoder = HIDDecoder()
		self._decoder.axes[AxisType.AXIS_LPAD_X] = AxisData(
			mode=AxisMode.HATSWITCH,
			byte_offset=5,
			size=8,
			data=AxisDataUnion(
				hatswitch=HatswitchModeData(
					button=SCButtons.LPAD | SCButtons.LPADTOUCH,
					min=STICK_PAD_MIN,
					max=STICK_PAD_MAX,
				),
			),
		)
		self._decoder.axes[AxisType.AXIS_STICK_X] = AxisData(
			mode=AxisMode.AXIS,
			byte_offset=1,
			size=8,
			data=AxisDataUnion(
				axis=AxisModeData(
					scale=1.0,
					offset=-127.5,
					clamp_max=257,
					deadzone=10,
				),
			),
		)
		self._decoder.axes[AxisType.AXIS_STICK_Y] = AxisData(
			mode=AxisMode.AXIS,
			byte_offset=2,
			size=8,
			data=AxisDataUnion(
				axis=AxisModeData(
					scale=-1.0,
					offset=127.5,
					clamp_max=257,
					deadzone=10,
				),
			),
		)
		self._decoder.axes[AxisType.AXIS_RPAD_X] = AxisData(
			mode=AxisMode.AXIS,
			byte_offset=3,
			size=8,
			data=AxisDataUnion(
				axis=AxisModeData(
					button=SCButtons.RPADTOUCH,
					scale=1.0,
					offset=-127.5,
					clamp_max=257,
					deadzone=10,
				),
			),
		)
		self._decoder.axes[AxisType.AXIS_RPAD_Y] = AxisData(
			mode=AxisMode.AXIS,
			byte_offset=4,
			size=8,
			data=AxisDataUnion(
				axis=AxisModeData(
					button=SCButtons.RPADTOUCH,
					scale=-1.0,
					offset=127.5,
					clamp_max=257,
					deadzone=10,
				),
			),
		)
		self._decoder.axes[AxisType.AXIS_LTRIG] = AxisData(
			mode=AxisMode.AXIS,
			byte_offset=8,
			size=8,
			data=AxisDataUnion(
				axis=AxisModeData(
					scale=1.0,
					clamp_max=1,
					deadzone=10,
				),
			),
		)
		self._decoder.axes[AxisType.AXIS_RTRIG] = AxisData(
			mode=AxisMode.AXIS,
			byte_offset=9,
			size=8,
			data=AxisDataUnion(
				axis=AxisModeData(
					scale=1.0,
					clamp_max=1,
					deadzone=10,
				),
			),
		)
		self._decoder.axes[AxisType.AXIS_GPITCH] = AxisData(mode=AxisMode.DS4ACCEL, byte_offset=13)
		self._decoder.axes[AxisType.AXIS_GROLL] = AxisData(mode=AxisMode.DS4ACCEL, byte_offset=17)
		self._decoder.axes[AxisType.AXIS_GYAW] = AxisData(mode=AxisMode.DS4ACCEL, byte_offset=15)
		self._decoder.axes[AxisType.AXIS_Q1] = AxisData(mode=AxisMode.DS4GYRO, byte_offset=23)
		self._decoder.axes[AxisType.AXIS_Q2] = AxisData(mode=AxisMode.DS4GYRO, byte_offset=19)
		self._decoder.axes[AxisType.AXIS_Q3] = AxisData(mode=AxisMode.DS4GYRO, byte_offset=21)

		self._decoder.axes[AxisType.AXIS_CPAD_X] = AxisData(mode=AxisMode.DS4TOUCHPAD, byte_offset=36)
		self._decoder.axes[AxisType.AXIS_CPAD_Y] = AxisData(mode=AxisMode.DS4TOUCHPAD, byte_offset=37, bit_offset=4)
		self._decoder.buttons = ButtonData(
			enabled=True,
			byte_offset=5,
			bit_offset=4,
			size=14,
			button_count=14,
		)

		if test_mode:
			for x in range(BUTTON_COUNT):
				self._decoder.buttons.button_map[x] = x
		else:
			for x in range(BUTTON_COUNT):
				self._decoder.buttons.button_map[x] = 64
			for x, sc in enumerate(DS4Controller.BUTTON_MAP):
				self._decoder.buttons.button_map[x] = button_to_bit(sc)

	def input(self, endpoint: int, data: bytes | bytearray) -> None:
		# Special override for CPAD touch button
		if _lib.decode(ctypes.byref(self._decoder), bytes(data)) and self.mapper:
			if data[35] >> 7:
				# cpad is not touched
				self._decoder.state.buttons &= ~SCButtons.CPADTOUCH
			else:
				self._decoder.state.buttons |= SCButtons.CPADTOUCH
			self.mapper.input(self, self._decoder.old_state, self._decoder.state)

	def get_gyro_enabled(self) -> bool:
		# Cannot be actually turned off, so it's always active
		# TODO: Maybe emulate turning off?
		return True

	def get_type(self) -> str:
		return "ds4"

	def get_gui_config_file(self) -> str:
		return "ds4-config.json"

	def __repr__(self) -> str:
		return f"<DS4Controller {self.get_id()}>"

	def _generate_id(self) -> str:
		"""ID is generated as 'ds4' or 'ds4:X' where 'X' starts as 1 and increases as controllers with same ids are connected."""
		magic_number = 1
		id = "ds4"
		while id in self.daemon.get_active_ids():
			id = f"ds4:{magic_number}"
			magic_number += 1
		return id


class DS4HIDController(DS4Controller, HIDController):
	def __init__(self, device: USBDevice, daemon: SCCDaemon, handle: usb1.USBDeviceHandle, config_file, config, test_mode=False) -> None:
		self._feedback_endpoint = self._find_feedback_endpoint(device)
		self._feedback_output = bytearray(DS4_USB_OUTPUT_REPORT_SIZE)
		self._feedback_output[0] = DS4_USB_OUTPUT_REPORT_ID
		self._feedback_output[1] = DS4_USB_OUTPUT_VALID_MOTOR
		self._feedback_pending = False
		self._feedback_cancel_tasks = [None, None]
		HIDController.__init__(self, device, daemon, handle, config_file, config, test_mode)
		log.debug("DS4 %s using USB/libusb", self.get_id())

	@staticmethod
	def _find_feedback_endpoint(device: USBDevice) -> int:
		"""Return the interrupt OUT endpoint belonging to the HID interface."""
		for interface in device[0]:
			for setting in interface:
				if setting.getClass() != 3:
					continue
				for endpoint in setting:
					address = endpoint.getAddress()
					if endpoint.getAttributes() == 3 and address & usb1.ENDPOINT_IN == 0:
						return address
		return DS4_USB_OUTPUT_ENDPOINT

	def feedback(self, data) -> None:
		position, amplitude, period, count = data.data
		amplitude = min(amplitude, 0x8000) / 0x8000
		right_amplitude = int(amplitude * 0xFF)
		left_amplitude = int(amplitude * 0xFF)

		motors = []
		if position in (HapticPos.LEFT, HapticPos.BOTH):
			self._feedback_output[5] = left_amplitude
			motors.append((0, 5))
		if position in (HapticPos.RIGHT, HapticPos.BOTH):
			self._feedback_output[4] = right_amplitude
			motors.append((1, 4))
		self._feedback_pending = True

		duration = max(float(period) * count / 0x10000, 0.02)
		for task_index, report_index in motors:
			task = self._feedback_cancel_tasks[task_index]
			if task:
				task.cancel()
			if amplitude == 0 or count == 0:
				self._feedback_cancel_tasks[task_index] = None
				continue

			def clear_feedback(mapper, task_index=task_index, report_index=report_index):
				self._feedback_output[report_index] = 0
				self._feedback_pending = True
				self._feedback_cancel_tasks[task_index] = None

			self._feedback_cancel_tasks[task_index] = self.mapper.schedule(duration, clear_feedback)

	def flush(self) -> None:
		HIDController.flush(self)
		if self._feedback_pending:
			self.handle.interruptWrite(self._feedback_endpoint, bytes(self._feedback_output))
			self._feedback_pending = False


class DS4HIDRawController(DS4Controller):
	def __init__(self, driver: DS4HIDRawDriver, syspath: str, hidrawdev: HIDRaw, device_file: BinaryIO, vid, pid) -> None:
		self.driver: DS4HIDRawDriver = driver
		self.syspath: str = syspath

		DS4Controller.__init__(self, driver.daemon)

		self._device_name: str = hidrawdev.getName()
		self._hidrawdev: HIDRaw = hidrawdev
		self._device_file: BinaryIO = device_file
		self._fileno: int = self._device_file.fileno()
		self._id: str = self._generate_id() if driver else "-"
		self._closed: bool = False
		self._feedback_output = bytearray(DS4_BT_OUTPUT_REPORT_SIZE)
		self._feedback_output[0] = DS4_BT_OUTPUT_REPORT_ID
		self._feedback_output[1] = DS4_BT_OUTPUT_HW_CONTROL
		self._feedback_output[3] = DS4_BT_OUTPUT_VALID_MOTOR
		self._feedback_cancel_tasks = [None, None]

		self._packet_size = 78
		self._load_hid_descriptor(driver.config, self._packet_size, vid, pid, None)

		# self._set_operational()
		self.read_serial()
		self._poller = self.daemon.get_poller()
		if self._poller:
			self._poller.register(self._fileno, self._poller.POLLIN, self._input)
		self.daemon.get_device_monitor().add_remove_callback(syspath, self.close)
		self.daemon.add_controller(self)
		log.debug("DS4 %s using Bluetooth/hidraw (%s)", self.get_id(), self.syspath)

	def read_serial(self) -> None:
		self._serial = (self._hidrawdev.getPhysicalAddress().replace(b":", b""))

	def _input(self, *args) -> None:
		try:
			data = self._device_file.read(self._packet_size)
		except Exception as error:
			log.debug("DS4 Bluetooth hidraw device disconnected: %s", error)
			self.close()
			return
		if data[0] != 0x11:
			return
		self.input(self._fileno, data[2:])

	def close(self, *args) -> None:
		if self._closed:
			return
		self._closed = True
		if self._poller:
			self._poller.unregister(self._fileno)

		self.daemon.remove_controller(self)
		self._device_file.close()

	def _write_feedback_report(self) -> None:
		crc = zlib.crc32(bytes((DS4_BT_OUTPUT_CRC_SEED,)))
		crc = zlib.crc32(self._feedback_output[:-4], crc)
		struct.pack_into("<I", self._feedback_output, DS4_BT_OUTPUT_REPORT_SIZE - 4, crc)
		#log.debug("DS4 Bluetooth output: motors=(%s,%s)", self._feedback_output[7], self._feedback_output[6])
		self._device_file.write(bytes(self._feedback_output))

	def feedback(self, data) -> None:
		position, amplitude, period, count = data.data
		amplitude = min(amplitude, 0x8000) / 0x8000
		motor_amplitude = int(amplitude * 0xFF)

		motors = []
		if position in (HapticPos.LEFT, HapticPos.BOTH):
			self._feedback_output[7] = motor_amplitude
			motors.append((0, 7))
		if position in (HapticPos.RIGHT, HapticPos.BOTH):
			self._feedback_output[6] = motor_amplitude
			motors.append((1, 6))

		duration = max(float(period) * count / 0x10000, 0.02)
		for task_index, report_index in motors:
			task = self._feedback_cancel_tasks[task_index]
			if task:
				task.cancel()
			if amplitude == 0 or count == 0:
				self._feedback_cancel_tasks[task_index] = None
				continue

			def clear_feedback(mapper, task_index=task_index, report_index=report_index):
				self._feedback_output[report_index] = 0
				self._feedback_cancel_tasks[task_index] = None
				self._write_feedback_report()

			self._feedback_cancel_tasks[task_index] = self.mapper.schedule(duration, clear_feedback)

		self._write_feedback_report()

	def turnoff(self) -> None:
		try:
			self.daemon.get_device_monitor().disconnect_bluetooth(self.syspath)
		except OSError as error:
			log.warning("Failed to turn off DS4 Bluetooth controller: %s", error)


class DS4HIDRawDriver:
	def __init__(self, daemon: SCCDaemon, config: dict) -> None:
		self.config = config
		self.daemon = daemon
		daemon.get_device_monitor().add_callback("bluetooth", VENDOR_ID, PRODUCT_ID, self.make_bt_hidraw_callback, None)
		daemon.get_device_monitor().add_callback("bluetooth", VENDOR_ID, DS4_V1_PRODUCT_ID, self.make_bt_hidraw_callback, None)

	def retry(self, syspath: str) -> None:
		pass

	def make_bt_hidraw_callback(self, syspath: str, vid, pid, *whatever) -> DS4HIDRawController | None:
		log.debug("DS4 Bluetooth callback: syspath=%s vid=%04x pid=%04x", syspath, vid, pid)
		hidrawname = self.daemon.get_device_monitor().get_hidraw(syspath)
		if hidrawname is None:
			return None
		try:
			device_file = open(os.path.join("/dev/", hidrawname), "r+b", buffering=0)
			hidraw = HIDRaw(device_file)
			return DS4HIDRawController(self, syspath, hidraw, device_file, vid, pid)
		except Exception as e:
			log.exception(e)
			return None

	def get_device_name(self) -> str:
		return "Dualshock 4 over Bluetooth HIDRaw"

	def get_type(self) -> str:
		return "ds4bt_hidraw"

class DS4EvdevController(EvdevController):
	TOUCH_FACTOR_X = STICK_PAD_MAX / 940.0
	TOUCH_FACTOR_Y = STICK_PAD_MAX / 470.0
	BUTTON_MAP = {
		304: "A",
		305: "B",
		307: "Y",
		308: "X",
		310: "LB",
		311: "RB",
		314: "BACK",
		315: "START",
		316: "C",
		317: "STICKPRESS",
		318: "RPAD",
		# 319: "CPAD",
	}
	AXIS_MAP = {
		0: {"axis": "stick_x", "deadzone": 4, "max": 255, "min": 0},
		1: {"axis": "stick_y", "deadzone": 4, "max": 0, "min": 255},
		3: {"axis": "rpad_x", "deadzone": 4, "max": 255, "min": 0},
		4: {"axis": "rpad_y", "deadzone": 8, "max": 0, "min": 255},
		2: {"axis": "ltrig", "max": 255, "min": 0},
		5: {"axis": "rtrig", "max": 255, "min": 0},
		16: {"axis": "lpad_x", "deadzone": 0, "max": 1, "min": -1},
		17: {"axis": "lpad_y", "deadzone": 0, "max": -1, "min": 1},
	}
	BUTTON_MAP_OLD = {
		304: "X",
		305: "A",
		306: "B",
		307: "Y",
		308: "LB",
		309: "RB",
		312: "BACK",
		313: "START",
		314: "STICKPRESS",
		315: "RPAD",
		316: "C",
		# 317: "CPAD",
	}
	AXIS_MAP_OLD = {
		0: {"axis": "stick_x", "deadzone": 4, "max": 255, "min": 0},
		1: {"axis": "stick_y", "deadzone": 4, "max": 0, "min": 255},
		2: {"axis": "rpad_x", "deadzone": 4, "max": 255, "min": 0},
		5: {"axis": "rpad_y", "deadzone": 8, "max": 0, "min": 255},
		3: {"axis": "ltrig", "max": 32767, "min": -32767},
		4: {"axis": "rtrig", "max": 32767, "min": -32767},
		16: {"axis": "lpad_x", "deadzone": 0, "max": 1, "min": -1},
		17: {"axis": "lpad_y", "deadzone": 0, "max": -1, "min": 1},
	}
	GYRO_MAP = {
		EvdevController.ECODES.ABS_RX: ("gpitch", 0.01),
		EvdevController.ECODES.ABS_RY: ("gyaw", 0.01),
		EvdevController.ECODES.ABS_RZ: ("groll", 0.01),
		EvdevController.ECODES.ABS_X: (None, 1),  # 'q2'
		EvdevController.ECODES.ABS_Y: (None, 1),  # 'q3'
		EvdevController.ECODES.ABS_Z: (None, -1),  # 'q1'
	}
	flags = (
		ControllerFlags.EUREL_GYROS
		| ControllerFlags.HAS_RSTICK
		| ControllerFlags.HAS_CPAD
		| ControllerFlags.HAS_DPAD
		| ControllerFlags.SEPARATE_STICK
		| ControllerFlags.NO_GRIPS
	)

	def __init__(
		self,
		daemon: SCCDaemon,
		controllerdevice: InputDevice[str],
		gyro: InputDevice[str],
		touchpad: InputDevice[str],
	) -> None:
		config = {
			"axes": DS4EvdevController.AXIS_MAP,
			"buttons": DS4EvdevController.BUTTON_MAP,
			"dpads": {},
		}
		if controllerdevice.info.version & 0x8000 == 0:
			# Older kernel uses different mappings
			# see kernel source, drivers/hid/hid-sony.c#L2748
			config["axes"] = DS4EvdevController.AXIS_MAP_OLD
			config["buttons"] = DS4EvdevController.BUTTON_MAP_OLD
		self._gyro = gyro
		self._touchpad = touchpad
		self._feedback_effect_id: int | None = None
		for device in (self._gyro, self._touchpad):
			if device:
				device.grab()
		EvdevController.__init__(self, daemon, controllerdevice, None, config)
		log.debug("DS4 %s using evdev (%s)", self.get_id(), controllerdevice.path)
		if self.poller:
			self.poller.register(touchpad.fd, self.poller.POLLIN, self._touchpad_input)
			self.poller.register(gyro.fd, self.poller.POLLIN, self._gyro_input)

	def _gyro_input(self, *a) -> None:
		new_state = self._state
		try:
			for event in self._gyro.read():
				if event.type == self.ECODES.EV_ABS:
					axis, factor = DS4EvdevController.GYRO_MAP[event.code]
					if axis:
						new_state = new_state._replace(**{axis: int(event.value * factor)})
		except OSError:
			# Errors here are not even reported, evdev class handles important ones
			return

		if new_state is not self._state:
			old_state, self._state = self._state, new_state
			if self.mapper:
				self.mapper.input(self, old_state, new_state)

	def _touchpad_input(self, *a):
		new_state = self._state
		try:
			for event in self._touchpad.read():
				if event.type == self.ECODES.EV_ABS:
					if event.code == self.ECODES.ABS_MT_POSITION_X:
						value = event.value * DS4EvdevController.TOUCH_FACTOR_X
						value = STICK_PAD_MIN + int(value)
						new_state = new_state._replace(cpad_x=value)
					elif event.code == self.ECODES.ABS_MT_POSITION_Y:
						value = event.value * DS4EvdevController.TOUCH_FACTOR_Y
						value = STICK_PAD_MAX - int(value)
						new_state = new_state._replace(cpad_y=value)
				elif event.type == 0:
					pass
				elif event.code == self.ECODES.BTN_LEFT:
					if event.value == 1:
						b = new_state.buttons | SCButtons.CPADPRESS
						new_state = new_state._replace(buttons=b)
					else:
						b = new_state.buttons & ~SCButtons.CPADPRESS
						new_state = new_state._replace(buttons=b)
				elif event.code == self.ECODES.BTN_TOUCH:
					if event.value == 1:
						b = new_state.buttons | SCButtons.CPADTOUCH
						new_state = new_state._replace(buttons=b)
					else:
						b = new_state.buttons & ~SCButtons.CPADTOUCH
						new_state = new_state._replace(buttons=b, cpad_x=0, cpad_y=0)
		except OSError:
			# Errors here are not even reported, evdev class handles important ones
			return

		if new_state is not self._state:
			old_state, self._state = self._state, new_state
			if self.mapper:
				self.mapper.input(self, old_state, new_state)

	def close(self) -> None:
		self._stop_feedback()
		EvdevController.close(self)
		for device in (self._gyro, self._touchpad):
			try:
				self.poller.unregister(device.fd)
				device.ungrab()
			except Exception:
				pass

	def get_gyro_enabled(self) -> bool:
		# Cannot be actually turned off, so it's always active
		# TODO: Maybe emulate turning off?
		return True

	def _stop_feedback(self) -> None:
		if self._feedback_effect_id is None:
			return
		try:
			self.device.write(self.ECODES.EV_FF, self._feedback_effect_id, 0)
			self.device.erase_effect(self._feedback_effect_id)
		except OSError as error:
			log.debug("Failed to stop DS4 evdev rumble effect: %s", error)
		finally:
			self._feedback_effect_id = None

	def feedback(self, data) -> None:
		position, amplitude, period, count = data.data
		self._stop_feedback()
		if amplitude == 0 or count == 0:
			return

		magnitude = min(amplitude * 2, 0xFFFF)
		strong_magnitude = magnitude if position in (HapticPos.LEFT, HapticPos.BOTH) else 0
		weak_magnitude = magnitude if position in (HapticPos.RIGHT, HapticPos.BOTH) else 0
		duration = max(min(round(float(period) * count / 0x10000 * 1000), 0xFFFF), 20)
		effect = ff.Effect(
			self.ECODES.FF_RUMBLE,
			-1,
			0,
			ff.Trigger(0, 0),
			ff.Replay(duration, 0),
			ff.EffectType(
				ff_rumble_effect=ff.Rumble(
					strong_magnitude=strong_magnitude,
					weak_magnitude=weak_magnitude,
				),
			),
		)
		try:
			self._feedback_effect_id = self.device.upload_effect(effect)
			self.device.write(self.ECODES.EV_FF, self._feedback_effect_id, 1)
		except OSError as error:
			self._feedback_effect_id = None
			log.warning("Failed to play DS4 evdev rumble effect: %s", error)

	def get_type(self) -> str:
		return "ds4evdev"

	def get_gui_config_file(self) -> str:
		return "ds4-config.json"

	def __repr__(self) -> str:
		return f"<DS4EvdevController {self.get_id()}>"

	def _generate_id(self) -> str:
		"""ID is generated as 'ds4' or 'ds4:X' where 'X' starts as 1 and increases as controllers with same ids are connected."""
		magic_number = 1
		id = "ds4"
		while id in self.daemon.get_active_ids():
			id = f"ds4:{magic_number}"
			magic_number += 1
		return id


def init(daemon: SCCDaemon, config: dict) -> bool:
	"""Register hotplug callback for DS4 device."""

	def hid_callback(device, handle) -> DS4HIDController:
		return DS4HIDController(device, daemon, handle, None, None)

	def make_evdev_device(sys_dev_path: str, *whatever):
		devices = get_evdev_devices_from_syspath(sys_dev_path)
		# With kernel 4.10 or later, PS4 controller pretends to be 3 different devices.
		# 1st, determining which one is actual controller is needed
		controllerdevice = None
		for device in devices:
			count = len(get_axes(device))
			if count == 8:
				# 8 axes - Controller
				controllerdevice = device
		if not controllerdevice:
			log.debug("DS4 evdev controller node is not ready; discovery will retry")
			return None
		# 2nd, find motion sensor and touchpad with physical address matching controllerdevice
		gyro, touchpad = None, None
		phys = device.phys.split("/")[0]
		for device in devices:
			if device.phys.startswith(phys):
				axes = get_axes(device)
				count = len(axes)
				if count == 6:
					# 6 axes
					if EvdevController.ECODES.ABS_MT_POSITION_X in axes:
						# kernel 4.17+ - touchpad
						touchpad = device
					else:
						# gyro sensor
						gyro = device
				elif count == 4:
					# 4 axes - Touchpad
					touchpad = device
		# 3rd, do a magic
		if controllerdevice and gyro and touchpad:
			return make_new_device(DS4EvdevController, controllerdevice, gyro, touchpad)

	def fail_cb(syspath: str, vid: int, pid: int) -> None:
		if HAVE_EVDEV:
			log.warning("Failed to acquire USB device, falling back to evdev driver. This is far from optimal.")
			make_evdev_device(syspath)
		else:
			log.error(
				"Failed to acquire USB device and evdev is not available. Everything is lost and DS4 support disabled.",
			)
			# TODO: Maybe add_error here, but error reporting needs a little rework, so it's not treated as fatal
			# daemon.add_error("ds4", "No access to DS4 device")

	if config["drivers"].get("hiddrv") or (HAVE_EVDEV and config["drivers"].get("evdevdrv")):
		# DS4 v.2
		register_hotplug_device(hid_callback, VENDOR_ID, PRODUCT_ID, on_failure=fail_cb)
		# DS4 v.1
		register_hotplug_device(hid_callback, VENDOR_ID, DS4_V1_PRODUCT_ID, on_failure=fail_cb)
		if config["drivers"].get("hiddrv"):
			# Only enable HIDRaw support for BT connections if hiddrv is enabled
			_drv = DS4HIDRawDriver(daemon, config)
		elif HAVE_EVDEV and config["drivers"].get("evdevdrv"):
			# DS4 v.2
			daemon.get_device_monitor().add_callback("bluetooth", VENDOR_ID, PRODUCT_ID, make_evdev_device, None)
			# DS4 v.1
			daemon.get_device_monitor().add_callback("bluetooth", VENDOR_ID, DS4_V1_PRODUCT_ID, make_evdev_device, None)
		return True
	log.warning("Neither HID nor Evdev driver is enabled, DS4 support cannot be enabled.")
	return False


if __name__ == "__main__":
	""" Called when executed as script """
	init_logging()
	set_logging_level(True, True)
	sys.exit(hiddrv_test(DS4HIDController, ["054c:09cc"]))
