"""SC-Controller - Slave Mapper

Mapper that is hooked to scc-daemon instance through socket instead of
using libusb directly. Relies to Observe or Lock message being sent by client.

Used by on-screen keyboard.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scc.constants import SCButtons, SCPads, SCSticks, SCTriggers
from scc.mapper import Mapper

if TYPE_CHECKING:
	from typing import Never

log = logging.getLogger("SlaveMapper")


class SlaveMapper(Mapper):
	def __init__(self, profile, scheduler, keyboard: bytes = b"SCController Keyboard", mouse: bytes | None = None) -> None:
		Mapper.__init__(self, profile, scheduler, keyboard, mouse, None)
		self._feedback_cb = None

	def set_controller(self, c) -> Never:
		"""Sets controller device, used by some (one so far) actions"""
		raise TypeError("SlaveMapper doesn't connect to controller device")

	def get_controller(self) -> Never:
		"""Returns assigned controller device or None if no controller is set"""
		raise TypeError("SlaveMapper doesn't connect to controller device")

	def set_feedback_callback(self, cb) -> None:
		"""Sets callback called to process haptic feedback effects.

		If callback is set, it's called as callback(hapticdata) every time
		when feedback would happen normally.

		Callback is used here instead of signal so this module doesn't
		depends on GLib
		"""
		self._feedback_cb = cb

	def send_feedback(self, hapticdata) -> None:
		"""Simply calls self._feedback_cb, if set. See docstring above."""
		if self._feedback_cb:
			self._feedback_cb(hapticdata)

	# TODO(Martin): Fix up the LSTICKPRESS/LPADTOUCH/RPADTOUCH literals
	def handle_event(self, daemon, what: SCSticks | SCPads | str, data) -> None:
		"""Handles event sent by scc-daemon.

		Without calling this, SlaveMapper basically does nothing.
		"""
		self.old_buttons = self.buttons
		if what == SCSticks.LSTICK:
			self.profile.lstick.whole(self, data[0], data[1], what)
		elif what == SCSticks.RSTICK:
			self.profile.rstick.whole(self, data[0], data[1], what)
		elif what == SCButtons.LT.name:
			self.profile.triggers[SCTriggers.LT].trigger(self, *data)
		elif what == SCButtons.RT.name:
			self.profile.triggers[SCTriggers.RT].trigger(self, *data)
		elif what in SCPads:
			self.profile.pads[what].whole(self, data[0], data[1], what)
		elif hasattr(SCButtons, what) or what in ("LPADPRESS", "RPADPRESS"):
			x = {
				"LPADPRESS": SCButtons.LPAD,
				"RPADPRESS": SCButtons.RPAD,
			}.get(what, getattr(SCButtons, what, None))
			if x is None:
				raise ValueError(f"Unknown button {what}")
			if data[0]:
				# Pressed
				self.buttons = self.buttons | x
				self.profile.buttons[x].button_press(self)
			else:
				self.buttons = self.buttons & ~x
				self.profile.buttons[x].button_release(self)
				if what == "LPADTOUCH":
					self.profile.pads[SCPads.LPAD].whole(self, 0, 0, SCPads.LPAD)
				elif what == "RPADTOUCH":
					self.profile.pads[SCPads.RPAD].whole(self, 0, 0, SCPads.RPAD)
		else:
			log.error(">>> %s %s", what, data)
		self.generate_events()
