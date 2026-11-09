"""Generic HIDAPI input for explicitly registered controllers on every platform."""

from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import time
from typing import TYPE_CHECKING

try:
	import hid
except ImportError:
	hid = None

from scc.constants import ControllerFlags
from scc.controller import Controller
from scc.device_config import load_device_config
from scc.lib.hid_registration import RawHIDInput, map_inputs, should_skip_hid_device
from scc.paths import get_config_path

if TYPE_CHECKING:
	from scc.sccdaemon import SCCDaemon

log = logging.getLogger("HIDAPI")

SCAN_INTERVAL = 1.0
MAX_REPORTS_PER_TICK = 32


class HIDControllerInput(ctypes.Structure):
	_fields_ = [
		("buttons", ctypes.c_uint32),
		("lstick_x", ctypes.c_int32),
		("lstick_y", ctypes.c_int32),
		("rstick_x", ctypes.c_int32),
		("rstick_y", ctypes.c_int32),
		("lpad_x", ctypes.c_int32),
		("lpad_y", ctypes.c_int32),
		("rpad_x", ctypes.c_int32),
		("rpad_y", ctypes.c_int32),
		("ltrig", ctypes.c_int32),
		("rtrig", ctypes.c_int32),
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
		("dpad_x", ctypes.c_int32),
		("dpad_y", ctypes.c_int32),
	]


class HIDAPIController(Controller):
	flags = (
		ControllerFlags.HAS_RSTICK
		| ControllerFlags.HAS_DPAD
		| ControllerFlags.SEPARATE_LSTICK
		| ControllerFlags.NO_GRIPS
	)

	def __init__(self, driver: HIDAPIDriver, info: dict, mapping_name: str, mapping: dict, config_file: str) -> None:
		super().__init__()
		self.driver = driver
		self.daemon = driver.daemon
		self.path = info["path"]
		self.config_file = config_file
		self.config = mapping
		self._state = HIDControllerInput()
		self._closed = False
		self.device = hid.device()
		self.device.open_path(self.path)
		self.device.set_nonblocking(True)
		try:
			try:
				descriptor = bytes(self.device.get_report_descriptor())
			except TypeError:
				# Some python-hidapi releases require an explicit maximum size,
				# while others expose only the zero-argument form
				log.warning("Type'err'd on the descriptor")
				descriptor = bytes(self.device.get_report_descriptor(4096))
			self._raw = RawHIDInput(descriptor)
			self._packet_size = max(self._raw.report_sizes.values())
		except AttributeError as exc:
			self.device.close()
			raise RuntimeError("This hidapi build does not expose get_report_descriptor()") from exc
		except Exception:
			self.device.close()
			raise

		vendor_id, product_id = int(info["vendor_id"]), int(info["product_id"])
		self._id = self._generate_id(f"hid{vendor_id:04x}:{product_id:04x}")
		self.mapping_name = mapping_name
		self._bluetooth = self._detect_bluetooth(info)
		self.daemon.add_controller(self)
		log.info("Opened %s using registered mapping %r", self._id, mapping_name)

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
				report = self.device.read(max(64, self._packet_size))
				if not report:
					break
				if not self._raw.read(bytes(report)):
					continue
				state = HIDControllerInput(**map_inputs(self._raw, self.config))
				if bytes(self._state) != bytes(state) and self.mapper:
					self.mapper.input(self, self._state, state)
				self._state = state
		except (OSError, ValueError):
			log.exception("Generic HID controller %s read failed", self._id)
			self.close()

	def get_type(self) -> str:
		return "hid"

	def get_gui_config_file(self) -> str:
		return self.config_file

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


class HIDAPIDriver:
	def __init__(self, daemon: SCCDaemon) -> None:
		self.daemon = daemon
		self.controllers: dict[bytes | str, HIDAPIController] = {}
		self._failed_paths: set[bytes | str] = set()
		self._seen_paths: set[bytes | str] = set()
		self._did_initial_scan = False
		self._next_scan = 0.0
		self.configs = {}

	def rescan(self) -> None:
		"""Reload registrations and reconnect devices whose mapping changed."""
		configs = {}
		path = os.path.join(get_config_path(), "devices")
		if os.path.isdir(path):
			for name in sorted(os.listdir(path)):
				match = re.fullmatch(r"(?:hid|hidapi)-([0-9a-fA-F]{4})_([0-9a-fA-F]{4})-.*\.json", name)
				if match is None:
					continue
				filename = os.path.join(path, name)
				try:
					config = load_device_config(filename)
					if config.get("input_backend") == "hidapi":
						configs[tuple(int(x, 16) for x in match.groups())] = (filename, config)
				except (OSError, ValueError, TypeError):
					log.exception("Failed to load HID registration %s", filename)
		if configs != self.configs:
			self.close()
			self.configs = configs
		self._failed_paths.clear()
		self.scan()

	def start(self) -> None:
		self.rescan()

	def mainloop(self) -> None:
		for controller in tuple(self.controllers.values()):
			controller.poll()
		if time.monotonic() >= self._next_scan:
			self.scan()

	def scan(self) -> None:
		self._next_scan = time.monotonic() + SCAN_INTERVAL
		found = {}
		seen = set()
		try:
			devices = hid.enumerate()
			if not self._did_initial_scan:
				log.debug("HIDAPI enumerated %d interface(s)", len(devices))
				self._did_initial_scan = True
			for info in devices:
				identity = int(info.get("vendor_id", 0)), int(info.get("product_id", 0))
				path = info.get("path")
				if path is None:
					continue
				registration = self.configs.get(identity)
				if registration is None or should_skip_hid_device(info):
					continue
				config_file, config = registration
				mapping = (str(info.get("product_string") or identity), config)
				seen.add(path)
				is_new = path not in self._seen_paths
				if is_new:
					log.debug(
						"Discovered mapped HID interface %04x:%04x %r, usage %r:%r, path %r",
						identity[0],
						identity[1],
						info.get("product_string"),
						info.get("usage_page"),
						info.get("usage"),
						path,
					)

				found[path] = (info, mapping, config_file)
		except Exception:
			log.exception("Failed to enumerate generic HID controllers")
			return
		self._seen_paths = seen

		for path, (info, (mapping_name, mapping), config_file) in found.items():
			if path in self.controllers or path in self._failed_paths:
				continue
			try:
				self.controllers[path] = HIDAPIController(self, info, mapping_name, mapping, config_file)
			except (OSError, RuntimeError, TypeError, ValueError):
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


_driver: HIDAPIDriver | None = None


def init(daemon: SCCDaemon, config: dict) -> bool:
	global _driver
	if sys.platform not in ("linux", "win32", "darwin"):
		return False
	if hid is None:
		log.error("Install sccontroller[hidapi] to enable the HIDAPI backend")
		return False
	_driver = HIDAPIDriver(daemon)
	daemon.add_mainloop(_driver.mainloop)
	daemon.add_on_exit(_driver.close)
	daemon.add_on_rescan(_driver.rescan)
	return True


def start(daemon: SCCDaemon) -> None:
	if _driver is not None:
		_driver.start()
