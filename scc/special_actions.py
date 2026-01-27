#!/usr/bin/env python3
"""
SC Controller - Special Actions

Special Action is "special" since it cannot be handled by mapper alone.
Instead, on_sa_<actionname> method on handler instance set by
mapper.set_special_actions_handler() is called to do whatever action is supposed
to do. If handler is not set, or doesn't have reqiuired method defined,
action only prints warning to console.
"""

from __future__ import annotations

from typing import override, TYPE_CHECKING
if TYPE_CHECKING:
	from collections.abc import Callable


from scc.constants import SCButtons
from scc.constants import LEFT, RIGHT, STICK, SAME
from scc.constants import STICK_PAD_MAX, DEFAULT
from scc.actions import Action, SpecialAction
from scc.actions import HapticEnabledAction, OSDEnabledAction
from scc.tools import strip_gesture, nameof, clamp
from scc.modifiers import Modifier
from difflib import get_close_matches
from math import sqrt

import sys, logging
log = logging.getLogger("SActions")
_: Callable[[str], str] = lambda x : x


class ChangeProfileAction(Action, SpecialAction):
	SA: str = "profile"
	COMMAND: str = "profile"

	def __init__(self, profile: str):
		Action.__init__(self, profile)
		self.profile: str = profile

	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		if context == Action.AC_OSD:
			return _("Profile: %s") % (self.profile,)
		if context == Action.AC_SWITCHER:
			return _("Switch to %s") % (self.profile,)
		return _("Profile Change")

	@override
	def get_compatible_modifiers(self) -> int:
		return Action.MOD_OSD

	@override
	def to_string(self, multiline: bool=False, pad: int=0) -> str:
		return (" " * pad) + "%s('%s')" % (self.COMMAND, self.profile)

	@override
	def button_release(self, mapper):
		# Execute only when button is released (executing this when button
		# is pressed would send following button_release event to another
		# action from loaded profile)
		self.execute(mapper)


	@override
	def whole(self, mapper, *a):
		self.execute(mapper)


class ShellCommandAction(Action, SpecialAction):
	SA: str = "shell"
	COMMAND: str = "shell"

	def __init__(self, command: str):
		#if type(command) == str:
		#	command = command.decode("unicode_escape")
		#assert type(command) == unicode
		Action.__init__(self, command)
		self.command: str = command


	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		return _("Execute Command")

	@override
	def get_compatible_modifiers(self) -> int:
		return Action.MOD_OSD

	@override
	def to_string(self, multiline: bool=False, pad: int=0) -> str:
		return (" " * pad) + "%s('%s')" % (self.COMMAND, self.command[0])

	@override
	def button_press(self, mapper):
		# Executes only when button is pressed
		return self.execute(mapper)


class TurnOffAction(Action, SpecialAction):
	SA: str = "turnoff"
	COMMAND: str = "turnoff"

	def __init__(self):
		Action.__init__(self)

	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		if context == Action.AC_OSD:
			return _("Turning controller OFF")
		return _("Turn Off the Controller")


	@override
	def to_string(self, multiline:bool=False, pad:int=0) -> str:
		return (" " * pad) + "%s()" % (self.COMMAND,)


	@override
	def get_compatible_modifiers(self) -> int:
		return Action.MOD_OSD


	@override
	def button_release(self, mapper):
		# Execute only when button is released (executing this when button
		# is pressed would hold stuck any other action bound to same button,
		# as button_release is not sent after controller turns off)
		self.execute(mapper)


	@override
	def whole(self, mapper, *a):
		self.execute(mapper)


class RestartDaemonAction(Action, SpecialAction):
	SA: str = "restart"
	COMMAND: str = "restart"
	ALIASES: tuple[str] = ("exit", )

	def __init__(self):
		Action.__init__(self)


	@override
	def describe(self, context) -> str:
		if self.name: return self.name
		return _("Restart SCC-Daemon")


	@override
	def to_string(self, multiline: bool=False, pad: int=0) -> str:
		return (" " * pad) + "%s()" % (self.COMMAND,)


	@override
	def button_release(self, mapper):
		# Execute only when button is released (for same reason as
		# TurnOffAction does)
		self.execute(mapper)


class LedAction(Action, SpecialAction):
	SA: str = "led"
	COMMAND: str = "led"

	def __init__(self, brightness: float):
		Action.__init__(self, brightness)
		self.brightness: int = int(clamp(0, int(brightness), 100))


	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		return _("Set LED brightness")


	@override
	def get_compatible_modifiers(self) -> int:
		return Action.MOD_OSD


	@override
	def button_press(self, mapper):
		# Execute only when button is pressed
		self.execute(mapper)


class OSDAction(Action, SpecialAction):
	"""
	Displays text in OSD, or, if used as modifier, displays action description
	and executes that action.
	"""
	SA: str = "osd"
	COMMAND: str = "osd"
	DEFAULT_TIMEOUT: int = 5
	DEFAULT_SIZE: int = 3
	PROFILE_KEY_PRIORITY: int = -5	# After XYAction, but before everything else

	def __init__(self, *parameters):
		Action.__init__(self, *parameters)
		self.action: Action | None = None
		self.timeout: float = self.DEFAULT_TIMEOUT
		self.size: float = self.DEFAULT_SIZE

		# this is too convoluted for the thing that its doing, why not just have default parameters?
		if len(parameters) > 1 and type(parameters[0]) in (int, float):
			# timeout parameter included
			self.timeout = float(parameters[0])
			parameters = parameters[1:]
		if len(parameters) > 1 and type(parameters[0]) in (int, float):
			# size parameter included
			self.size = int(parameters[0])
			parameters = parameters[1:]
		if isinstance(parameters[0], Action):
			self.action = parameters[0]
			self.text = self.action.describe(Action.AC_OSD)
		else:
			self.text = str(parameters[0])
		if self.action and isinstance(self.action, OSDEnabledAction):
			self.action.enable_osd(self.timeout)

	@override
	def get_compatible_modifiers(self) -> int:
		if self.action:
			return self.action.get_compatible_modifiers()
		return 0

	@staticmethod
	def decode(data: dict[str, Any], a, *b) -> OSDAction:
		a = OSDAction(a)
		if data["osd"] is not True:
			a.timeout = float(data["osd"])
		return a

	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		if self.action:
			return _("%s (with OSD)") % (self.action.describe(context),)
		elif context == Action.AC_OSD:
			return _("Display '%s'" % self.text)
		return _("OSD Message")


	@override
	def to_string(self, multiline: bool=False, pad: int=0) -> str:
		parameters: list[str] = []
		if self.timeout != self.DEFAULT_TIMEOUT or self.size != self.DEFAULT_SIZE:
			parameters.append(str(self.timeout))
		if self.size != self.DEFAULT_SIZE:
			parameters.append(str(self.size))
		if self.action:
			parameters.append(self.action.to_string(multiline=multiline, pad=pad))
		else:
			parameters.append("'%s'" % (str(self.text),))
		return (" " * pad) + "%s(%s)" % (self.COMMAND, ",".join(parameters))


	@override
	def strip(self) -> Action | OSDAction:
		if self.action:
			return self.action.strip()
		return self


	@override
	def compress(self):
		if self.action:
			if isinstance(self.action, OSDEnabledAction):
				return self.action.compress()
			self.action = self.action.compress()
		return self


	@override
	def button_press(self, mapper):
		self.execute(mapper)
		if self.action:
			return self.action.button_press(mapper)


	@override
	def button_release(self, mapper):
		if self.action:
			return self.action.button_release(mapper)


	@override
	def trigger(self, mapper, position, old_position):
		if self.action:
			return self.action.trigger(mapper, position, old_position)

	@override
	def axis(self, mapper, position, what):
		if self.action:
			return self.action.axis(mapper, position, what)

	@override
	def pad(self, mapper, position, what):
		if self.action:
			return self.action.pad(mapper, position, what)

	@override
	def whole(self, mapper, x, y, what):
		if self.action:
			return self.action.whole(mapper, x, y, what)


class ClearOSDAction(Action, SpecialAction):
	"""
	Clears all windows from OSD layer. Cancels all menus, clears all messages,
	etc, etc.
	"""
	SA: str = "clearosd"
	COMMAND: str = "clearosd"

	@override
	def describe(self, context: int) -> str:
		return _("Hide all OSD Menus and Messages")


	@override
	def button_press(self, mapper):
		self.execute(mapper)


class MenuAction(Action, SpecialAction, HapticEnabledAction):
	"""
	Displays menu defined in profile or globally.
	"""
	SA: str = "menu"
	COMMAND: str = "menu"
	MENU_TYPE: str = "menu"
	MIN_STICK_DISTANCE: float = STICK_PAD_MAX / 3
	DEFAULT_POSITION: tuple[int,int] = 10, -10

	def __init__(self, menu_id: str, control_with: str | int=DEFAULT, confirm_with: str=DEFAULT,
					cancel_with: str=DEFAULT, show_with_release: bool=False, size: int = 0):
		if control_with == SAME:
			# Little touch of backwards compatibility
			control_with, confirm_with = DEFAULT, SAME
		if type(control_with) == int:
			# Allow short form in case when menu is assigned to pad
			# eg.: menu("some-id", 3) sets size to 3
			# why not move size to be the second argument then?
			control_with, size = DEFAULT, control_with
		Action.__init__(self, menu_id, control_with, confirm_with, cancel_with, show_with_release, size)
		HapticEnabledAction.__init__(self)
		self.menu_id: str = menu_id
		assert(type(control_with) == str)
		self.control_with: str = control_with
		self.confirm_with: str = confirm_with
		self.cancel_with: str = cancel_with
		self.size: int = size
		self.x: float
		self.y: float
		self.x, self.y = MenuAction.DEFAULT_POSITION
		self.show_with_release: bool = bool(show_with_release)
		self._stick_distance: float = 0

	@override
	def describe(self, context) -> str:
		if self.name: return self.name
		return _("Menu")


	@override
	def get_compatible_modifiers(self) -> int:
		return Action.MOD_FEEDBACK


	@override
	def to_string(self, multiline: bool=False, pad: int=0) -> str:
		if self.control_with == DEFAULT:
			dflt = (DEFAULT, DEFAULT, False)
			vals = (self.confirm_with, self.cancel_with, self.show_with_release)
			if dflt == vals:
				# Special case when menu is assigned to pad
				if self.size == 0:
					return "%s%s('%s')" % (" " * pad, self.COMMAND, self.menu_id)
				else:
					return "%s%s('%s', %s)" % (" " * pad, self.COMMAND, self.menu_id, self.size)

		return "%s%s(%s)" % (" " * pad, self.COMMAND, ",".join(Action.encode_parameters(self.strip_defaults())))

	@override
	def get_previewable(self) -> bool:
		return True


	@override
	def button_press(self, mapper):
		if not self.show_with_release:
			confirm_with = self.confirm_with
			cancel_with = self.cancel_with
			args = [mapper]
			if confirm_with == SAME:
				confirm_with = mapper.get_pressed_button() or DEFAULT
			elif confirm_with == DEFAULT:
				confirm_with = DEFAULT
			if cancel_with == DEFAULT:
				cancel_with = DEFAULT
			if nameof(self.control_with) in (LEFT, RIGHT):
				args += ["--use-cursor"]
			args += [
				"--control-with",
				nameof(self.control_with),
				"-x",
				str(self.x),
				"-y",
				str(self.y),
				"--size",
				str(self.size),
				"--confirm-with",
				nameof(confirm_with),
				"--cancel-with",
				nameof(cancel_with),
			]
			self.execute(*args)


	@override
	def button_release(self, mapper):
		if self.show_with_release:
			self.execute(mapper, "-x", str(self.x), "-y", str(self.y))

	@override
	def whole(self, mapper, x: float, y: float, what: str, *params):
		if x == 0 and y == 0:
			# Sent when pad is released - don't display menu then
			return
		if self.haptic:
			params = list(params) + ["--feedback-amplitude", str(self.haptic.get_amplitude())]
		if what in (LEFT, RIGHT):
			confirm_with = self.confirm_with
			cancel_with = self.cancel_with
			if what == LEFT:
				if confirm_with == DEFAULT:
					confirm_with = SCButtons.LPAD
				if cancel_with == DEFAULT:
					cancel_with = SCButtons.LPADTOUCH
			elif what == RIGHT:
				if confirm_with == DEFAULT:
					confirm_with = SCButtons.RPAD
				if cancel_with == DEFAULT:
					cancel_with = SCButtons.RPADTOUCH
			else:
				# Stick
				if confirm_with == DEFAULT:
					confirm_with = SCButtons.STICKPRESS
				if cancel_with == DEFAULT:
					cancel_with = SCButtons.B
			if not mapper.was_pressed(cancel_with):
				self.execute(
					mapper,
					"--control-with",
					what,
					"-x",
					str(self.x),
					"-y",
					str(self.y),
					"--use-cursor",
					"--size",
					str(self.size),
					"--confirm-with",
					nameof(confirm_with),
					"--cancel-with",
					nameof(cancel_with),
					*params,
				)
		if what == STICK:
			# Special case, menu is displayed only if is moved enought
			distance = sqrt(x * x + y * y)
			if self._stick_distance < MenuAction.MIN_STICK_DISTANCE and distance > MenuAction.MIN_STICK_DISTANCE:
				self.execute(
					mapper,
					"--control-with",
					STICK,
					"-x",
					str(self.x),
					"-y",
					str(self.y),
					"--use-cursor",
					"--size",
					str(self.size),
					"--confirm-with",
					"STICKPRESS",
					"--cancel-with",
					STICK,
					*params,
				)
			self._stick_distance = distance


class HorizontalMenuAction(MenuAction):
	"""
	Same as menu, but packed as row
	"""
	COMMAND: str = "hmenu"
	MENU_TYPE: str = "hmenu"


class GridMenuAction(MenuAction):
	"""
	Same as menu, but displayed in grid
	"""
	COMMAND: str = "gridmenu"
	MENU_TYPE: str = "gridmenu"


class QuickMenuAction(MenuAction):
	"""
	Quickmenu. Max.6 items, controller by buttons
	"""
	COMMAND: str = "quickmenu"
	MENU_TYPE: str = "quickmenu"


	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		return _("QuickMenu")


	@override
	def button_press(self, mapper):
		# QuickMenu is always shown with release
		pass


	@override
	def button_release(self, mapper):
		self.execute(mapper, "-x", str(self.x), "-y", str(self.y))


class RadialMenuAction(MenuAction):
	"""
	Same as grid menu, which is same as menu but displayed in grid,
	but displayed as circle.
	"""
	COMMAND: str = "radialmenu"
	MENU_TYPE: str = "radialmenu"

	def __init__(
		self,
		menu_id: str,
		control_with: str | int = DEFAULT,
		confirm_with: str = DEFAULT,
		cancel_with: str = DEFAULT,
		show_with_release: bool = False,
		size: int = 0,
	):
		MenuAction.__init__(
			self,
			menu_id,
			control_with,
			confirm_with,
			cancel_with,
			show_with_release,
			size,
		)
		self.rotation: float = 0

	@override
	def whole(self, mapper, x: int | float, y: int | float, what: str, *_params):
		if self.rotation:
			MenuAction.whole(self, mapper, x, y, what, "--rotation", self.rotation)
		else:
			MenuAction.whole(self, mapper, x, y, what)

	def set_rotation(self, angle: float):
		self.rotation = angle


	@override
	def get_compatible_modifiers(self):
		return MenuAction.get_compatible_modifiers(self) or Action.MOD_ROTATE


class DialogAction(Action, SpecialAction):
	"""
	Dialog is actually kind of menu, but options for it are different.
	"""
	SA: str = "dialog"
	COMMAND: str = "dialog"
	DEFAULT_POSITION: tuple[int, int] = 10, -10

	def __init__(self, *params):
		Action.__init__(self, params)

		self.options = []
		self.confirm_with: str = DEFAULT
		self.cancel_with: str  = DEFAULT
		self.text: str = _("Dialog")
		self.x: int
		self.y: int
		self.x, self.y = MenuAction.DEFAULT_POSITION
		#TODO: move from *params to actual parameters
		# First and 2nd parameter may be confirm and cancel button
		if len(params) > 0 and params[0] in SCButtons.__members__.values():
			self.confirm_with, params = params[0], params[1:]
			if len(params) > 0 and params[0] in SCButtons.__members__.values():
				self.cancel_with, params = params[0], params[1:]
		# 1st always present argument is title
		if len(params) > 0:
			self.text, params = params[0], params[1:]
		# ... everything else are actions
		self.options = params


	@override
	def describe(self, context) -> str:
		if self.name: return self.name
		return _("Dialog")


	@override
	def to_string(self, multiline: bool=False, pad: int=0) -> str:
		rv = "%s%s(" % (" " * pad, self.COMMAND)
		if self.confirm_with != DEFAULT:
			rv += "%s, " % (nameof(self.confirm_with),)
			if self.cancel_with != DEFAULT:
				rv += "%s, " % (nameof(self.cancel_with),)
		rv += "'%s', " % (self.text,)
		if multiline:
			rv += "\n%s" % (" " * (pad + 2))
		for option in self.options:
			rv += "%s, " % (option.to_string(False),)
			if multiline:
				rv += "\n%s" % (" " * (pad + 2))

		rv = rv.strip("\n ,")
		if multiline:
			rv += "\n)"
		else:
			rv += ")"
		return rv


	@override
	def get_previewable(self) -> bool:
		return False


	@override
	def button_release(self, mapper):
		confirm_with = self.confirm_with
		cancel_with = self.cancel_with
		args = [
			mapper,
			"-x",
			str(self.x),
			"-y",
			str(self.y),
			"--confirm-with",
			nameof(confirm_with),
			"--cancel-with",
			nameof(cancel_with),
			"--text",
			self.text,
		]
		for x in self.options:
			args.append(x)
		self.execute(*args)


class KeyboardAction(Action, SpecialAction):
	"""
	Shows OSD keyboard.
	"""
	SA: str = "keyboard"
	COMMAND: str = "keyboard"

	@override
	def __init__(self):
		Action.__init__(self)


	@override
	def get_compatible_modifiers(self) -> int:
		return Action.MOD_POSITION


	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		if context == Action.AC_OSD:
			return _("Display Keyboard")
		return _("OSD Keyboard")


	def to_string(self, multiline=False, pad=0) -> str:
		return (" " * pad) + "%s()" % (self.COMMAND,)

	def button_press(self, mapper):
		self.execute(mapper)


class PositionModifier(Modifier):
	"""
	Sets position for OSD menu.
	"""
	COMMAND: str = "position"

	@override
	def _mod_init(self, x: int, y: int):
		self.position: tuple[int, int] = (x, y)


	@override
	def compress(self):
		if isinstance(self.action, MenuAction):
			self.action.x, self.action.y = self.position
		return self.action

	@staticmethod
	def decode(data: dict[str, Any], a, *b) -> PositionModifier:
		x, y = data[PositionModifier.COMMAND]
		return PositionModifier(x, y, a)

	@override
	def describe(self, context: int) -> str:
		return self.action.describe(context)


class GesturesAction(Action, OSDEnabledAction, SpecialAction):
	"""
	Stars gesture detection on pad. Recognition is handled by whatever
	is special_actions_handler and results are then sent back to this action
	as parameter of gesture() method.
	"""
	SA: str = "gestures"
	COMMAND: str = "gestures"
	PROFILE_KEYS: tuple[str] = ("gestures",)
	PROFILE_KEY_PRIORITY: int = 2
	DEFAULT_PRECISION: float = 1.0

	def __init__(self, *params):
		OSDEnabledAction.__init__(self)
		Action.__init__(self, *params)
		self.gestures: dict[str, Any] = {}
		self.precision: float = self.DEFAULT_PRECISION
		gesture_str: str | None = None

		# TODO: migrate from this
		if len(params) > 0 and type(params[0]) in (int, float):
			self.precision = clamp(0.0, float(params[0]), 1.0)
			params = params[1:]

		for i in params:
			if gesture_str is None and type(i) == str:
				gesture_str = i
			elif gesture_str is not None and isinstance(i, Action):
				self.gestures[gesture_str] = i
				gesture_str = None
			else:
				raise ValueError("Invalid parameter for '%s': unexpected %s" % (self.COMMAND, i))

	@override
	def get_compatible_modifiers(self) -> int:
		return Action.MOD_OSD


	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		return _("Gestures")


	#TODO: un-fever-dream this
	@override
	def to_string(self, multiline: bool=False, pad: int=0) -> str:
		if multiline:
			rv = [(" " * pad) + self.COMMAND + "("]
			if self.precision != self.DEFAULT_PRECISION:
				rv[0] += "%s," % (self.precision)
			for gesture_str in self.gestures:
				a_str: list[str] = self.gestures[gesture_str].to_string(True).split("\n")
				a_str[0] = (" " * pad) + "  '" + (gesture_str + "',").ljust(11) + a_str[0]	# Key has to be one of SCButtons
				for i in range(1, len(a_str)):
					a_str[i] = (" " * pad) + "  " + a_str[i]
				a_str[-1] = a_str[-1] + ","
				rv += a_str
			if rv[-1][-1] == ",":
				rv[-1] = rv[-1][0:-1]
			rv += [(" " * pad) + ")"]
			return "\n".join(rv)
		else:
			rv = []
			if self.precision != self.DEFAULT_PRECISION:
				rv.append(str(self.precision))
			for gesture_str in self.gestures:
				rv += [ "'%s'" % (gesture_str,), self.gestures[gesture_str].to_string(False) ]
			return self.COMMAND + "(" + ", ".join(rv) + ")"


	@override
	def compress(self):
		for gstr in self.gestures:
			a = self.gestures[gstr].compress()
			if "i" in gstr:
				del self.gestures[gstr]
				gstr = strip_gesture(gstr)
			self.gestures[gstr] = a
		return self

	@staticmethod
	def decode(data, a, parser, *b) -> OSDAction | GesturesAction:
		ga = GesturesAction()
		ga.gestures = {
			gstr: parser.from_json_data(data[GesturesAction.PROFILE_KEYS[0]][gstr])
			for gstr in data[GesturesAction.PROFILE_KEYS[0]]
		}
		if "name" in data:
			ga.name = data["name"]
		if "osd" in data:
			ga = OSDAction(ga)
		return ga

	def _find_exact_gesture(self, gesture_string: str):
		return self.gestures.get(gesture_string)

	def _find_ignore_stroke_count_gesture(self, gesture_string: str):
		stripped_gesture_string = strip_gesture(gesture_string)
		return self.gestures.get(stripped_gesture_string)

	def _find_best_match_gesture(self, gesture_string: str):
		NUM_MATCHES_TO_RETURN = 1

		similar_gestures = get_close_matches(
			gesture_string, self.gestures.keys(), NUM_MATCHES_TO_RETURN, self.precision
		)
		best_gesture = next(iter(similar_gestures), None)

		if best_gesture is not None:
			return self.gestures[best_gesture]
		else:
			return None

	def find_gesture_action(self, gesture_string: str):
		action = None
		action = action or self._find_exact_gesture(gesture_string)
		action = action or self._find_ignore_stroke_count_gesture(gesture_string)
		action = action or self._find_best_match_gesture(gesture_string)
		return action

	def gesture(self, mapper, gesture_string: str):
		action = self.find_gesture_action(gesture_string)
		if action:
			action.button_press(mapper)
			mapper.schedule(0, action.button_release)

	@override
	def whole(self, mapper, x, y, what):
		if (x, y) != (0, 0):
			# (0, 0) singlanizes released touchpad
			self.execute(mapper, x, y, what)


class CemuHookAction(Action, SpecialAction):
	SA: str = "cemuhook"
	COMMAND: str = "cemuhook"
	MAGIC_GYRO: float = (2000.0 / 32768.0)
	ACC_RES_PER_G: float = 16384.0

	@override
	def gyro(self, mapper, *pyr):
		sa_data: tuple[float, float, float, float, float, float] = (
			-mapper.state.accel_x / CemuHookAction.ACC_RES_PER_G, # AccelX
			-mapper.state.accel_z / CemuHookAction.ACC_RES_PER_G, # AccelZ
			mapper.state.accel_y / CemuHookAction.ACC_RES_PER_G, # AccelY
			pyr[0] * CemuHookAction.MAGIC_GYRO, # Gyro Pitch
			-pyr[1] * CemuHookAction.MAGIC_GYRO, # Gyro Yaw
			-pyr[2] * CemuHookAction.MAGIC_GYRO, # Gyro Roll
		)
		# log.debug(sa_data)
		self.execute(mapper, sa_data)

	@override
	def describe(self, context: int) -> str:
		if self.name: return self.name
		return _("CemuHook")


# Register actions from current module
Action.register_all(sys.modules[__name__])
