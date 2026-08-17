"""SC Controller - Profile

Handles mapping a .sccprofile config stored in a JSON formatted file
"""

from __future__ import annotations

import json
import logging
from json import JSONEncoder
from typing import TYPE_CHECKING

from scc.actions import NoAction
from scc.constants import CPAD, DPAD, GYRO, LEFT, LSTICK, RIGHT, RSTICK, WHOLE, SCButtons
from scc.menu_data import MenuData
from scc.modifiers import HoldModifier
from scc.special_actions import MenuAction

if TYPE_CHECKING:
	from typing import Self

	from scc.actions import Action
	from scc.parser import ActionParser

log = logging.getLogger("profile")


class Profile:
	# Current profile version. When loading profile file with version lower than this, auto-conversion may happen
	VERSION = 1.6

	LEFT = LEFT
	RIGHT = RIGHT
	LPAD = SCButtons.LPAD.name
	RPAD = SCButtons.RPAD.name
	CPAD = CPAD
	DPAD = DPAD
	WHOLE = WHOLE
	LSTICK = LSTICK
	RSTICK = RSTICK
	GYRO = GYRO
	X, Y, Z = "X", "Y", "Z"
	LSTICK_AXES = {X: "lstick_x", Y: "lstick_y"}
	RSTICK_AXES = {X: "rstick_x", Y: "rstick_y"}
	LPAD_AXES = {X: "lpad_x", Y: "lpad_y"}
	RPAD_AXES = {X: "rpad_x", Y: "rpad_y"}
	TRIGGERS = [LEFT, RIGHT]

	def __init__(self, parser: ActionParser) -> None:
		self.buttons: dict[int, Action]
		self.lstick: Action
		self.rstick: Action
		self.gyro: Action
		self.buttons: dict[int, Action]
		self.triggers: dict[str, Action]
		self.parser: ActionParser = parser
		self.clear()
		self.filename: str | None = None
		# UI-only values
		self.is_template: bool = False
		self.description: str = ""

	def save(self, filename: str) -> Self:
		"""Saves profile into file. Returns self"""
		with open(filename, "w") as fileobj:
			self.save_fileobj(fileobj)
		return self

	def save_fileobj(self, fileobj) -> Self:
		"""Saves profile into file-like object. Returns self"""
		data = {
			"_": (self.description if "\n" not in self.description else self.description.strip("\n").split("\n")),
			"buttons": {},
			"lstick": self.lstick,
			"rstick": self.rstick,
			"gyro": self.gyro,
			"trigger_left": self.triggers[Profile.LEFT],
			"trigger_right": self.triggers[Profile.RIGHT],
			"pad_left": self.pads[Profile.LEFT],
			"pad_right": self.pads[Profile.RIGHT],
			"cpad": self.pads[Profile.CPAD],
			"dpad": self.pads[Profile.DPAD],
			"menus": {id: self.menus[id].encode() for id in self.menus},
			"is_template": self.is_template,
			"version": Profile.VERSION,
		}

		for i in self.buttons:
			if self.buttons[i]:
				data["buttons"][i.name] = self.buttons[i]

		# Generate & save json
		jstr = Encoder(sort_keys=True, indent=4).encode(data)
		fileobj.write(jstr)
		return self

	def load(self, filename: str) -> Self:
		"""Loads profile from file. Returns self"""
		with open(filename) as fileobj:
			self.load_fileobj(fileobj)
		self.filename = filename
		return self

	def load_fileobj(self, fileobj) -> Self:
		"""Loads profile from file-like object.

		Filename attribute is not set, what may cause some trouble if used in GUI.

		Returns self.
		"""
		data = json.loads(fileobj.read())
		# Version
		try:
			version = float(data["version"])
		except Exception:
			logging.exception("Failed to load file-like object")
			version = 0

		# Settings - Description
		# (stored in key "_", so it's serialized on top of JSON file)
		if "_" not in data:
			self.description = ""
		elif type(data["_"]) == list:
			self.description = "\n".join(data["_"])
		else:
			self.description = data["_"]
		# Settings - Template
		self.is_template = bool(data["is_template"]) if "is_template" in data else False

		# Buttons
		self.buttons = {}
		for x in SCButtons:
			self.buttons[x] = self.parser.from_json_data(data["buttons"], x.name)
		# Left-stick click was previously named STICKPRESS, and STICK before that.
		if version < 1.6 and "LSTICKPRESS" not in data["buttons"]:
			for legacy_name in ("STICKPRESS", "STICK"):
				if legacy_name in data["buttons"]:
					log.warning("Out of date profile: '%s' renamed to LSTICKPRESS", legacy_name)
					self.buttons[SCButtons.LSTICKPRESS] = self.parser.from_json_data(data["buttons"], legacy_name)
					break
		# Right-stick clicks were historically stored as right-pad clicks.
		if version < 1.5 and "RPAD" in data["buttons"] and "RSTICKPRESS" not in data["buttons"]:
			log.warning("Out of date profile(?): 'RPAD' definition present but RSTICKPRESS isn't!")
			self.buttons[SCButtons.RSTICKPRESS] = self.parser.from_json_data(data["buttons"], "RPAD")

		# Stick & gyro
		if version < 1.6:
			lstick_key = "lstick" if "lstick" in data else "stick"
			if lstick_key == "stick":
				log.warning("Out of date profile: 'stick' renamed to 'lstick'")
			self.lstick = self.parser.from_json_data(data, lstick_key)
		else:
			self.lstick = self.parser.from_json_data(data, "lstick")
		self.gyro = self.parser.from_json_data(data, "gyro")

		if "triggers" in data:
			log.warning("Out of date profile: triggers present instead of trigger_left and trigger_right!")
			# Old format
			# Triggers
			self.triggers = {x: self.parser.from_json_data(data["triggers"], x) for x in Profile.TRIGGERS}

			# Pads
			self.pads = {
				Profile.LEFT: self.parser.from_json_data(data, "left_pad"),
				Profile.RIGHT: self.parser.from_json_data(data, "right_pad"),
				Profile.CPAD: NoAction(),
				Profile.DPAD: NoAction(),
			}

			# Right stick
			self.rstick = NoAction()
		else:
			# New format
			# Triggers
			self.triggers = {
				Profile.LEFT: self.parser.from_json_data(data, "trigger_left"),
				Profile.RIGHT: self.parser.from_json_data(data, "trigger_right"),
			}

			# Pads
			self.pads = {
				Profile.LEFT: self.parser.from_json_data(data, "pad_left"),
				Profile.RIGHT: self.parser.from_json_data(data, "pad_right"),
				Profile.CPAD: self.parser.from_json_data(data, "cpad"),
				Profile.DPAD: self.parser.from_json_data(data, "dpad"),
			}

			# Right stick
			self.rstick = self.parser.from_json_data(data, "rstick")

		# Menus
		self.menus = {}
		if "menus" in data:
			for id in data["menus"]:
				for invalid_char in ".:/":
					if invalid_char in id:
						raise ValueError(f"Invalid character '{invalid_char}' in menu id '{id}'")
				self.menus[id] = MenuData.from_json_data(data["menus"][id], self.parser)

		# Conversion
		self.original_version = version  # TODO: This is temporary
		if version < Profile.VERSION:
			self._convert(version)

		return self

	def clear(self) -> None:
		"""Clears all actions and adds default menu action on center button"""
		self.buttons = {x: NoAction() for x in SCButtons}
		self.buttons[SCButtons.C] = HoldModifier(MenuAction("Default.menu"), normalaction=MenuAction("Default.menu"))
		self.menus = {}
		self.lstick = NoAction()
		self.rstick = NoAction()
		self.is_template = False
		self.triggers = {Profile.LEFT: NoAction(), Profile.RIGHT: NoAction()}
		self.pads = {
			Profile.LEFT: NoAction(),
			Profile.RIGHT: NoAction(),
			Profile.CPAD: NoAction(),
			Profile.DPAD: NoAction(),
		}
		self.gyro = NoAction()

	def get_all_actions(self):
		"""Returns generator with every action defined in this profile,

		including actions in menus.
		Recursively walks into macros, dpads and everything else that can have
		nested actions, so both parent and all child actions are yielded.

		May yield NoAction, but shouldn't yield None.

		Used for checks when profile is exported or imported.
		"""
		for action in self.get_actions():
			for i in action.get_all_actions():
				yield i
		for id in self.menus:
			for i in self.menus[id].get_all_actions():
				yield i

	def get_actions(self):
		"""As get_all_actions, but returns only root actions, without children, and ignores menus."""
		for dct in (self.buttons, self.triggers, self.pads):
			for k in dct:
				yield dct[k]
		for action in (self.lstick, self.rstick, self.gyro):
			yield action

	def get_filename(self):
		"""Returns filename of last loaded file or None."""
		return self.filename

	def compress(self) -> None:
		"""Calls compress on every action to throw out some redundant stuff.

		Note that calling save() after compress() will cause data loss.
		"""
		for dct in (self.buttons, self.triggers, self.pads):
			for x in dct:
				dct[x] = dct[x].compress()
		self.rstick = self.rstick.compress()
		self.lstick = self.lstick.compress()
		self.gyro = self.gyro.compress()
		for menu in self.menus.values():
			menu.compress()

	def _convert(self, from_version: float) -> None:
		"""Performs conversion from older profile version"""
		if from_version < 1:

			# Add 'display Default.menu if center button is held' for old profiles
			c = self.buttons[SCButtons.C]
			if not c:
				# Nothing set to C button
				self.buttons[SCButtons.C] = HoldModifier(
					MenuAction("Default.menu"), normalaction=MenuAction("Default.menu"),
				)
			elif hasattr(c, "holdaction") and c.holdaction:
				# Already set to something, don't overwrite it
				pass
			elif c.to_string().startswith("OSK."):
				# Special case, don't touch this either
				pass
			else:
				self.buttons[SCButtons.C] = HoldModifier(
					MenuAction("Default.menu"), normalaction=self.buttons[SCButtons.C],
				)
		if from_version < 1.1:
			# Convert old scrolling wheel to new representation
			from scc.actions import MouseAction, XYAction
			from scc.modifiers import BallModifier, FeedbackModifier
			from scc.uinput import Rels

			iswheelaction = lambda x: isinstance(x, MouseAction) and x.parameters[0] in (
				Rels.REL_HWHEEL,
				Rels.REL_WHEEL,
			)
			for p in (Profile.LEFT, Profile.RIGHT):
				a, feedback = self.pads[p], None
				if isinstance(a, FeedbackModifier):
					feedback = a.haptic.get_position()
					a = a.action
				if isinstance(a, XYAction):
					if iswheelaction(a.x) or iswheelaction(a.y):
						n = BallModifier(XYAction(a.x, a.y))
						if feedback is not None:
							n = FeedbackModifier(feedback, 4096, 16, n)
						self.pads[p] = n
						log.info("Converted %s to %s", a.to_string(), n.to_string())
		if from_version < 1.2:
			# Convert old trigger settings that were done with ButtonAction
			# to new TriggerAction
			from scc.actions import ButtonAction, MultiAction, TriggerAction
			from scc.constants import TRIGGER_CLICK, TRIGGER_HALF, TRIGGER_MAX
			from scc.uinput import Keys

			for p in (Profile.LEFT, Profile.RIGHT):
				if isinstance(self.triggers[p], ButtonAction):
					buttons, numbers = [], []
					n = None
					# There were one or two keys and zero to two numeric
					# parameters for old button action
					for param in self.triggers[p].parameters:
						if param in Keys:
							buttons.append(param)
						elif type(param) in (int, float):
							numbers.append(int(param))
					if len(numbers) == 0:
						# Trigger range was not specified, assume defaults
						numbers = (TRIGGER_HALF, TRIGGER_CLICK)
					elif len(numbers) == 1:
						# Only lower range was specified, add default upper range
						numbers.append(TRIGGER_CLICK)
					if len(buttons) == 1:
						# If only one button was set, trigger should work like
						# one big button
						n = TriggerAction(numbers[0], ButtonAction(buttons[0]))
					elif len(buttons) == 2:
						# Both buttons were set
						n = MultiAction(
							TriggerAction(numbers[0], numbers[1], ButtonAction(buttons[0])),
							TriggerAction(numbers[1], TRIGGER_MAX, ButtonAction(buttons[1])),
						)

					if n:
						log.info("Converted %s to %s", self.triggers[p].to_string(), n.to_string())
						self.triggers[p] = n
		if from_version < 1.3:
			# Action format completly changed in v0.4, but profile format is same.
			pass


class Encoder(JSONEncoder):
	def default(self, obj):
		# if type(obj) in (list, tuple):
		# return basestring("[" + ", ".join(self.encode(x) for x in obj) + " ]")
		if hasattr(obj, "encode"):
			return obj.encode()
		return JSONEncoder.default(self, obj)
