"""SC Controller - Steam Controller Driver.

Called and used when single Steam Controller is connected directly by USB cable.

Shares a lot of classes with sc_dongle.py
"""
from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING

from usb1 import USBError

from scc.drivers.usb import SCUSBDevice, register_hotplug_device

from .sc_dongle import TUP_FORMAT, ControllerInput, SCController, SCStatus

if TYPE_CHECKING:
	from usb1 import USBDevice, USBDeviceHandle

	from scc.sccdaemon import SCCDaemon

VENDOR_ID = 0x28DE
PRODUCT_ID = 0x1102
ENDPOINT = 3
CONTROLIDX = 2
TIMER_INTERVAL = 0.01

log = logging.getLogger("SCCable")


def init(daemon: SCCDaemon, config: dict) -> bool:
	"""Register hotplug callback for controller dongle."""

	def cb(device: USBDevice, handle: USBDeviceHandle) -> SCByCable:
		return SCByCable(device, handle, daemon)

	register_hotplug_device(cb, VENDOR_ID, PRODUCT_ID)
	return True


class SCByCable(SCUSBDevice, SCController):
	FORMAT1 = b">BBBBB13sB2s"

	def __init__(self, device: USBDevice, handle: USBDeviceHandle, daemon: SCCDaemon) -> None:
		self._id: str
		self.daemon: SCCDaemon = daemon
		SCUSBDevice.__init__(self, device, handle)
		SCController.__init__(self, self, CONTROLIDX, ENDPOINT)
		self._ready: bool = False
		self._last_tup = None
		daemon.add_mainloop(self._timer)

		self.claim_by(klass=3, subclass=0, protocol=0)
		self.read_serial()

	def generate_serial(self) -> None:
		self._serial = f"{self.device.getBusNumber()}:{self.device.getPortNumber()}"

	def disconnected(self) -> None:
		# Overrided to skip returning serial# to pool.
		pass

	def __repr__(self) -> str:
		return f"<SCByCable {self.get_id()}>"

	def on_serial_got(self) -> None:
		log.debug("Got wired SC with serial %s", self._serial)
		self._id = f"sc{self._serial}"
		self.set_input_interrupt(ENDPOINT, 64, self._wait_input)

	def _wait_input(self, endpoint, data) -> None:
		tup = ControllerInput._make(struct.unpack(TUP_FORMAT, data))
		if not self._ready:
			self.daemon.add_controller(self)
			self.configure()
			self._ready = True
		if tup.status == SCStatus.INPUT:
			self._last_tup = tup

	def _timer(self) -> None:
		m = self.get_mapper()
		if m:
			if self._last_tup:
				self.input(self._last_tup)
				self._last_tup = None
			else:
				m.generate_events()
				m.generate_feedback()
			try:
				self.flush()
			except USBError as e:
				log.exception(e)
				log.error("Error while communicating with device, baling out...")
				self.force_restart()

	def close(self) -> None:
		if self._ready:
			self.daemon.remove_controller(self)
			self._ready = False
		self.daemon.remove_mainloop(self._timer)
		SCUSBDevice.close(self)

	def turnoff(self) -> None:
		log.warning("Ignoring request to turn off wired controller.")
