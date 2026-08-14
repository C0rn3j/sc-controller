"""SC Controller - Controller Registration data

Dummy container classes
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN
from scc.gui.creg.constants import AXIS_TO_BUTTON

if TYPE_CHECKING:
	from scc.constants import SCButtons


log = logging.getLogger("CReg.data")


class AxisData:
	"""(Almost) dumb container.

	Stores position, center and limits for single axis.
	"""

	def __init__(self, name: str, xy: int, min: int = STICK_PAD_MAX, max: int = STICK_PAD_MIN) -> None:
		self.name: str = name
		self.area: str = name.split("_")[0].upper()
		if self.area.endswith("TRIG"):
			self.area = self.area[0:-3]
		self.xy: int = xy
		self.pos : int = 0
		self.center: int = 0
		self.min: int = min
		self.max: int = max
		self.invert: bool = False
		self.cursor = None

	def reset(self) -> None:
		"""Reset min and max value so axis can (has to be) recalibrated again"""
		self.min = STICK_PAD_MAX
		self.max = STICK_PAD_MIN

	def __repr__(self) -> str:
		return f"<Axis data '{self.name}'>"

	def set_position(self, value):
		"""Return (changed, x), value determining if axis limits were changed and current position position.

		translated to range of (STICK_PAD_MIN, STICK_PAD_MAX)
		"""
		changed = False
		if value < self.min:
			self.min = value
			changed = True
		if value > self.max:
			self.max = value
			changed = True
		self.pos = value
		try:
			r = (STICK_PAD_MAX - STICK_PAD_MIN) / (self.max - self.min)
			v = (self.pos - self.min) * r
			if self.invert:
				return changed, STICK_PAD_MAX - v
			return changed, v + STICK_PAD_MIN
		except ZeroDivisionError:
			return changed, 0


class DPadEmuData:
	"""Dumb container that stores dpad emulation data.

	DPAd emulation is used, for example, on PS3 controller, where dpad does not
	inputs as 2 axes, but as 4 buttons.

	This class stores mapping of one button to one half of axis.
	"""

	def __init__(self, axis_data: AxisData, positive: bool) -> None:
		self.axis_data: AxisData = axis_data
		self.positive: bool = positive
		self.button: SCButtons | None = AXIS_TO_BUTTON.get(axis_data.name)
