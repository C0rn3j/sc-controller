"""SC Controller - OSD Mode Mapper

Very special case of mapper used when main application is launched in "odd mode".
That means it's drawn in OSD layer, cannot be clicked and cannot react to
keyboard. This mapper emulates input events on it using GTK methods.

Mouse movement (but not buttons) are passed to uinput as usuall.
"""

import logging

from gi.repository import Gdk, Gtk

from scc.constants import SCButtons
from scc.gui.gdk_to_key import KEY_TO_GDK
from scc.osd.slave_mapper import SlaveMapper
from scc.uinput import Keys

log = logging.getLogger("OSDModMapper")


class OSDModeMapper(SlaveMapper):
	def __init__(self, app, profile):
		SlaveMapper.__init__(self, profile, None, keyboard="osd", mouse="osd")
		self.app = app
		self.set_special_actions_handler(self)
		self.target_window = None

	def on_sa_restart(self, *a):
		"""Restart / exit handler"""
		self.app.quit()

	def set_target_window(self, w):
		"""Set the GTK4 window whose focused widget receives OSD actions."""
		self.target_window = w

	def create_keyboard(self, name):
		return OSDModeKeyboard(self)

	def create_mouse(self, name):
		return OSDModeMouse(self)


class OSDModeKeyboard:
	"""Translate the navigation keys used by OSD mode into GTK4 actions."""

	def __init__(self, mapper):
		self.mapper = mapper

	def _focused_widget(self):
		window = self.mapper.target_window
		return window.get_focus() if isinstance(window, Gtk.Window) else None

	def pressEvent(self, keys):
		for k in keys:
			keyval = KEY_TO_GDK.get(k)
			direction = {
				Gdk.KEY_Left: Gtk.DirectionType.LEFT,
				Gdk.KEY_Right: Gtk.DirectionType.RIGHT,
				Gdk.KEY_Up: Gtk.DirectionType.UP,
				Gdk.KEY_Down: Gtk.DirectionType.DOWN,
				Gdk.KEY_Tab: Gtk.DirectionType.TAB_FORWARD,
			}.get(keyval)
			if direction is not None:
				self.mapper.target_window.child_focus(direction)
			elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
				focused = self._focused_widget()
				if focused is not None:
					focused.activate()

	def releaseEvent(self, keys=None):
		# GTK4 does not provide public synthetic key-event construction. OSD
		# navigation and activation are completed on key press instead.
		return


class OSDModeMouse:
	"""Provide the mapper's mouse interface using GTK4 widget activation."""

	def __init__(self, mapper):
		self.mapper = mapper

	def synEvent(self, *a):
		pass

	def keyEvent(self, key, val) -> None:
		if key != Keys.BTN_LEFT or not val:
			return
		window = self.mapper.target_window
		focused = window.get_focus() if isinstance(window, Gtk.Window) else None
		if focused is not None:
			focused.activate()

	def moveEvent(self, *args) -> None:
		pass

	moveStickEvent = moveEvent
	scrollEvent = moveEvent
	updateParams = moveEvent
	updateScrollParams = moveEvent


class OSDModeMappings:
	ICONS = {
		"imgOsdmodeAct": SCButtons.A,
		"imgOsdmodeClose": SCButtons.B,
		"imgOsdmodeExit": SCButtons.C,
		"imgOsdmodeSave": SCButtons.Y,
		"imgOsdmodeOK": SCButtons.Y,
	}

	MAIN_WINDOW_BUTTONS = {"vbOsdmodeExit", "vbOsdmodeSave"}
	OTHER_WINDOW_BUTTONS = {"vbOsdmodeExit", "vbOsdmodeAct", "vbOsdmodeClose", "vbOsdmodeOK"}

	def __init__(self, app, mapper, window):
		self.app = app
		self.mapper = mapper
		self.window = window
		self.parent = app.window
		focus = Gtk.EventControllerFocus.new()
		focus.connect("enter", self.on_main_window_focus_in_event)
		focus.connect("leave", self.on_main_window_focus_out_event)
		self.app.window.add_controller(focus)
		self.on_main_window_focus_in_event()

	def set_controller(self, c):
		config = c.load_gui_config(self.app.imagepath or {})
		for name in OSDModeMappings.ICONS:
			w = self.app.builder.get_object(name)
			icon, trash = c.get_button_icon(config, OSDModeMappings.ICONS[name])
			w.set_from_file(icon)

	def on_main_window_focus_in_event(self, *a):
		for x in self.OTHER_WINDOW_BUTTONS:
			self.app.builder.get_object(x).set_visible(False)
		for x in self.MAIN_WINDOW_BUTTONS:
			self.app.builder.get_object(x).set_visible(True)

	def on_main_window_focus_out_event(self, *a):
		for x in self.MAIN_WINDOW_BUTTONS:
			self.app.builder.get_object(x).set_visible(False)
		for x in self.OTHER_WINDOW_BUTTONS:
			self.app.builder.get_object(x).set_visible(True)

	def show(self):
		# GTK4 does not expose override-redirect or absolute top-level window
		# positioning. Present the helper as a regular undecorated window.
		self.window.set_decorated(False)
		self.window.present()


def direction(x):
	if x >= 1:
		return 1
	if x <= -1:
		return -1
	return 0
