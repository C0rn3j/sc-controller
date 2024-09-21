"""SC Controller - Fake controller driver.

This driver does nothing by default, unless SCC_FAKES environment variable is
set. If it is, creates as many fake controller devices as integer stored in
SCC_FAKES says.

Created controllers are completely useless. For debuging purposes only.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from scc.controller import Controller

if TYPE_CHECKING:
	from scc.sccdaemon import SCCDaemon

ENV_VAR = "SCC_FAKES"

if ENV_VAR in os.environ:
	log = logging.getLogger("FakeDrv")

	def init(daemon: SCCDaemon, config: dict) -> bool:
		return True

	def start(daemon: SCCDaemon) -> None:
		num = int(os.environ[ENV_VAR])
		log.debug("Creating %s fake controllers", num)
		for x in range(num):
			daemon.add_controller(FakeController(x))

class FakeController(Controller):
	def __init__(self, number: int) -> None:
		Controller.__init__(self)
		self._number = number
		self._id = f"fake{self._number}"

	def get_type(self) -> str:
		return "fake"

	def set_led_level(self, level:int) -> None:
		log.debug("FakeController %s led level set to %s", self.get_id(), level)

	def __repr__(self) -> str:
		return f"<FakeController {self.get_id()}>"
