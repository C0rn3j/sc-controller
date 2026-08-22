"""SC Controller - On Screen Keyboard Actions.

Special Actions that are used to bind functions like closing keyboard or moving
cursors around.

Actions defined here are *not* automatically registered, but OSD Keyboard
and its binding editor enables them to use with 'OSK.something'
syntax.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scc.actions import Action, SpecialAction
from scc.constants import TRIGGER_HALF, HapticPos, SCLeftRight, SCSidesOSD

if TYPE_CHECKING:
	from scc.mapper import Mapper

log = logging.getLogger("OSDKeyActs")
_ = lambda x: x


class OSKAction(Action, SpecialAction):
	def __init__(self, *a) -> None:
		Action.__init__(self, *a)
		self.speed: float = 1.0

	def set_speed(self, x: float, y, z) -> bool:
		self.speed = x
		return True

	def trigger(self, mapper: Mapper, p, old_p) -> None:
		if p * self.speed >= TRIGGER_HALF and old_p * self.speed < TRIGGER_HALF:
			self.button_press(mapper)
		elif p * self.speed < TRIGGER_HALF and old_p * self.speed >= TRIGGER_HALF:
			self.button_release(mapper)


class CloseOSKAction(OSKAction):
	SA: str = "close"
	COMMAND: str = SA

	def describe(self, context):
		if context == Action.AC_OSK:
			return _("Hide")
		return _("Hide Keyboard")

	def to_string(self, multiline: bool = False, pad: int = 0) -> str:
		return (" " * pad) + f"OSK.{self.COMMAND}()"

	def button_press(self, mapper: Mapper) -> None:
		self.execute(mapper)

	def button_release(self, mapper: Mapper) -> None:
		pass


class OSKCursorAction(Action, SpecialAction):
	SA: str = "cursor"
	COMMAND: str = SA

	def __init__(self, side: HapticPos | SCSidesOSD) -> None:
		Action.__init__(self, side)
		if hasattr(side, "name"):
			side = side.name
		self.speed: tuple[float, float] = (1.0, 1.0)
		self.side: SCSidesOSD = side

	def set_speed(self, x, y, z) -> bool:
		self.speed = (x, y)
		return True

	def whole(self, mapper: Mapper, x, y, what) -> None:
		self.execute(mapper, x, y)

	def describe(self, context):
		if self.side == SCLeftRight.LEFT:
			return _("Move LEFT Cursor")
		if self.side == SCLeftRight.RIGHT:
			return _("Move RIGHT Cursor")
		return _("Move Cursor")

	def to_string(self, multiline: bool = False, pad: int = 0) -> str:
		return (" " * pad) + f"OSK.{self.COMMAND}({self.side})"


class MoveOSKAction(OSKAction):
	SA: str = "move"
	COMMAND: str = SA

	def whole(self, mapper, x, y, what) -> None:
		self.execute(mapper, x, y)

	def describe(self, context):
		return _("Move Keyboard")

	def to_string(self, multiline: bool = False, pad: int = 0) -> str:
		return (" " * pad) + f"OSK.{self.COMMAND}()"


class OSKPressAction(OSKAction):
	SA: str = "press"
	COMMAND: str = SA

	def __init__(self, side: HapticPos | SCSidesOSD) -> None:
		OSKAction.__init__(self, side)
		if hasattr(side, "name"):
			side = side.name
		self.side: SCSidesOSD = side

	def describe(self, context):
		if context == Action.AC_OSK:
			return _("Press Key")
		if self.side == SCLeftRight.LEFT:
			return _("Press Key Under LEFT Cursor")
		return _("Press Key Under RIGHT Cursor")

	def button_press(self, mapper: Mapper) -> None:
		self.execute(mapper, True)

	def button_release(self, mapper: Mapper) -> None:
		self.execute(mapper, False)

	def to_string(self, multiline=False, pad=0) -> str:
		return (" " * pad) + f"OSK.{self.COMMAND}({self.side})"
