"""SC-Controller - Controller Widget

Button that user can click to choose emulated action for physical button, axis
or pad.

Wraps around actual button defined in glade file.
"""

import itertools
import logging
import os

from gi.repository import Gdk, Gtk, Pango

from scc.actions import Action, MultiAction
from scc.constants import GYRO, LEFT, LSTICK, RIGHT, SCButtons, SCPads, SCSticks, SCTriggers
from scc.gui.ae.gyro_action import is_gyro_enable
from scc.modifiers import DoubleclickModifier
from scc.profile import Profile
from scc.tools import _, nameof

log = logging.getLogger("ControllerWidget")

TRIGGERS = [SCTriggers.LT, SCTriggers.RT]
PADS = [SCPads.LPAD, SCPads.RPAD, SCPads.CPAD]
STICKS = [SCSticks.LSTICK, SCSticks.RSTICK, SCPads.DPAD] # TODO(Martin): WHY IS DPAD NOT A PAD
GYROS = [GYRO]
PRESSABLE = [SCButtons.LPAD, SCButtons.RPAD, SCButtons.LSTICKPRESS, SCButtons.CPADPRESS]
_NOT_BUTTONS = PADS + STICKS + GYROS + TRIGGERS
_NOT_BUTTONS += [x + "TOUCH" for x in PADS]
BUTTONS = [b for b in SCButtons if b.name not in _NOT_BUTTONS]
LONG_TEXT = 16


class ControllerWidget:
	ACTION_CONTEXT = None

	def __init__(self, app, id, use_icon, widget):
		self.app = app
		self.id = id
		self.name = id if type(id) in (str,) else id.name
		self.widget = widget

		self.label = Gtk.Label()
		self.label.set_ellipsize(Pango.EllipsizeMode.END)
		self.icon = Gtk.Image.new_from_file(self.get_image()) if use_icon else None
		self.update()

		motion = Gtk.EventControllerMotion.new()
		motion.connect("enter", self.on_cursor_enter)
		motion.connect("leave", self.on_cursor_leave)
		self.widget.add_controller(motion)
		self.widget.connect("clicked", self.on_click)
		click = Gtk.GestureClick.new()
		click.set_button(0)
		click.connect("released", self.on_button_release)
		self.widget.add_controller(click)

	def get_image(self):
		return os.path.join(self.app.imagepath, self.name + ".svg")

	def update(self):
		self.label.set_label(_("(no action)"))

	def on_click(self, *a):
		self.app.show_editor(self.id)

	def on_button_release(self, gesture, n_press, x, y):
		if gesture.get_current_button() == 3:
			# Rightclick
			self.app.show_context_menu(self.id)

	def on_cursor_enter(self, *a):
		self.app.hilight(self.name)

	def on_cursor_leave(self, *a):
		self.app.hilight(None)


class ControllerButton(ControllerWidget):
	ACTION_CONTEXT = Action.AC_BUTTON

	def __init__(self, app, name, use_icon, widget):
		ControllerWidget.__init__(self, app, name, use_icon, widget)

		if use_icon:
			vbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
			vbox.set_spacing(6)
			separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
			vbox.append(self.icon)
			vbox.append(separator)
			vbox.append(self.label)
			self.widget.add(vbox)
		else:
			self.widget.add(self.label)
		self.widget.show_all()
		self.label.set_max_width_chars(LONG_TEXT)
		if name == "C":
			self.label.set_max_width_chars(10)

	def update(self):
		if self.id in SCButtons.__members__.values() and self.id in self.app.current.buttons:
			txt = self.app.current.buttons[self.id].describe(self.ACTION_CONTEXT)
			if len(txt) > LONG_TEXT or "\n" in txt:
				txt = "\n".join(txt.split("\n")[0:2])
				txt = txt.replace("<", "&lt;").replace(">", "&gt;")
				self.label.set_markup("<small>%s</small>" % (txt,))
			else:
				txt = txt.replace("<", "&lt;").replace(">", "&gt;")
				self.label.set_markup(txt)
		else:
			self.label.set_label(_("(no action)"))


class ControllerStick(ControllerWidget):
	ACTION_CONTEXT = Action.AC_STICK

	def __init__(self, app, id: str, use_icon, enable_press, widget) -> None:
		self.pressed = Gtk.Label() if enable_press else None
		self.click_button = SCButtons.LSTICKPRESS if id == LSTICK else SCButtons.RSTICKPRESS
		ControllerWidget.__init__(self, app, id, use_icon, widget)

		grid = Gtk.Grid()
		grid.set_column_spacing(6)
		motion = Gtk.EventControllerMotion.new()
		motion.connect("motion", self.on_cursor_motion)
		self.widget.add_controller(motion)
		self.label.set_max_width_chars(LONG_TEXT)
		if self.pressed:
			self.label.set_halign(Gtk.Align.START)
			self.pressed.set_halign(Gtk.Align.START)
			self.pressed.set_valign(Gtk.Align.END)
			self.pressed.set_ellipsize(Pango.EllipsizeMode.END)
			self.pressed.set_max_width_chars(LONG_TEXT)
			grid.attach(self.pressed, 2, 2, 1, 1)
		else:
			self.label.set_halign(Gtk.Align.CENTER)
			self.label.set_valign(Gtk.Align.CENTER)
			self.pressed = None
		if self.icon:
			grid.attach(self.icon, 1, 1, 1, 2)
		grid.attach(self.label, 2, 1, 1, 1)
		self.over_icon = False
		self.enable_press = enable_press
		self.widget.add(grid)
		self.widget.show_all()

	def on_cursor_enter(self, *a):
		return

	def on_click(self, *a):
		if self.over_icon and self.enable_press:
			self.app.show_editor(self.click_button)
		else:
			self.app.show_editor(self.id)

	def on_cursor_motion(self, controller, x, y):
		# self.icon.get_allocation().x + self.icon.get_allocation().width	# yields nonsense
		ix2 = 74
		# Check if cursor is placed on icon
		what = None
		if x < ix2:
			what = {
				Profile.LPAD: LEFT,
				Profile.RPAD: RIGHT,
				Profile.CPAD: nameof(SCButtons.CPADPRESS),
				Profile.LSTICK: nameof(SCButtons.LSTICKPRESS),
				Profile.RSTICK: nameof(SCButtons.RSTICKPRESS),
				Profile.DPAD: None,
			}.get(self.name)
		if what:
			self.app.hilight(what)
			self.over_icon = True
		else:
			self.app.hilight(self.name)
			self.over_icon = False

	def _set_label(self, action) -> None:
		self.label.set_label(action.describe(self.ACTION_CONTEXT))

	def update(self):
		if self.id == SCSticks.LSTICK:
			self._set_label(self.app.current.lstick)
		elif self.id == SCSticks.RSTICK:
			self._set_label(self.app.current.rstick)
		elif self.id == SCPads.DPAD:
			self._set_label(self.app.current.pads[SCPads.DPAD])
		if self.click_button and self.pressed:
			action = self.app.current.buttons[self.click_button]
			self._update_pressed(action)

	def _update_pressed(self, action) -> None:
		escape = lambda t: t.replace("<", "&lt;").replace(">", "&gt;")
		if isinstance(action, DoubleclickModifier):
			lines = []
			if action.normalaction:
				txt = action.normalaction.describe(self.ACTION_CONTEXT)
				lines.append(f"Pressed: {escape(txt)}")
			if action.holdaction:
				txt = action.holdaction.describe(self.ACTION_CONTEXT)
				lines.append(f"Hold: {escape(txt)}")
			self.pressed.set_markup("<small>{}</small>".format("\n".join(lines)))
		else:
			txt = escape(action.describe(self.ACTION_CONTEXT))
			self.pressed.set_markup(f"<small>Pressed: {txt}</small>")


class ControllerTrigger(ControllerButton):
	ACTION_CONTEXT = Action.AC_TRIGGER

	def update(self):
		# TODO: Use LT and RT in profile as well
		side = LEFT if self.id == "LT" else RIGHT
		if self.id in TRIGGERS and side in self.app.current.triggers:
			self.label.set_label(self.app.current.triggers[side].describe(self.ACTION_CONTEXT))
		else:
			self.label.set_label(_("(no action)"))


class ControllerPad(ControllerStick):
	ACTION_CONTEXT = Action.AC_PAD

	def __init__(self, app, name, use_icon, enable_press, widget) -> None:
		ControllerStick.__init__(self, app, name, use_icon, enable_press, widget)
		if name in (SCPads.LPAD, SCPads.RPAD):
			self.click_button = getattr(SCButtons, name)
		elif name == SCPads.CPAD:
			self.click_button = SCButtons.CPADPRESS

	def update(self) -> None:
		if self.id == SCPads.LPAD:
			action = self.app.current.pads[SCPads.LPAD]
			pressed = self.app.current.buttons[SCButtons.LPAD]
		elif self.id == SCPads.RPAD:
			action = self.app.current.pads[SCPads.RPAD]
			pressed = self.app.current.buttons[SCButtons.RPAD]
		else:
			action = self.app.current.pads[SCPads.CPAD]
			pressed = self.app.current.buttons[SCButtons.CPADPRESS]

		self._set_label(action)
		if self.pressed:
			self._update_pressed(pressed)


class ControllerGyro(ControllerWidget):
	ACTION_CONTEXT = Action.AC_GYRO

	def __init__(self, app, name, use_icon, widget) -> None:
		self.pressed = Gtk.Label()
		ControllerWidget.__init__(self, app, name, use_icon, widget)

		grid = Gtk.Grid()
		grid.set_column_spacing(6)
		self.label.set_max_width_chars(LONG_TEXT)
		self.label.set_halign(Gtk.Align.START)
		self.pressed.set_max_width_chars(LONG_TEXT)
		self.pressed.set_halign(Gtk.Align.START)
		self.pressed.set_valign(Gtk.Align.END)
		grid.attach(self.icon, 1, 1, 1, 2)
		grid.attach(self.label, 2, 1, 1, 1)
		grid.attach(self.pressed, 2, 2, 1, 1)
		self.over_icon = False
		self.widget.add(grid)
		self.widget.show_all()

	def on_click(self, *a) -> None:
		self.app.show_editor(self.id)

	def _set_label(self, action) -> None:
		if is_gyro_enable(action):
			action = next(itertools.islice(action.mods.values(), 0, 1)) or action.default
		if isinstance(action, MultiAction):
			rv = []
			for a in action.actions:
				d = a.describe(self.ACTION_CONTEXT)
				if d not in rv:
					rv.append(d)
			self.label.set_label("\n".join(rv))
			return
		self.label.set_label(action.describe(self.ACTION_CONTEXT))

	def update(self) -> None:
		self._set_label(self.app.current.gyro)
