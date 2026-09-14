"""Controller navigation for the profile editor's OSD mode.

Use the same virtual input devices as the daemon so GTK4 receives ordinary
keyboard and pointer events on both Wayland and X11.
"""

from gi.repository import Gtk

from scc.constants import SCButtons
from scc.osd.slave_mapper import SlaveMapper


class OSDModeMapper(SlaveMapper):
	def __init__(self, app, profile):
		super().__init__(profile, None,
			keyboard=b"SCController OSD Keyboard", mouse=b"SCController OSD Mouse")
		self.app = app
		self.set_special_actions_handler(self)

	def on_sa_restart(self, *a):
		"""Restart / exit handler"""
		self.app.quit()


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
		# GTK4/Wayland cannot position a separate hints window beneath the
		# editor. Keep the hints in its layout, where they cannot steal focus.
		hints = self.window.get_child()
		if hints is not None:
			self.window.set_child(None)
			self.app.builder.get_object("content").append(hints)
			hints.set_visible(True)


def direction(x):
	if x >= 1:
		return 1
	if x <= -1:
		return -1
	return 0
