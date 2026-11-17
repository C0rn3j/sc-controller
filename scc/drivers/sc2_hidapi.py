"""Steam Controller (2026) wired USB and wireless Puck through HIDAPI.

The Linux libusb driver remains available as ``sc2``. Enable only one SC2
backend at a time. Bluetooth is not implemented by either backend.
"""

from __future__ import annotations

import logging
import sys
import time
from concurrent.futures import Future
from threading import Thread
from typing import TYPE_CHECKING

try:
	import hid
except ImportError:
	hid = None

from scc.constants import ControllerFlags, HapticPos, SCButtons
from scc.controller import Controller, HapticData
from scc.lib import sc2 as protocol

if TYPE_CHECKING:
	from scc.sccdaemon import SCCDaemon

log = logging.getLogger("SC2HIDAPI")
SCAN_INTERVAL = 1.0
MAX_REPORTS_PER_TICK = 32


class SC2Controller(Controller):
	flags = (
		ControllerFlags.EUREL_GYROS | ControllerFlags.SEPARATE_LSTICK
		| ControllerFlags.HAS_RSTICK | ControllerFlags.HAS_DPAD
	)

	def __init__(self, slot: SC2HIDDevice) -> None:
		super().__init__()
		self.slot = slot
		self._old_state = protocol.SC2_NULL
		self._led_level = 10
		self._enable_gyros = False
		self._closed = False
		# The Puck serial identifies the receiver, not a controller. Include the
		# interface so its four slots retain separate profiles and IDs.
		serial = slot.info.get("serial_number") or str(slot.path)
		preferred = f"sc2:{serial}:{slot.info.get('interface_number', 0)}"
		self._id = preferred
		index = 1
		while self._id in slot.daemon.get_active_ids():
			self._id = f"{preferred}:{index}"
			index += 1

	def get_type(self) -> str:
		return "sc2"

	def get_gui_config_file(self) -> str:
		return "sc2-config.json"

	def clear_mappings(self) -> None:
		self.slot.send_feature(b"\x81\x00")

	def configure(self, idle_timeout=None, enable_gyros=None, led_level=None) -> None:
		# Same captured configuration blocks as the Linux driver. The idle and
		# gyro registers are still unknown; preserve its current behavior.
		if led_level is not None:
			self._led_level = led_level
		self.slot.send_feature(bytes.fromhex("87 0f 30 18 00 07 07 00 08 07 00 31 02 00 52 03"))
		self.slot.send_feature(bytes((0x87, 0x03, 0x2D, int(self._led_level))))

	def apply_config(self, config: dict) -> None:
		self.configure(idle_timeout=int(config["idle_timeout"]), led_level=float(config["led_level"]))

	def set_led_level(self, level: int) -> None:
		level = min(100, int(level)) & 0xFF
		if level != self._led_level:
			self._led_level = level
			self.slot.send_feature(bytes((0x87, 0x03, 0x2D, level)))

	def set_gyro_enabled(self, enabled: bool) -> None:
		self._enable_gyros = enabled

	def get_gyro_enabled(self) -> bool:
		return self._enable_gyros

	def queue_pad_click(self, state) -> None:
		for button, side in ((SCButtons.LPAD, HapticPos.LEFT), (SCButtons.RPAD, HapticPos.RIGHT)):
			was, now = self._old_state.buttons & button, state.buttons & button
			if bool(was) != bool(now):
				amplitude = protocol.PAD_CLICK_PRESS if now else protocol.PAD_CLICK_RELEASE
				self.mapper.send_feedback(HapticData(side, amplitude=amplitude))

	def feedback(self, data: HapticData) -> None:
		position, amplitude = data.data[:2]
		if amplitude <= 0:
			return
		side = {HapticPos.LEFT: 0, HapticPos.RIGHT: 1, HapticPos.BOTH: 2}.get(position, 1)
		# Haptics must use interrupt OUT (hid_write), not a feature report.
		try:
			self.slot.write(bytes((0x82, side, 0x01, min(255, amplitude >> 7))))
		except (OSError, ValueError):
			# Feedback is generated inside mapper.input(). An output failure must
			# not reach poll() and masquerade as an input disconnect.
			log.exception("Failed to send SC2 haptics at %r", self.slot.path)

	def turnoff(self) -> None:
		self.slot.send_feature(b"\x9f\x04off!")
		self.slot._suppressed_at = time.monotonic()
		self.close()

	def close(self, *args) -> None:
		if self._closed:
			return
		self._closed = True
		if self.slot.controller is self:
			self.slot.controller = None
		self.slot.daemon.remove_controller(self)


class SC2HIDDevice:
	"""One wired interface or Puck slot; empty slots keep listening for input."""

	def __init__(self, driver: SC2Driver, info: dict) -> None:
		self.driver = driver
		self.daemon = driver.daemon
		self.info = info
		self.path = info["path"]
		self.controller: SC2Controller | None = None
		self._closed = False
		self._suppressed_at: float | None = None
		self._warned_0x45 = False
		self.device = hid.device()
		try:
			self.device.open_path(self.path)
			self.device.set_nonblocking(True)
		except Exception:
			self.device.close()
			raise

	def send_feature(self, data: bytes) -> None:
		# SET_REPORT feature 0x01, exactly 64 bytes including report ID.
		report = (b"\x01" + data)[:64].ljust(64, b"\x00")
		try:
			if self.device.send_feature_report(report) != len(report):
				raise OSError("Incomplete SC2 feature report")
		except (OSError, ValueError):
			# A powered-off Puck slot can stall while the receiver stays online.
			if self.controller:
				self.controller.close()
			raise

	def write(self, report: bytes) -> None:
		written = self.device.write(report)
		# Windows HIDAPI pads to the longest output report and returns that
		# padded byte count, which can exceed the command length.
		if written < len(report):
			raise OSError(f"Incomplete SC2 haptic report: wrote {written} of {len(report)} bytes")

	def _on_input(self, report: bytes) -> None:
		if self._suppressed_at is not None:
			now = time.monotonic()
			if now - self._suppressed_at < protocol.TURNOFF_QUIET_PERIOD:
				self._suppressed_at = now
				return
			self._suppressed_at = None
		state = protocol.parse_input(report)
		if state is None:
			if report and report[0] == 0x45 and not self._warned_0x45:
				self._warned_0x45 = True
				log.warning("SC2 at %r sent report 0x45 (NoQuat); only report 0x42 is supported", self.path)
			return
		if protocol._CALIB:
			protocol._log_imu_calib(state)
		try:
			if self.controller is None:
				controller = SC2Controller(self)
				controller.clear_mappings()
				controller.configure()
				self.controller = controller
				self.daemon.add_controller(controller)
				log.info("Connected SC2 %s at %r", controller.get_id(), self.path)
			controller = self.controller
			if state.seq % protocol.UNLIZARD_INTERVAL == 0:
				controller.clear_mappings()
		except (OSError, ValueError):
			log.debug("SC2 slot at %r stopped accepting commands; keeping interface open", self.path)
			return
		if controller.mapper:
			controller.queue_pad_click(state)
			controller.mapper.input(controller, controller._old_state, state)
		controller._old_state = state

	def poll(self) -> None:
		if self._closed:
			return
		try:
			for _ in range(MAX_REPORTS_PER_TICK):
				report = self.device.read(protocol.INPUT_BUFFER)
				if not report:
					break
				self._on_input(bytes(report))
		except (OSError, ValueError):
			log.exception("SC2 input failed at %r", self.path)
			self.close()

	def close(self, *args) -> None:
		if self._closed:
			return
		self._closed = True
		self.driver.devices.pop(self.path, None)
		try:
			self.device.close()
		finally:
			if self.controller:
				self.controller.close()


class SC2Driver:
	def __init__(self, daemon: SCCDaemon) -> None:
		self.daemon = daemon
		self.devices: dict[bytes | str, SC2HIDDevice] = {}
		self._next_scan = 0.0
		self._scan_result: Future | None = None

	@staticmethod
	def _enumerate() -> dict | None:
		found = {}
		try:
			for product in (protocol.PID_WIRED, protocol.PID_PUCK):
				for info in hid.enumerate(protocol.VENDOR_ID, product):
					interface = info.get("interface_number", -1)
					interfaces = range(2, 6) if product == protocol.PID_PUCK else (0,)
					if interface not in interfaces:
						continue
					# Each slot is a vendor-defined collection, not the lizard
					# keyboard/mouse collections exposed on some platforms.
					if info.get("usage_page") not in (None, 0, 0xFF00):
						continue
					if info.get("path") is not None:
						found[info["path"]] = info
		except Exception:
			log.exception("Failed to enumerate SC2 HID interfaces")
			return None
		return found

	def _apply_scan(self, found: dict) -> None:
		for path, info in found.items():
			if path not in self.devices:
				try:
					self.devices[path] = SC2HIDDevice(self, info)
				except (OSError, ValueError):
					log.exception("Failed to open SC2 HID interface at %r", path)
		for path in set(self.devices) - set(found):
			self.devices[path].close()

	def scan(self) -> None:
		self._next_scan = time.monotonic() + SCAN_INTERVAL
		if self._scan_result is None:
			found = self._enumerate()
			if found is not None:
				self._apply_scan(found)

	def mainloop(self) -> None:
		for device in tuple(self.devices.values()):
			device.poll()
		if self._scan_result is not None and self._scan_result.done():
			result, self._scan_result = self._scan_result, None
			found = result.result()
			if found is not None:
				self._apply_scan(found)
		if time.monotonic() >= self._next_scan and self._scan_result is None:
			self._next_scan = time.monotonic() + SCAN_INTERVAL
			result = self._scan_result = Future()

			def enumerate_devices() -> None:
				result.set_result(self._enumerate())

			Thread(target=enumerate_devices, name="sc2-hidapi-discovery", daemon=True).start()

	def close(self, *args) -> None:
		for device in tuple(self.devices.values()):
			device.close()


_driver: SC2Driver | None = None


def init(daemon: SCCDaemon, config: dict) -> bool:
	global _driver
	_driver = None
	if sys.platform not in ("linux", "win32", "darwin"):
		return False
	if sys.platform == "linux" and config.get("drivers", {}).get("sc2", True):
		log.error("Disable the sc2 Linux backend before enabling sc2_hidapi")
		return False
	if hid is None:
		log.error("Install sccontroller[hidapi] to enable the SC2 HIDAPI driver")
		return False
	_driver = SC2Driver(daemon)
	daemon.add_mainloop(_driver.mainloop)
	daemon.add_on_exit(_driver.close)
	daemon.add_on_rescan(_driver.scan)
	return True


def start(daemon: SCCDaemon) -> None:
	if _driver is not None:
		_driver.scan()
