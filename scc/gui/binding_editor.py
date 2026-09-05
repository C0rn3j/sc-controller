"""SC Controller - BindingEditor

Base class for main application window and OSD Keyboard bindings editor.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from scc.actions import NoAction
from scc.constants import SCButtons, SCPads, SCSticks, SCTriggers
from scc.gui.action_editor import ActionEditor
from scc.gui.ae.buttons import is_button_repeat, is_button_togle
from scc.gui.ae.gyro_action import is_gyro_enable
from scc.gui.controller_widget import (
	BUTTONS,
	GYROS,
	PADS,
	PRESSABLE,
	STICKS,
	TRIGGERS,
	ControllerButton,
	ControllerGyro,
	ControllerPad,
	ControllerStick,
	ControllerTrigger,
	ControllerWidget,
)
from scc.gui.macro_editor import MacroEditor
from scc.gui.modeshift_editor import ModeshiftEditor
from scc.gui.ring_editor import RingEditor
from scc.macros import Macro, Type
from scc.modifiers import DoubleclickModifier, FeedbackModifier, HoldModifier, ModeModifier, SensitivityModifier
from scc.tools import _

if TYPE_CHECKING:
	from typing import Literal

	from scc.actions import Action
	from scc.gui.editor import Editor
	from scc.profile import Profile


class BindingEditor:
	def __init__(self, app) -> None:
		self.button_widgets: dict[SCButtons | SCPads | SCSticks | Literal["GYRO"], ControllerWidget] = {}
		self.app = app

	def create_binding_buttons(self, use_icons: bool = True, enable_press: bool = True) -> None:
		"""Create ControllerWidget instances for available Gtk.Buttons defined in glade file."""
		for b in BUTTONS:
			w = self.builder.get_object("bt" + b.name)
			if w:
				self.button_widgets[b] = ControllerButton(self, b, use_icons, w)
		for b in TRIGGERS:
			w = self.builder.get_object("bt" + b)
			if w:
				self.button_widgets[b] = ControllerTrigger(self, b, use_icons, w)
		for b in PADS:
			w = self.builder.get_object("bt" + b)
			if w:
				self.button_widgets[b] = ControllerPad(self, b, use_icons, enable_press, w)
		for b in STICKS:
			w = self.builder.get_object("bt" + b)
			if w:
				e = False if b == SCPads.DPAD else enable_press
				self.button_widgets[b] = ControllerStick(self, b, use_icons, e, w)
		w = self.builder.get_object("btLSTICKPRESS")
		if w:
			self.button_widgets[SCButtons.LSTICKPRESS] = ControllerButton(self, SCButtons.LSTICKPRESS, use_icons, w)
		for b in GYROS:
			w = self.builder.get_object("bt" + b)
			if w:
				self.button_widgets[b] = ControllerGyro(self, b, use_icons, w)

	def on_action_chosen(self, id, action, mark_changed=True):
		"""Callback called when action editting is finished in editor.

		Should return None or action being replaced.
		"""
		raise TypeError("Non-overriden on_action_chosen")

	def set_action(self, profile: Profile, id: SCButtons | SCSticks | SCPads, action: Action):
		"""Stores action in profile.

		Returns formely stored action.
		"""
		before = NoAction()
		# First three are LSTICK/RSTICK/CPAD workarounds
		# See https://github.com/C0rn3j/sc-controller/issues/139#issuecomment-5485733318
		if id == SCButtons.LSTICKPRESS and SCSticks.LSTICK in self.button_widgets:
			before, profile.buttons[id] = profile.buttons[id], action
			self.button_widgets[SCSticks.LSTICK].update()
		elif id == SCButtons.RSTICKPRESS and SCSticks.RSTICK in self.button_widgets:
			before, profile.buttons[id] = profile.buttons[id], action
			self.button_widgets[SCSticks.RSTICK].update()
		elif id == SCButtons.CPADPRESS and SCPads.CPAD in self.button_widgets:
			before, profile.buttons[id] = profile.buttons[id], action
			self.button_widgets[SCPads.CPAD].update()
		elif id in PRESSABLE:
			before, profile.buttons[id] = profile.buttons[id], action
			self.button_widgets[id.name].update()
		elif id in BUTTONS:
			before, profile.buttons[id] = profile.buttons[id], action
			# Some buttons (e.g. the stick-touch sensors, set via the Touch tab)
			# have no on-screen widget; just store the action for those.
			if id in self.button_widgets:
				self.button_widgets[id].update()
		elif id in SCTriggers:
			side = id
			before, profile.triggers[side] = profile.triggers[side], action
			self.button_widgets[id].update()
		elif id in GYROS:
			before, profile.gyro = profile.gyro, action
			self.button_widgets[id].update()
		elif id in STICKS + PADS:
			if id == SCSticks.LSTICK:
				before, profile.lstick = profile.lstick, action
			elif id == SCSticks.RSTICK:
				before, profile.rstick = profile.rstick, action
			elif id == SCPads.DPAD:
				before, profile.pads[SCPads.DPAD] = profile.pads[SCPads.DPAD], action
			elif id == SCPads.LPAD:
				before, profile.pads[SCPads.LPAD] = profile.pads[SCPads.LPAD], action
			elif id == SCPads.RPAD:
				before, profile.pads[SCPads.RPAD] = profile.pads[SCPads.RPAD], action
			elif id == SCPads.CPAD:
				before, profile.pads[SCPads.CPAD] = profile.pads[SCPads.CPAD], action
			else:
				raise ValueError(f"unknown id {id}")
			self.button_widgets[id].update()
		return before

	def get_action(self, profile: Profile, id) -> Action | None:
		"""Returns action for specified id.

		Returns None if id is not known.
		"""
		if id in BUTTONS or id in PRESSABLE:
			return profile.buttons[id]
		if id in SCTriggers:
			side = id
			return profile.triggers[side]
		if id in GYROS:
			return profile.gyro
		if id in STICKS + PADS:
			if id == SCSticks.LSTICK:
				return profile.lstick
			if id == SCSticks.RSTICK:
				return profile.rstick
			if id == SCPads.DPAD:
				return profile.pads[SCPads.DPAD]
			if id == SCPads.LPAD:
				return profile.pads[SCPads.LPAD]
			if id == SCPads.RPAD:
				return profile.pads[SCPads.RPAD]
			if id == SCPads.CPAD:
				return profile.pads[SCPads.CPAD]
			raise ValueError(f"unknown id {id}")
		return None

	def choose_editor(self, action: Action, title: str, id: str | None = None) -> Editor:
		"""Chooses apropripate Editor instance for edited action"""
		if isinstance(action, SensitivityModifier):
			action = action.action
		if isinstance(action, FeedbackModifier):
			action = action.action
		if id in GYROS:
			e = ActionEditor(self.app, self.on_action_chosen)
			e.set_title(title)
		elif isinstance(action, (ModeModifier, DoubleclickModifier, HoldModifier)) and not is_gyro_enable(action):
			e = ModeshiftEditor(self.app, self.on_action_chosen)
			e.set_title(_("Mode Shift for %s") % (title,))
		elif RingEditor.is_ring_action(action):
			e = RingEditor(self.app, self.on_action_chosen)
			e.set_title(title)
		elif isinstance(action, Type):
			# Type is subclass of Macro
			e = ActionEditor(self.app, self.on_action_chosen)
			e.set_title(title)
		elif isinstance(action, Macro) and not (is_button_togle(action) or is_button_repeat(action)):
			e = MacroEditor(self.app, self.on_action_chosen)
			e.set_title(_("Macro for %s") % (title,))
		else:
			e = ActionEditor(self.app, self.on_action_chosen)
			e.set_title(title)
		return e

	def hilight(self, button):
		"""Hilights button on image. Overriden by app."""

	def show_editor(self, id):
		raise TypeError("show_editor not overriden")
