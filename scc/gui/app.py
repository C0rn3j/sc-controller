"""SC Controller - App

Main application window
"""

import json
import logging
import os
import platform
import re
import sys
from urllib.parse import unquote

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from scc.actions import NoAction
from scc.config import Config
from scc.constants import DAEMON_VERSION, DPAD, LEFT, RIGHT, RSTICK, STICK, STICK_PAD_MAX, SCButtons
from scc.custom import load_custom_module
from scc.gui.binding_editor import BindingEditor
from scc.gui.controller_image import ControllerImage
from scc.gui.controller_widget import BUTTONS, GYROS, PADS, STICKS, TRIGGERS
from scc.gui.daemon_manager import ControllerManager, DaemonManager
from scc.gui.dwsnc import IS_UNITY, headerbar
from scc.gui.parser import GuiActionParser, InvalidAction
from scc.gui.profile_switcher import ProfileSwitcher
from scc.gui.ribar import RIBar
from scc.gui.statusicon import get_status_icon
from scc.gui.userdata_manager import UserDataManager
from scc.modifiers import NameModifier
from scc.paths import get_config_path, get_profiles_path
from scc.profile import Profile
from scc.tools import (
	_,
	check_access,
	find_controller_icon,
	find_gksudo,
	find_profile,
	get_profile_name,
	nameof,
	profile_is_default,
	profile_is_override,
	set_logging_level,
)

log = logging.getLogger("App")

# Human-friendly default names per controller type (controller.get_type()).
# Used when the user has not given the controller a custom name. Wrapped in
# _() at lookup time so they remain translatable.
CONTROLLER_TYPE_NAMES = {
	"sc": "Steam Controller v1",
	"scbt": "Steam Controller v1 (Bluetooth)",
	"sc2": "Steam Controller v2",
	"deck": "Steam Deck",
	"ds4": "DualShock 4",
	"ds4evdev": "DualShock 4",
	"ds5": "DualSense",
	"ds5evdev": "DualSense",
	"ds5bt_hidraw": "DualSense",
	"hid": "HID Controller",
	"evdev": "Controller",
	"rpad": "Remote Pad",
	"fake": "Fake Controller",
}


class App(Gtk.Application, UserDataManager, BindingEditor):
	"""Main application / window."""

	HILIGHT_COLOR = "#FF00FF00"  # ARGB
	OBSERVE_COLOR = "#FF60A0FF"  # ARGB
	CONFIG = "scc.config.json"
	RELEASE_URL = "https://github.com/C0rn3j/sc-controller/releases/tag/v%s"

	def __init__(self, gladepath: str = "/usr/share/scc", imagepath: str = "/usr/share/scc/images"):
		Gtk.Application.__init__(
			self,
			application_id="me.c0rn3j.scc",
			flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE | Gio.ApplicationFlags.NON_UNIQUE,
		)
		UserDataManager.__init__(self)
		BindingEditor.__init__(self, self)
		# Setup Gtk.Application
		self.convert_old_profiles()
		self.setup_commandline()
		# Setup DaemonManager
		self.dm = DaemonManager()
		self.dm.connect("alive", self.on_daemon_alive)
		self.dm.connect("event", self.on_daemon_event_observer)
		self.dm.connect("controller-count-changed", self.on_daemon_ccunt_changed)
		self.dm.connect("dead", self.on_daemon_dead)
		self.dm.connect("error", self.on_daemon_error)
		(self.dm.connect("reconfigured", self.on_daemon_reconfigured),)
		self.dm.connect("version", self.on_daemon_version)
		# Load custom stuff
		load_custom_module(log, "gui")
		# Set variables
		self.config = Config()
		self.gladepath = gladepath
		self.imagepath = imagepath
		self.builder = None
		self.recursing = False
		self.statusicon = None
		self.status = "unknown"
		self.context_menu_for = None
		self.daemon_changed_profile = False
		self.osk_edit_mode = False  # --osd: open only the OSD-keyboard bindings editor
		self.background = None
		self.outdated_version = None
		self.profile_switchers: list[ProfileSwitcher] = []
		self.test_mode_controller = None
		self.current_ui_layout = "default"  # only "default" and "deck" are supported
		self.current_file = None  # Currently edited file
		self.controller_count: int = 0
		self._controller_shown: bool = False
		self.current = Profile(GuiActionParser())
		self.just_started = True
		self.button_widgets = {}
		self.hilights = {App.HILIGHT_COLOR: set(), App.OBSERVE_COLOR: set()}
		self.undo = []
		self.redo = []

	def setup_widgets(self):
		# Important stuff
		self.builder = Gtk.Builder()
		self.builder.add_from_file(os.path.join(self.gladepath, "app.glade"))
		self.builder.connect_signals(self)
		self.window = self.builder.get_object("window")
		self.add_window(self.window)
		self.window.set_title(_("SC Controller"))
		self.window.set_wmclass("SC Controller", "SC Controller")
		self.ribar = None
		self.create_binding_buttons()

		ps = self.add_switcher(12, 12)
		ps.set_allow_new(True)
		ps.set_profile(self.load_profile_selection())
		ps.connect("new-clicked", self.on_new_clicked)
		ps.connect("save-clicked", self.on_save_clicked)

		# Controller selector: shown above the profile switcher only when more
		# than one controller is connected. Lets the user pick which controller
		# the editor shows (replacing the old stack of one profile bar per
		# controller + the per-bar "switch-to" pen button). Each row is the
		# controller's icon + name, with its current profile as dim secondary
		# text; selecting a row makes that controller the active/edited one.
		self._selector_recursing = False
		self.controller_selector = self._build_controller_selector()

		# Drag&drop target
		self.builder.get_object("content").drag_dest_set(
			Gtk.DestDefaults.ALL,
			[
				Gtk.TargetEntry.new("text/uri-list", Gtk.TargetFlags.OTHER_APP, 0),
				Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.OTHER_APP, 0),
			],
			Gdk.DragAction.COPY,
		)

		# 'C' and 'CPAD' buttons
		vbc = self.builder.get_object("vbC")
		self.main_area = self.builder.get_object("mainArea")
		vbc.get_parent().remove(vbc)

		# Background
		self.background = ControllerImage(self)
		self.background.connect("hover", self.on_background_area_hover)
		self.background.connect("leave", self.on_background_area_hover, None)
		self.background.connect("click", self.on_background_area_click)
		self.background.connect("button-press-event", self.on_background_button_press)
		self.main_area.put(self.background, 0, 0)
		self.main_area.put(vbc, 0, 0)  # (self.IMAGE_SIZE[0] / 2) - 90, self.IMAGE_SIZE[1] - 100)

		# Test markers (those blue circles over PADs and sticks)
		self.lpad_test = Gtk.Image.new_from_file(os.path.join(self.imagepath, "test-cursor.svg"))
		self.rpad_test = Gtk.Image.new_from_file(os.path.join(self.imagepath, "test-cursor.svg"))
		self.stick_test = Gtk.Image.new_from_file(os.path.join(self.imagepath, "test-cursor.svg"))
		self.rstick_test = Gtk.Image.new_from_file(os.path.join(self.imagepath, "test-cursor.svg"))
		self.dpad_test = Gtk.Image.new_from_file(os.path.join(self.imagepath, "test-cursor.svg"))
		self.main_area.put(self.lpad_test, 40, 40)
		self.main_area.put(self.rpad_test, 290, 90)
		self.main_area.put(self.stick_test, 150, 40)
		self.main_area.put(self.rstick_test, 290, 40)
		self.main_area.put(self.dpad_test, 40, 90)

		# Headerbar
		headerbar(self.builder.get_object("hbWindow"))

	def load_gui_config_for_controller(self, controller: ControllerManager, first) -> None:
		"""Loads controller config, changes image and hides, shows or disables buttons around it.

		To make this look less jumpy, Gtk.Stack is used to make transition
		to empty page and only after that is grid repopulated, everything
		set up and Stack switched back to original page.
		"""
		stckEditor = self.builder.get_object("stckEditor")
		lblEmpty = self.builder.get_object("lblEmpty")
		if controller:
			self._controller_shown = True
			config = controller.load_gui_config(self.imagepath or {})
		else:
			config = {}
		config = self.background.use_config(config, controller=controller)

		def do_loading() -> None:
			"""Called after transition is finished"""
			self.background.use_config(config, controller=controller)
			self.apply_gui_config_buttons(config)

		if first:
			b1 = self.background.get_config()["gui"]["background"]
			b2 = config["gui"]["background"]
			if b1 == b2:
				# If application has just started and image is
				# not changing, transition would just look weird
				do_loading()
				return
		else:
			stckEditor.set_transition_type(Gtk.StackTransitionType.SLIDE_DOWN)
		stckEditor.set_visible_child(lblEmpty)
		GLib.timeout_add(stckEditor.get_transition_duration(), do_loading)

	def apply_gui_config_buttons(self, config) -> None:
		"""Changes UI according to controller configuration"""
		stckEditor = self.builder.get_object("stckEditor")
		grEditor = self.builder.get_object("grEditor")
		btCPAD = self.builder.get_object("btCPAD")
		btDPAD = self.builder.get_object("btDPAD")
		btGYRO = self.builder.get_object("btGYRO")
		btC = self.builder.get_object("btC")
		btLGRIPTOUCH = self.builder.get_object("btLGRIPTOUCH")
		btRGRIPTOUCH = self.builder.get_object("btRGRIPTOUCH")
		btRSTICK = self.builder.get_object("btRSTICK")

		buttons = ControllerImage.get_names(config.get("buttons", {}))
		axes = ControllerImage.get_names(config.get("axes", {}))
		gyros = config.get("gyros", False)
		# Set sensitivity to signalize available inputs
		# Buttons (as on image)
		for b in BUTTONS:
			w = self.builder.get_object("bt" + nameof(b))
			if w:
				w.set_sensitive(nameof(b) in buttons)
		# Buttons (as GTK Widgets)
		# A controller may ship its own side-panel icons under
		# images/<background>/<NAME>.svg (e.g. images/sc2/); use them when
		# present, else fall back to the shared default icon.
		bg = config.get("gui", {}).get("background")
		for b in self.button_widgets:
			try:
				w = self.button_widgets[b]
				icon, trash = ControllerManager.get_button_icon(config, b, True)
				if bg:
					cand = os.path.join(self.imagepath, bg, nameof(b) + ".svg")
					if os.path.exists(cand):
						icon = cand
				w.icon.set_from_file(icon)
			except Exception:
				pass
		# Triggers
		w = self.builder.get_object("btLT")
		if w:
			w.set_sensitive("ltrig" in axes)
		w = self.builder.get_object("btRT")
		if w:
			w.set_sensitive("rtrig" in axes)
		# Sticks & pads
		for b in PADS + STICKS:
			w = self.builder.get_object("bt" + nameof(b))
			if w:
				w.set_sensitive(b.lower() + "_x" in axes or b.lower() + "_y" in axes or nameof(b) in buttons)
		# Gyro
		for b in GYROS:
			w = self.builder.get_object("bt" + b)
			if w:
				# TODO: Maybe actual detection
				w.set_sensitive(gyros)

		for w in (btC, btCPAD, btDPAD, btGYRO, btLGRIPTOUCH, btRGRIPTOUCH, btRSTICK):
			if w:
				w.set_visible(w.get_sensitive())

		# Re-layout if needed
		expected_layout = "default"
		if "rstick_x" in axes and btC.get_sensitive():
			expected_layout = "deck"

		if expected_layout != self.current_ui_layout:
			self.apply_ui_layout(expected_layout)

		# The Steam Deck maps its lower back paddles to LGRIP/RGRIP (labelled
		# L5/R5) and the upper ones to LGRIP2/RGRIP2 (L4/R4) - the reverse of the
		# SC2. Left alone the side panel reads L5/R5 above L4/R4; reorder the
		# paddle buttons so they match the device (L4/R4 above L5/R5). Every other
		# controller (incl. the SC2, whose LGRIP=L4) keeps the .glade order.
		if bg == "deck":
			grip_pairs = (("btLGRIP2", "btLGRIP"), ("btRGRIP2", "btRGRIP"))
		else:
			grip_pairs = (("btLGRIP", "btLGRIP2"), ("btRGRIP", "btRGRIP2"))
		for above, below in grip_pairs:
			wa = self.builder.get_object(above)
			wb = self.builder.get_object(below)
			if wa and wb and wa.get_parent() is wb.get_parent():
				kids = wa.get_parent().get_children()
				if kids.index(wa) > kids.index(wb):
					wa.get_parent().reorder_child(wa, kids.index(wb))

		stckEditor.set_visible_child(grEditor)
		GLib.idle_add(self.on_c_size_allocate)

	def apply_ui_layout(self, layout) -> None:
		"""Changes layout of ui elements to fit additional buttons needed for Deck"""
		if layout == "deck":
			btLGRIP = self.builder.get_object("btLGRIP")
			# Put 'DPAD' at the top of the left column (above the back paddles),
			# to mirror the Deck's physical layout: D-Pad, L4, L5, View, Steam.
			btDPAD = self.builder.get_object("btDPAD")
			btDPAD.get_parent().remove(btDPAD)
			btLGRIP.get_parent().pack_start(btDPAD, False, True, 6)
			btLGRIP.get_parent().reorder_child(btDPAD, 2)
			# Move 'C' (Steam) to the bottom of the LEFT column (was the right)
			btC = self.builder.get_object("btC")
			btC.get_parent().remove(btC)
			btC.set_margin_right(0)
			btLGRIP.get_parent().pack_start(btC, False, True, 0)
			# Move 'GYRO' button to middle of image (where C was)
			btGYRO = self.builder.get_object("btGYRO")
			btGYRO.get_parent().remove(btGYRO)
			vbC = self.builder.get_object("vbC")
			vbC.pack_start(btGYRO, False, True, 0)
			btGYRO.set_margin_top(30)

	def setup_statusicon(self) -> None:
		if self.statusicon is None:
			menu = self.builder.get_object("mnuTray")
			self.statusicon = get_status_icon(self.imagepath, menu)
			self.statusicon.connect("clicked", self.on_statusicon_clicked)
		else:
			self.statusicon.show()

		# if not self.statusicon.is_clickable():
		# self.builder.get_object("mnuShowWindowTray").set_visible(True)
		# Workaround - always add it to the menu, see https://github.com/C0rn3j/sc-controller/issues/53
		self.builder.get_object("mnuShowWindowTray").set_visible(True)
		GLib.idle_add(self.statusicon.set, f"scc-{self.status}", _("SC Controller"))

	def destroy_statusicon(self):
		self.statusicon.hide()

	def check(self):
		"""Performs various (three) checks and reports possible problems"""
		# TODO: Maybe not best place to do this
		try:
			# Dynamic modules
			with open("/proc/modules") as file:
				rawlist = file.read().split("\n")
			kernel_mods = [line.split(" ")[0] for line in rawlist]
			# Built-in modules
			release = platform.uname()[2]
			with open("/lib/modules/%s/modules.builtin" % release) as file:
				rawlist = file.read().split("\n")
			kernel_mods += [os.path.split(x)[-1].split(".")[0] for x in rawlist]
		except Exception:
			# Maybe running on BSD or Windows...
			kernel_mods = []

		if len(kernel_mods) > 0 and "uinput" not in kernel_mods:
			# There is no uinput
			msg = _("uinput kernel module not loaded")
			msg += "\n\n" + _("Please, consult your distribution manual on how to enable uinput")
			msg += "\n" + _('or click on "Fix Temporary" button to attempt fix that should work until next restart.')
			ribar = self.show_error(msg)
			gksudo = find_gksudo()
			if gksudo and not hasattr(ribar, "_fix_tmp"):
				button = Gtk.Button.new_with_label(_("Fix Temporary"))
				ribar._fix_tmp = button
				button.connect(
					"clicked",
					self.apply_temporary_fix,
					gksudo + ["modprobe", "uinput"],
					_("This will load missing uinput module."),
				)
				ribar.add_button(button, -1)
			return True
		if not os.path.exists("/dev/uinput"):
			# /dev/uinput missing
			msg = _("/dev/uinput doesn't exists")
			msg += "\n" + _("uinput kernel module is loaded, but /dev/uinput is missing.")
			# msg += "\n\n" + _('Please, consult your distribution manual on what in the world could cause this.')
			msg += "\n\n" + _("Please, consult your distribution manual on how to enable uinput")
			self.show_error(msg)
			return True
		if not check_access("/dev/uinput"):
			# Cannot acces uinput
			msg = _("You don't have required access to /dev/uinput.")
			msg += "\n" + _("This will most likely prevent emulation from working.")
			msg += "\n\n" + _("Please, consult your distribution manual on how to enable uinput")
			msg += "\n" + _('or click on "Fix Temporary" button to attempt fix that should work until next restart.')
			ribar = self.show_error(msg)
			gksudo = find_gksudo()
			if gksudo and not hasattr(ribar, "_fix_tmp"):
				button = Gtk.Button.new_with_label(_("Fix Temporary"))
				ribar._fix_tmp = button
				button.connect(
					"clicked",
					self.apply_temporary_fix,
					gksudo + ["chmod", "666", "/dev/uinput"],
					_(
						"This will enable input emulation for <i>every application</i> and <i>all users</i> on this machine.",
					),
				)
				ribar.add_button(button, -1)
			return True
		return False

	def apply_temporary_fix(self, trash, shell_command, message):
		"""Display MessageBox with confirmation, try to run passed shell command and restart daemon.

		Doing this allows user to teporary fix some uinput-related problems
		by his vaim belief I'll not format his harddrive.
		"""
		d = Gtk.MessageDialog(
			parent=self.window,
			flags=Gtk.DialogFlags.MODAL,
			type=Gtk.MessageType.WARNING,
			buttons=Gtk.ButtonsType.OK_CANCEL,
			message_format=_("sudo fix-my-pc"),
		)

		def on_response(dialog, response_id):
			if response_id == -5:  # OK button, not defined anywhere
				sudo = Gio.Subprocess.new(shell_command, 0)
				sudo.communicate(None, None)
				if sudo.get_exit_status() == 0:
					self.dm.restart()
				else:
					d2 = Gtk.MessageDialog(
						parent=d,
						flags=Gtk.DialogFlags.MODAL,
						type=Gtk.MessageType.ERROR,
						buttons=Gtk.ButtonsType.OK,
						message_format=_("Command Failed"),
					)
					d2.run()
					d2.destroy()
			d.destroy()

		d.connect("response", on_response)
		d.format_secondary_markup(
			_("""Following command is going to be executed:

<b>%s</b>

%s""")
			% (" ".join(shell_command), message),
		)
		d.show()

	def hilight(self, button):
		"""Hilights specified button on background image"""
		if button:
			self.hilights[App.HILIGHT_COLOR] = set([button])
		else:
			self.hilights[App.HILIGHT_COLOR] = set()
		self._update_background()

	def _update_background(self):
		h = {}
		for color in self.hilights:
			for i in self.hilights[color]:
				h[i] = color
		self.background.hilight(h)

	def hint(self, button):
		"""As hilight, but marks GTK Button as well"""
		active = None
		for b in self.button_widgets.values():
			if b.widget.get_sensitive():
				b.widget.set_state(Gtk.StateType.NORMAL)
				if b.name == button:
					active = b.widget

		if active is not None:
			active.set_state(Gtk.StateType.ACTIVE)

		self.hilight(button)

	def show_editor(self, id):
		action = self.get_action(self.current, id)
		ae = self.choose_editor(action, "", id)
		ae.allow_first_page()
		ae.set_input(id, action)
		ae.show(self.window)

	def show_context_menu(self, for_id):
		"""Sets sensitivity of popup menu items and displays it on screen"""
		mnuPopup = self.builder.get_object("mnuPopup")
		mnuCopy = self.builder.get_object("mnuCopy")
		mnuClear = self.builder.get_object("mnuClear")
		mnuPaste = self.builder.get_object("mnuPaste")
		mnuEPress = self.builder.get_object("mnuEditPress")
		mnuEPressS = self.builder.get_object("mnuEditPressSeparator")
		self.context_menu_for = for_id
		clp = Gtk.Clipboard.get_default(Gdk.Display.get_default())
		mnuCopy.set_sensitive(bool(self.get_action(self.current, for_id)))
		mnuClear.set_sensitive(bool(self.get_action(self.current, for_id)))
		mnuPaste.set_sensitive(clp.wait_is_text_available())
		mnuEPress.set_visible(for_id in STICKS + PADS)
		mnuEPressS.set_visible(mnuEPress.get_visible())

		mnuPopup.popup(None, None, None, None, 3, Gtk.get_current_event_time())

	def save_config(self) -> None:
		self.config.save()
		self.dm.reconfigure()
		self.enable_test_mode()

	def on_statusicon_clicked(self, *a) -> None:
		"""Handler for user clicking on tray icon button."""
		self.window.set_visible(not self.window.get_visible())

	def on_window_delete_event(self, *a) -> bool:
		"""Called when user tries to close window"""
		if not IS_UNITY and self.config["gui"]["enable_status_icon"] and self.config["gui"]["minimize_to_status_icon"]:
			if self.statusicon and self.statusicon.get_property("active"):
				# Override closing and hide instead
				self.window.set_visible(False)
			else:
				log.error("Tray icon not available/active, refusing to close window!")
		else:
			self.on_mnuExit_activate()
		return True # TRUE to stop other handlers from being invoked for the event. FALSE to propagate the event further.

	def on_mnuClear_activate(self, *a):
		"""Handler for 'Clear' context menu item.
		Simply sets NoAction to input.
		"""
		self.on_action_chosen(self.context_menu_for, NoAction())

	def on_mnuCopy_activate(self, *a):
		"""Handler for 'Copy' context menu item.
		Converts action to string and sends that string to clipboard.
		"""
		a = self.get_action(self.current, self.context_menu_for)
		if a:
			if a.name:
				a = NameModifier(a.name, a)
			clp = Gtk.Clipboard.get_default(Gdk.Display.get_default())
			clp.set_text(a.to_string().encode("utf-8"), -1)
			clp.store()

	def on_mnuPaste_activate(self, *a):
		"""Handler for 'Paste' context menu item.
		Reads string from clipboard, parses it as action and sets that action
		on selected input.
		"""
		clp = Gtk.Clipboard.get_default(Gdk.Display.get_default())
		text = clp.wait_for_text()
		if text:
			a = GuiActionParser().restart(text.decode("utf-8")).parse()
			if not isinstance(a, InvalidAction):
				self.on_action_chosen(self.context_menu_for, a)

	def on_mnuEditPress_activate(self, *a):
		"""Handler for 'Edit Pressed Action' context menu item.
		"""
		id = self.context_menu_for
		if id == STICK:
			id = nameof(SCButtons.STICKPRESS)
		elif id == Profile.RSTICK:
			id = nameof(SCButtons.RSTICKPRESS)
		elif id == Profile.CPAD:
			id = nameof(SCButtons.CPADPRESS)
		self.show_editor(getattr(SCButtons, id))

	def on_mnuGlobalSettings_activate(self, *a):
		from scc.gui.global_settings import GlobalSettings

		gs = GlobalSettings(self)
		gs.show(self.window)

	def on_mnuImport_activate(self, *a):
		"""Handler for 'Import Steam Profile' context menu item.
		Displays apropriate dialog.
		"""
		from scc.gui.importexport.dialog import Dialog

		ied = Dialog(self)
		ied.show(self.window)

	def on_btUndo_clicked(self, *a):
		if len(self.undo) < 1:
			return
		undo, self.undo = self.undo[-1], self.undo[0:-1]
		self.set_action(self.current, undo.id, undo.before)
		self.redo.append(undo)
		self.builder.get_object("btRedo").set_sensitive(True)
		if len(self.undo) < 1:
			self.builder.get_object("btUndo").set_sensitive(False)
		self.on_profile_modified()

	def on_btRedo_clicked(self, *a):
		if len(self.redo) < 1:
			return
		redo, self.redo = self.redo[-1], self.redo[0:-1]
		self.set_action(self.current, redo.id, redo.after)
		self.undo.append(redo)
		self.builder.get_object("btUndo").set_sensitive(True)
		if len(self.redo) < 1:
			self.builder.get_object("btRedo").set_sensitive(False)
		self.on_profile_modified()

	def on_profiles_loaded(self, profiles) -> None:
		for ps in self.profile_switchers:
			ps.set_profile_list(profiles)

	def undeletable_dialog(self, dlg, *a):
		dlg.hide()
		return True

	def on_btNewProfile_clicked(self, *a):
		"""Called when new profile name is set and OK is clicked."""
		txNewProfile = self.builder.get_object("txNewProfile")
		rbNewProfile = self.builder.get_object("rbNewProfile")

		dlg = self.builder.get_object("dlgNewProfile")
		if rbNewProfile.get_active():
			# Creating blank profile is requested
			self.current.clear()
		else:
			self.current.is_template = False
		self.new_profile(self.current, txNewProfile.get_text())
		dlg.hide()

	def on_rbNewProfile_group_changed(self, *a):
		"""Called when user clicks 'Copy current profile' button.

		If profile name was not changed by user before clicking it,
		it's automatically changed.
		"""
		txNewProfile = self.builder.get_object("txNewProfile")
		rbNewProfile = self.builder.get_object("rbNewProfile")

		if not txNewProfile._changed:
			self.recursing = True
			if rbNewProfile.get_active():
				# Create empty profile
				txNewProfile.set_text(self.generate_new_name())
			else:
				# Copy current profile
				txNewProfile.set_text(self.generate_copy_name(txNewProfile._name))
			self.recursing = False

	def on_profile_modified(self, update_ui: bool = True) -> None:
		"""Called when selected profile is modified in memory."""
		if update_ui:
			self.profile_switchers[0].set_profile_modified(True, self.current.is_template)

		if not self.current_file.get_path().endswith(".mod"):
			mod = self.current_file.get_path() + ".mod"
			self.current_file = Gio.File.new_for_path(mod)

		self.save_profile(self.current_file, self.current)

	def on_profile_loaded(self, profile: Profile, giofile: Gio.File):
		self.current = profile
		self.current_file = giofile
		self.recursing = True
		self.profile_switchers[0].set_profile_modified(False, self.current.is_template)
		self.builder.get_object("txProfileFilename").set_text(giofile.get_path())
		self.builder.get_object("txProfileDescription").get_buffer().set_text(self.current.description)
		self.builder.get_object("cbProfileIsTemplate").set_active(self.current.is_template)
		for b in self.button_widgets.values():
			b.update()
		self.recursing = False

	def on_profile_selected(self, ps, name, giofile: Gio.File):
		if ps == self.profile_switchers[0]:
			self.load_profile(giofile)
		if ps.get_controller():
			ps.get_controller().set_profile(giofile.get_path())

	def on_unknown_profile(self, ps, name):
		log.warning("Daemon reported unknown profile: '%s'; Overriding.", name)
		if self.current_file is not None and ps.get_controller() is not None:
			ps.get_controller().set_profile(self.current_file.get_path())

	def on_save_clicked(self, *a):
		if self.current_file.get_path().endswith(".mod"):
			orig = self.current_file.get_path()[0:-4]
			self.current_file = Gio.File.new_for_path(orig)

		if self.current.is_template:
			# Ask user if he is OK with overwriting template
			d = Gtk.MessageDialog(
				parent=self.window,
				flags=Gtk.DialogFlags.MODAL,
				type=Gtk.MessageType.QUESTION,
				buttons=Gtk.ButtonsType.YES_NO,
				message_format=_("You are about to save changes over template.\nAre you sure?"),
			)
			NEW_PROFILE_BUTTON = 7
			d.add_button(_("Create New Profile"), NEW_PROFILE_BUTTON)

			r = d.run()
			d.destroy()
			if r == NEW_PROFILE_BUTTON:
				# New profile button clicked
				ps = self.profile_switchers[0]
				rbCopyProfile = self.builder.get_object("rbCopyProfile")
				self.on_new_clicked(ps, ps.get_profile_name())
				rbCopyProfile.set_active(True)
				return
			if r != -8:
				# Bail out if user answers anything but yes
				return

		self.save_profile(self.current_file, self.current)

	def on_switch_to_clicked(self, ps, *a) -> None:
		"""Switches editor to another controller"""
		ps0 = self.profile_switchers[0]
		if ps == ps0:
			return

		c, p = ps.get_controller(), ps.get_profile_name()
		c0, p0 = ps0.get_controller(), ps0.get_profile_name()

		ps0.set_controller(c)
		ps0.set_profile(p)
		ps.set_controller(c0)
		ps.set_profile(p0)

		self.load_gui_config_for_controller(c, False)
		self.enable_test_mode(c)

	def on_profile_saved(self, giofile: Gio.File, send: bool = True) -> None:
		"""Called when selected profile is saved to disk"""
		if giofile.get_path().endswith(".mod"):
			# Special case, this one is saved only to be sent to daemon
			# and user doesn't need to know about it
			if self.dm.is_alive():
				controller = self.profile_switchers[0].get_controller()
				if controller:
					controller.set_profile(giofile.get_path())
				else:
					self.dm.set_profile(giofile.get_path())
			return

		self.profile_switchers[0].set_profile_modified(False, self.current.is_template)
		if send and self.dm.is_alive() and not self.daemon_changed_profile:
			# Re-send to every controller currently running this profile (not
			# just the active one), so a saved profile reloads on all of them.
			for controller in self.dm.get_controllers():
				if controller:
					active = controller.get_profile()
					if active.endswith(".mod"):
						active = active[0:-4]
					if active == giofile.get_path():
						controller.set_profile(giofile.get_path())

		self.current_file = giofile

	def generate_new_name(self):
		"""Generates name for new profile.
		That is 'New Profile X', where X is number that makes name unique.
		"""
		i = 1
		new_name = _("New Profile %s") % (i,)
		filename = os.path.join(get_profiles_path(), new_name + ".sccprofile")
		while os.path.exists(filename):
			i += 1
			new_name = _("New Profile %s") % (i,)
			filename = os.path.join(get_profiles_path(), new_name + ".sccprofile")
		return new_name

	def generate_copy_name(self, name):
		"""Generates name for profile copy.
		That is 'New Profile X', where X is number that makes name unique.
		"""
		new_name = _("%s (copy)") % (name,)
		filename = os.path.join(get_profiles_path(), new_name + ".sccprofile")
		i = 2
		while os.path.exists(filename):
			new_name = _("%s (copy %s)") % (name,)
			filename = os.path.join(get_profiles_path(), new_name + ".sccprofile")
			i += 1
		return new_name

	def on_txNewProfile_changed(self, tx):
		if self.recursing:
			return
		tx._changed = True

	def on_new_clicked(self, ps, name):
		dlg = self.builder.get_object("dlgNewProfile")
		txNewProfile = self.builder.get_object("txNewProfile")
		rbNewProfile = self.builder.get_object("rbNewProfile")
		self.recursing = True
		rbNewProfile.set_active(True)
		txNewProfile.set_text(self.generate_new_name())
		txNewProfile._name = name
		txNewProfile._changed = False
		self.recursing = False
		dlg.set_transient_for(self.window)
		dlg.show()

	def on_action_chosen(self, id, action, mark_changed=True):
		before = self.set_action(self.current, id, action)
		if mark_changed:
			if before.to_string() != action.to_string():
				# TODO: Maybe better comparison
				self.undo.append(UndoRedo(id, before, action))
				self.builder.get_object("btUndo").set_sensitive(True)
			self.on_profile_modified()
		else:
			self.on_profile_modified(update_ui=False)
		return before

	def on_background_area_hover(self, trash, area):
		self.hint(area)

	def on_background_button_press(self, trash, event):
		if event.button == 3:
			mnuImage = self.builder.get_object("mnuImage")
			mnuImage.popup(None, None, None, None, 3, Gtk.get_current_event_time())

	def on_mnu_change_background_image(self, mnu, *a):
		command, filename = mnu.get_name().split(",")
		if command == "background":
			self.background.override_background(filename)
		elif command == "buttons":
			self.background.override_buttons(filename)
			self.apply_gui_config_buttons(self.background.get_config())
		elif command == "undo":
			self.background.undo_override()
			self.apply_gui_config_buttons(self.background.get_config())

	def on_background_area_click(self, trash, area):
		if area in [x.name for x in BUTTONS]:
			self.hint(None)
			self.show_editor(getattr(SCButtons, area))
		elif area in TRIGGERS + STICKS + PADS:
			self.hint(None)
			self.show_editor(area)

	def on_c_size_allocate(self, *a):
		"""Called when size of 'Button C' or CPAD is changed.
		Centers buttons on background image
		"""
		main_area = self.builder.get_object("mainArea")
		y = main_area.get_allocation().height - 5
		w = self.builder.get_object("vbC")
		allocation = w.get_allocation()
		x = (self.background.get_allocation().width - allocation.width) / 2
		y -= allocation.height

		if self.background.get_config()["gui"]["no_buttons_in_gui"]:
			# no_buttons_in_gui is used to keep image without changes
			# This moves "C" button away so it doesn't obscure it as well
			y = 10

		if w.get_parent():
			main_area.move(w, x, y)
		else:
			main_area.put(w, x, y)
		return False

	def on_ebImage_motion_notify_event(self, box, event):
		self.background.on_mouse_moved(event.x, event.y)

	def on_exiting_n_daemon_killed(self, *a):
		self.quit()

	def on_mnuExit_activate(self, *a):
		if self.app.config["gui"]["autokill_daemon"]:
			log.debug("Terminating scc-daemon")
			for x in ("content", "mnuEmulationEnabled", "mnuEmulationEnabledTray"):
				w = self.builder.get_object(x)
				w.set_sensitive(False)
			self.set_daemon_status("unknown", False)
			self.hide_error()
			if self.dm.is_alive():
				self.dm.connect("dead", self.on_exiting_n_daemon_killed)
				self.dm.connect("error", self.on_exiting_n_daemon_killed)
				self.dm.stop()
			else:
				# Daemon appears to be dead, kill it just in case
				self.dm.stop()
				self.quit()
		else:
			self.quit()

	def on_mnuAbout_activate(self, *a) -> None:
		from scc.gui.aboutdialog import AboutDialog

		AboutDialog(self).show(self.window)

	def on_daemon_alive(self, *a) -> None:
		self.set_daemon_status("alive", True)
		if not self.release_notes_visible():
			self.hide_error()
		self.just_started = False
		if self.profile_switchers[0].get_file() is not None and not self.just_started:
			self.dm.set_profile(self.current_file.get_path())
		GLib.timeout_add_seconds(1, self.check)
		self.enable_test_mode()

	def on_daemon_ccunt_changed(self, daemon, count: int) -> None:
		# A single profile switcher always shows the *active* controller; any
		# others are reachable through the controller selector above it (built
		# in setup_widgets). So here we only keep the active controller in the
		# switcher and rebuild the selector.
		controllers = list(self.dm.get_controllers())
		ps0 = self.profile_switchers[0]
		first_connect = self.controller_count == 0 and count >= 1

		if count >= 1:
			active = ps0.get_controller()
			if active not in controllers:
				# No active controller yet (first connect) or the active one was
				# disconnected: fall back to the first connected controller and
				# switch the editor image to it.
				active = controllers[0]
				ps0.set_controller(active)
				self.load_gui_config_for_controller(active, first=first_connect)
		else:
			# No controllers connected, but one switcher has to stay on screen
			ps0.set_controller(None)
			self.load_gui_config_for_controller(None, first=True)

		self.rebuild_controller_selector()
		self.controller_count = count
		if count >= 1:
			# Re-arm Input Test on the (now) active controller. Without this, a
			# controller connected *after* startup is never observed -- the
			# enable at 'alive' ran while no controller was present -- so Input
			# Test stays blank until the user toggles it off and on again.
			self.enable_test_mode()

	def new_profile(self, profile: Profile, name: str) -> None:
		filename = os.path.join(get_profiles_path(), name + ".sccprofile")
		self.current_file = Gio.File.new_for_path(filename)
		self.save_profile(self.current_file, profile)
		controller = self.profile_switchers[0].get_controller()
		if controller:
			controller.set_profile(filename)
		else:
			self.dm.set_profile(filename)
		self.profile_switchers[0].set_profile(name, create=True)

	def add_switcher(self, margin_left=24, margin_right=24) -> ProfileSwitcher:
		"""Adds new profile switcher widgets on top of window. Called when new controller is connected to daemon.

		Returns generated ProfileSwitcher instance.
		"""
		vbSwitchers = self.builder.get_object("vbSwitchers")
		sepSwitchers = self.builder.get_object("sepSwitchers")

		ps = ProfileSwitcher(self.imagepath, self.config)
		ps.set_margin_left(margin_left)
		ps.set_margin_right(margin_right)
		ps.connect("right-clicked", self.on_profile_right_clicked)
		ps.connect("switch-to-clicked", self.on_switch_to_clicked)

		vbSwitchers.pack_start(ps, False, False, 0)
		vbSwitchers.reorder_child(ps, 0)
		if len(vbSwitchers.get_children()) == 2:
			# 1st switcher is bellow separator, rest is stacked on top.
			# That means separator should be moved and shown when 2nd
			# switcher is created.
			vbSwitchers.reorder_child(sepSwitchers, 0)
			sepSwitchers.set_visible(True)
		vbSwitchers.show_all()

		if len(self.profile_switchers) > 0:
			ps.set_profile_list(self.profile_switchers[0].get_profile_list())
			ps.set_switch_to_enabled(True)

		self.profile_switchers.append(ps)
		ps.connect("changed", self.on_profile_selected)
		ps.connect("unknown-profile", self.on_unknown_profile)
		return ps

	def remove_switcher(self, s):
		"""Removes given profile switcher from UI."""
		vbSwitchers = self.builder.get_object("vbSwitchers")
		sepSwitchers = self.builder.get_object("sepSwitchers")
		vbSwitchers.remove(s)
		s.destroy()
		if len(vbSwitchers.get_children()) == 2:
			sepSwitchers.set_visible(False)

	def _build_controller_selector(self):
		"""Creates the 'which controller' combo and packs it above the profile
		switcher. Hidden until 2+ controllers are connected."""
		# model columns: controller object, icon pixbuf, name, current profile
		model = Gtk.ListStore(object, GdkPixbuf.Pixbuf, str, str)
		combo = Gtk.ComboBox.new_with_model(model)
		rPix, rName, rProf = Gtk.CellRendererPixbuf(), Gtk.CellRendererText(), Gtk.CellRendererText()
		rProf.set_property("foreground", "#888888")
		combo.pack_start(rPix, False)
		combo.pack_start(rName, True)
		combo.pack_start(rProf, False)
		combo.add_attribute(rPix, "pixbuf", 1)
		combo.add_attribute(rName, "text", 2)
		combo.add_attribute(rProf, "text", 3)
		combo.set_margin_left(12)
		combo.set_margin_right(12)
		combo.set_margin_top(4)
		combo.connect("changed", self.on_controller_selected)
		combo.connect("notify::popup-shown", self._refresh_selector_profiles)
		vbSwitchers = self.builder.get_object("vbSwitchers")
		vbSwitchers.pack_start(combo, False, False, 0)
		# Layout top-to-bottom: [ selector ][ separator ][ profile switcher ]
		vbSwitchers.reorder_child(combo, 0)
		vbSwitchers.reorder_child(self.builder.get_object("sepSwitchers"), 1)
		combo.set_no_show_all(True)
		combo.set_visible(False)
		return combo

	def _load_controller_pixbuf(self, c):
		"""Loads the 24px icon for a controller, or None if unavailable."""
		try:
			iconname = self.config.get_controller_config(c.get_id()).get("icon")
			if iconname:
				path = find_controller_icon(iconname)
				if path and os.path.exists(path):
					return GdkPixbuf.Pixbuf.new_from_file_at_size(path, 24, 24)
		except Exception as e:
			log.debug("No selector icon for %s: %s", c.get_id(), e)
		return None

	def controller_display_name(self, c):
		"""Human-friendly controller name: the user's custom name if one was set
		in controller settings, otherwise a per-type label (e.g. 'Steam
		Controller v2') rather than the raw internal id (e.g. 'sc1' / '3:4')."""
		name = self.config.get_controller_config(c.get_id())["name"]
		if name and name != c.get_id():
			return name  # user-customised
		return _(CONTROLLER_TYPE_NAMES.get(c.get_type(), "Controller"))

	def rebuild_controller_selector(self):
		"""Refills the controller selector from the connected controllers and
		shows it only when more than one is connected."""
		combo = self.controller_selector
		controllers = list(self.dm.get_controllers())
		active = self.profile_switchers[0].get_controller()
		# Friendly names, disambiguating duplicates of the same type with #N
		# (e.g. two 'Steam Controller v1' become '... #1' and '... #2').
		names = [self.controller_display_name(c) for c in controllers]
		dupes = {n for n in names if names.count(n) > 1}
		seen = {}
		labels = []
		for n in names:
			if n in dupes:
				seen[n] = seen.get(n, 0) + 1
				labels.append("%s #%d" % (n, seen[n]))
			else:
				labels.append(n)
		self._selector_recursing = True
		model = combo.get_model()
		model.clear()
		active_iter = None
		for c, label in zip(controllers, labels):
			prof = get_profile_name(c.get_profile() or "") or ""
			it = model.append((c, self._load_controller_pixbuf(c), label, prof))
			if c is active:
				active_iter = it
		if active_iter is not None:
			combo.set_active_iter(active_iter)
		self._selector_recursing = False
		multi = len(controllers) >= 2
		combo.set_visible(multi)
		self.builder.get_object("sepSwitchers").set_visible(multi)

	def _refresh_selector_profiles(self, combo, *a):
		"""Refreshes each row's profile subtext when the dropdown is opened."""
		if not combo.get_property("popup-shown"):
			return
		for row in combo.get_model():
			row[3] = get_profile_name(row[0].get_profile() or "") or ""

	def on_controller_selected(self, combo):
		"""Makes the chosen controller the active (edited) one, with the same
		image transition the old switch-to button used."""
		if self._selector_recursing:
			return
		it = combo.get_active_iter()
		if it is None:
			return
		c = combo.get_model().get_value(it, 0)
		ps0 = self.profile_switchers[0]
		if c is None or c is ps0.get_controller():
			return
		ps0.set_controller(c)
		ps0.set_profile(c.get_profile())
		self.load_gui_config_for_controller(c, False)
		self.enable_test_mode()

	def enable_test_mode(self, controller: ControllerManager | None = None) -> None:
		"""Disables and re-enables Input Test mode.

		If sniffing is disabled in daemon configuration, 2nd call fails and logs error.
		"""
		if self.dm.is_alive():
			if self.test_mode_controller:
				self.test_mode_controller.unlock_all()
			if controller is None:
				try:
					controller = self.dm.get_controllers()[0]
				except IndexError:
					# Zero controllers
					return
			c = controller
			if c:
				c.unlock_all()
				c.observe(
					DaemonManager.nocallback,
					self.on_observe_failed,
					"A",
					"B",
					"C",
					"X",
					"Y",
					"START",
					"BACK",
					"LB",
					"RB",
					"LPAD",
					"RPAD",
					"LGRIP",
					"RGRIP",
					"LT",
					"RT",
					"LEFT",
					"RIGHT",
					"STICK",
					"STICKPRESS",
					# v2 (Steam Controller 2025) additions: the "..." button and
					# the capacitive handle-grip sensors (highlight by id; valid
					# SCButtons, so harmless/never-fire on controllers without them)
					"DOTS",
					"LGRIPTOUCH",
					"RGRIPTOUCH",
					# Lower back paddles (L5/R5 -> LGRIP2/RGRIP2; the upper L4/R4
					# are LGRIP/RGRIP, already above) and the right-stick click.
					"LGRIP2",
					"RGRIP2",
					"RSTICKPRESS",
					# Capacitive stick-touch sensors (Deck / SC 2025): highlight the
					# touch dot centred over each stick.
					"LSTICKTOUCH",
					"RSTICKTOUCH",
					# ...and the right stick + d-pad positions (positional axis
					# sources; never fire on controllers without them)
					"RSTICK",
					"DPAD",
				)
				self.test_mode_controller = c

	def on_observe_failed(self, error):
		log.debug("Failed to enable test mode: %s", error)

	def on_daemon_version(self, daemon, version):
		"""Checks if reported version matches expected one.
		If not, daemon is restarted.
		"""
		if version != DAEMON_VERSION and self.outdated_version != version:
			log.warning(
				"Running daemon instance is too old (version %s, expected %s). Restarting...", version, DAEMON_VERSION,
			)
			self.outdated_version = version
			self.set_daemon_status("unknown", False)
			self.dm.restart()
		# At this point, correct daemon version of daemon is running
		# and we can check if there is anything new to inform user about
		elif self.app.config["gui"]["news"]["last_version"] != App.get_release():
			if self.app.config["gui"]["news"]["enabled"]:
				self.check_release_notes()

	def on_daemon_error(self, daemon, error):
		log.debug("Daemon reported error '%s'", error)
		msg = _("There was an error with enabling emulation: <b>%s</b>") % (error,)
		# Known errors are handled with aditional message
		if "Device not found" in error:
			msg += "\n" + _("Please, check if you have receiver dongle connected to USB port.")
		elif "LIBUSB_ERROR_ACCESS" in error:
			msg += "\n" + _("You don't have access to controller device.")
			msg += "\n\n" + (
				_(
					"Consult your distribution manual, try installing Steam package or <a href='%s'>install required udev rules manually</a>.",
				)
				% "https://wiki.archlinux.org/index.php/Gamepad#Steam_Controller_not_pairing"
			)
			# TODO: Write howto somewhere instead of linking to ArchWiki
		elif "LIBUSB_ERROR_BUSY" in error:
			msg += "\n" + _("Another application (most likely Steam) is using the controller.")
		elif "CANT_SUMMON_THE_DAEMON" in error:
			msg += "\n" + _(
				'Background process responsible for emulation is not starting.\n\nTry executing "scc-daemon debug" in terminal window to check for any errors'
				"\nor <a href='https://github.com/C0rn3j/sc-controller/issues'>open issue on GitHub</a> and copy output there.",
			)
		elif "LIBUSB_ERROR_PIPE" in error:
			msg += "\n" + _("USB dongle was removed.")
		elif "Failed to create uinput device." in error:
			# Call check() method and try to determine what went wrong.
			if self.check():
				# Check() returns True if error was "handled".
				return
			# If check() fails to find error reason, error message is displayed as it is

		self.show_error(msg)
		self.set_daemon_status("error", True)

	def on_daemon_event_observer(self, daemon, c, what, data) -> None:
		# Only react to the controller Input Test is observing. Other connected
		# controllers also emit events; without this, their input would show on
		# the selected controller's image.
		if c is not self.test_mode_controller:
			return
		if what in (LEFT, RIGHT, STICK, RSTICK, DPAD):
			widget, area = {
				LEFT: (self.lpad_test, "LPADTEST"),
				RIGHT: (self.rpad_test, "RPADTEST"),
				STICK: (self.stick_test, "STICKTEST"),
				RSTICK: (self.rstick_test, "RSTICKTEST"),
				DPAD: (self.dpad_test, "DPADTEST"),
			}[what]
			# Check if stick or pad is released
			if data[0] == data[1] == 0:
				widget.hide()
				return
			# Grab values. The controller image may not define a test area for
			# this input (e.g. deck.svg has no STICKTEST); skip silently rather
			# than crashing the GUI and spamming the log with ValueError.
			try:
				ax, ay, aw, ah = self.background.get_area_position(area)
			except ValueError:
				widget.hide()
				return
			# Area coords are in SVG document space, but the cursor is a GTK
			# overlay placed in image pixels. Shift by the viewBox origin so a
			# non-zero origin (e.g. sc2.svg's "0 -45 ..." trigger headroom)
			# doesn't push every cursor up/left. Origin is (0,0) for the other
			# controllers, so they are unaffected.
			vbx, vby, _vbw, _vbh = self.background.get_viewbox()
			ax -= vbx
			ay -= vby
			if not widget.is_visible():
				widget.show()
			cw = widget.get_allocation().width
			ch = widget.get_allocation().height
			# Rest position = centre of the area on BOTH axes (the old code
			# used 'ay + 1.0' for Y, pinning the cursor to the top of the area
			# so it sat half a control too high until the stick/pad was pushed).
			x = ax + aw * 0.5 - cw * 0.5
			y = ay + ah * 0.5 - ch * 0.5
			# Add pad/stick position
			x += data[0] * aw / STICK_PAD_MAX * 0.5
			y -= data[1] * ah / STICK_PAD_MAX * 0.5
			# Move circle
			self.main_area.move(widget, x, y)
		elif what in ("LT", "RT", "STICKPRESS"):
			if data[0]:
				self.hilights[App.OBSERVE_COLOR].add(what)
			else:
				self.hilights[App.OBSERVE_COLOR].remove(what)
			self._update_background()
		elif hasattr(SCButtons, what):
			try:
				if data[0]:
					self.hilights[App.OBSERVE_COLOR].add(what)
				else:
					self.hilights[App.OBSERVE_COLOR].remove(what)
				self._update_background()
			except KeyError:
				# Non fatal
				pass
		else:
			print("event", what)

	def on_profile_right_clicked(self, ps) -> None:
		for name in ("mnuConfigureController", "mnuTurnoffController"):
			# Disable controller-related menu items if controller is not connected
			obj = self.builder.get_object(name)
			obj.set_sensitive(ps.get_controller() is not None)

		for name in (
			"mnuProfileNew",
			"mnuProfileCopy",
			"mnuProfileRename",
			"mnuProfileDetails",
			"mnuProfileSeparator1",
			"mnuProfileSeparator2",
		):
			# Hide profile-related menu items for all but 1st profile switcher
			obj = self.builder.get_object(name)
			obj.set_visible(ps == self.profile_switchers[0])

		if ps == self.profile_switchers[0]:
			name = ps.get_profile_name()
			is_override = profile_is_override(name)
			is_default = profile_is_default(name)
			self.builder.get_object("mnuProfileDelete").set_visible(not is_default)
			self.builder.get_object("mnuProfileRevert").set_visible(is_override)
			self.builder.get_object("mnuProfileRename").set_visible(not is_default)
		else:
			self.builder.get_object("mnuProfileDelete").set_visible(False)
			self.builder.get_object("mnuProfileRevert").set_visible(False)

		mnuPS = self.builder.get_object("mnuPS")
		mnuPS.ps = ps
		mnuPS.popup(None, None, None, None, 3, Gtk.get_current_event_time())

	def on_mnuConfigureController_activate(self, *a) -> None:
		from scc.gui.controller_settings import ControllerSettings

		mnuPS = self.builder.get_object("mnuPS")
		cs = ControllerSettings(self, mnuPS.ps.get_controller(), mnuPS.ps)
		cs.show(self.window)

	def on_mnuProfileNew_activate(self, *a) -> None:
		mnuPS = self.builder.get_object("mnuPS")
		self.on_new_clicked(mnuPS.ps, mnuPS.ps.get_name())

	def on_mnuProfileCopy_activate(self, *a) -> None:
		mnuPS = self.builder.get_object("mnuPS")
		rbCopyProfile = self.builder.get_object("rbCopyProfile")
		self.on_new_clicked(mnuPS.ps, mnuPS.ps.get_profile_name())
		rbCopyProfile.set_active(True)

	def on_mnuProfileDetails_activate(self, *a) -> None:
		self.builder.get_object("dlgProfileDetails").show()

	def on_mnuProfileRename_activate(self, *a) -> None:
		dlg = self.builder.get_object("dlgRenameProfile")
		txRename = self.builder.get_object("txRename")
		mnuPS = self.builder.get_object("mnuPS")
		name = mnuPS.ps.get_profile_name()
		txRename.set_text(name)
		dlg._name = name
		dlg.set_transient_for(self.window)
		dlg.show()

	def on_txRename_changed(self, tx) -> None:
		name = tx.get_text()
		btRenameProfile = self.builder.get_object("btRenameProfile")
		btRenameProfile.set_sensitive(find_profile(name) is None)

	def on_btRenameProfile_clicked(self, *a) -> None:
		dlg = self.builder.get_object("dlgRenameProfile")
		txRename = self.builder.get_object("txRename")
		old_name = dlg._name
		new_name = txRename.get_text()
		old_fname = os.path.join(get_profiles_path(), old_name + ".sccprofile")
		new_fname = os.path.join(get_profiles_path(), new_name + ".sccprofile")
		try:
			os.rename(old_fname, new_fname)
			for n in (old_fname, new_fname):
				try:
					os.unlink(n + ".mod")
				except:
					# non-existing .mod file is expected
					pass
		except Exception as e:
			log.error("Failed to rename %s: %s", old_fname, e)

		controllers = list(self.dm.get_controllers())
		for c in controllers:
			if get_profile_name(c.get_profile()) == old_name:
				c.set_profile(new_name)
				if c is self.profile_switchers[0].get_controller():
					self.profile_switchers[0].set_profile(new_name, True)
		self.load_profile_list()
		self.rebuild_controller_selector()
		dlg.hide()

	def on_mnuProfileDelete_activate(self, *a) -> None:
		mnuPS = self.builder.get_object("mnuPS")
		name = mnuPS.ps.get_profile_name()
		is_override = profile_is_override(name)

		if is_override:
			text = _("Really revert current profile to default values?")
		else:
			text = _("Really delete current profile?")

		d = Gtk.MessageDialog(
			parent=self.window,
			flags=Gtk.DialogFlags.MODAL,
			type=Gtk.MessageType.WARNING,
			buttons=Gtk.ButtonsType.OK_CANCEL,
			message_format=text,
		)
		d.format_secondary_text(_("This action is not undoable!"))

		if d.run() == -5:  # OK button, no idea where is this defined...
			fname = os.path.join(get_profiles_path(), name + ".sccprofile")
			try:
				os.unlink(fname)
				try:
					os.unlink(fname + ".mod")
				except:
					# non-existing .mod file is expected
					pass
				for ps in self.profile_switchers:
					ps.refresh_profile_path(name)
			except Exception as e:
				log.error("Failed to remove %s: %s", fname, e)
		d.destroy()

	def mnuTurnoffController_activate(self, *a) -> None:
		mnuPS = self.builder.get_object("mnuPS")
		if mnuPS.ps.get_controller():
			mnuPS.ps.get_controller().turnoff()

	def on_window_key_press_event(self, window, event) -> None:
		if (event.state & Gdk.ModifierType.CONTROL_MASK) != 0:
			if event.keyval == 115:
				self.on_save_clicked()

	def show_error(self, message, ribar=None):
		if self.ribar is None or self.ribar.get_label() is None:
			self.ribar = ribar or RIBar(message, Gtk.MessageType.ERROR)
			content = self.builder.get_object("content")
			content.pack_start(self.ribar, False, False, 0)
			content.reorder_child(self.ribar, 0)
			self.ribar.connect("close", self.hide_error)
			self.ribar.connect("response", self.hide_error)
		else:
			self.ribar.get_label().set_markup(message)
		self.ribar.show()
		self.ribar.set_reveal_child(True)
		return self.ribar

	def hide_error(self, *a):
		if self.ribar is not None:
			if self.ribar.get_parent() is not None:
				self.ribar.get_parent().remove(self.ribar)
		self.ribar = None

	def on_daemon_reconfigured(self, *a) -> None:
		log.debug("Reloading config...")
		self.config.reload()
		# If Input Test was just turned off, drop any highlights left over from
		# the last observed press (e.g. a held grip sensor): with sniffing off no
		# release event arrives to clear them, so they'd stay stuck on the image.
		if not self.config["enable_sniffing"] and self.hilights[App.OBSERVE_COLOR]:
			self.hilights[App.OBSERVE_COLOR].clear()
			self._update_background()
		for ps in self.profile_switchers:
			ps.set_controller(ps.get_controller())
		self.rebuild_controller_selector()

	def on_daemon_dead(self, *a):
		if self.just_started:
			self.dm.restart()
			self.just_started = False
			self.set_daemon_status("unknown", True)
			return

		for ps in self.profile_switchers:
			ps.set_controller(None)
			ps.on_daemon_dead()
		self._selector_recursing = True
		self.controller_selector.get_model().clear()
		self._selector_recursing = False
		self.controller_selector.set_visible(False)
		self.builder.get_object("sepSwitchers").set_visible(False)
		self.set_daemon_status("dead", False)

	def on_mnuEmulationEnabled_toggled(self, cb):
		if self.recursing:
			return
		if cb.get_active():
			# Turning daemon on
			self.set_daemon_status("unknown", True)
			cb.set_sensitive(False)
			self.dm.start()
		else:
			# Turning daemon off
			self.set_daemon_status("unknown", False)
			cb.set_sensitive(False)
			self.hide_error()
			self.dm.stop()

	def do_startup(self, *a) -> None:
		Gtk.Application.do_startup(self, *a)
		self.load_profile_list()
		self.setup_widgets()
		# No tray icon for the transient OSD-keyboard bindings editor launch.
		if self.app.config["gui"]["enable_status_icon"] and not self.osk_edit_mode:
			self.setup_statusicon()
		self.set_daemon_status("unknown", True)

	def do_local_options(self, trash, lo):
		set_logging_level(lo.contains("verbose"), lo.contains("debug"))
		# --osd opens the standalone OSD-keyboard bindings editor (do_activate) -
		# the same dialog as Settings > Menus & Keyboard > Advanced. Used on both
		# X11 and Wayland for a consistent, reliable single-window experience.
		self.osk_edit_mode = lo.contains("osd")
		return -1

	def do_command_line(self, cl):
		Gtk.Application.do_command_line(self, cl)
		if len(cl.get_arguments()) > 1:
			filename = " ".join(cl.get_arguments()[1:])  # 'cos fuck Gtk...
			from scc.gui.importexport.dialog import Dialog

			if Dialog.determine_type(filename) is not None:
				ied = Dialog(self)

				def i_told_you_to_quit(*a):
					sys.exit(0)

				ied.window.connect("destroy", i_told_you_to_quit)
				ied.show(self.window)
				# Skip first screen and try to import this file
				ied.import_file(filename)
			else:
				sys.exit(1)
		else:
			self.activate()
		return 0

	def do_activate(self, *a) -> None:
		if self.osk_edit_mode:
			# "Edit Bindings" (OSD menu): show only the OSD-keyboard bindings
			# editor, never the main window, and quit when it is closed - so it
			# can't pile up duplicate main windows.
			if not getattr(self, "_osk_editor", None):
				self.open_osk_editor()
			return
		self.builder.get_object("window").show()
		if self.config["gui"]["minimize_on_start"] and self.statusicon and self.statusicon.get_property("active"):
			self.builder.get_object("window").hide()
		else:
			self.builder.get_object("window").show()

	def open_osk_editor(self):
		"""Opens the standalone OSD-keyboard bindings editor (the same window
		reachable from Settings > Menus & Keyboard > Advanced) as the only
		window, quitting the app when it closes. Backs the OSD menu's
		'Edit Bindings' item."""
		import fcntl

		import scc.osd.osk_actions
		from scc.actions import Action
		from scc.gui.osk_binding_editor import OSKBindingEditor
		# Single-instance: each "Edit Bindings" is its own process (the app is
		# NON_UNIQUE), so without this a repeated launch would stack a second
		# editor window. Hold an exclusive lock for our lifetime; if another
		# launch already holds it, just quit instead of opening a duplicate.
		try:
			self._osk_lock = open(os.path.join(get_config_path(), ".osk-editor.lock"), "w")
			fcntl.flock(self._osk_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
		except OSError:
			log.info("OSD-keyboard bindings editor already open; not opening another")
			self.quit()
			return
		except Exception:
			log.exception("OSK editor single-instance lock failed; opening anyway")
		# The OSD-keyboard profile uses OSK.* actions; register them so the
		# editor can parse it (GlobalSettings does the same before opening it).
		Action.register_all(scc.osd.osk_actions, prefix="OSK")
		self._osk_editor = OSKBindingEditor(self)
		self._osk_editor.window.connect("destroy", lambda *a: self.quit())
		self._osk_editor.show(None)

	def remove_dot_profile(self) -> None:
		"""Checks if first profile in list begins with dot and if yes, removes it.
		This is done to undo automatic addition that is done when daemon reports
		selecting such profile.
		"""
		cb = self.builder.get_object("cbProfile")
		model = cb.get_model()
		if len(model) == 0:
			# Nothing to remove
			return
		if not model[0][0].startswith("."):
			# Not dot profile
			return
		active = model.get_path(cb.get_active_iter())
		first = model[0].path
		if active == first:
			# Can't remove active item
			return
		model.remove(model[0].iter)

	def get_current_profile(self):
		return self.profile_switchers[0].get_profile_name()

	def set_daemon_status(self, status: str, daemon_runs: bool) -> None:
		"""Updates image that shows daemon status and menu shown when image is clicked"""
		log.debug("daemon status: %s", status)
		icon = os.path.join(self.imagepath, f"scc-{status}.svg")
		imgDaemonStatus = self.builder.get_object("imgDaemonStatus")
		btDaemon = self.builder.get_object("btDaemon")
		mnuEmulationEnabled = self.builder.get_object("mnuEmulationEnabled")
		mnuEmulationEnabledTray = self.builder.get_object("mnuEmulationEnabledTray")
		imgDaemonStatus.set_from_file(icon)
		mnuEmulationEnabled.set_sensitive(True)
		mnuEmulationEnabledTray.set_sensitive(True)
		self.window.set_icon_from_file(icon)
		self.status = status
		if self.statusicon:
			GLib.idle_add(self.statusicon.set, "scc-%s" % (self.status,), _("SC Controller"))
		self.recursing = True
		if status == "alive":
			btDaemon.set_tooltip_text(_("Emulation is active"))
		elif status == "error":
			btDaemon.set_tooltip_text(_("Error enabling emulation"))
		elif status == "dead":
			btDaemon.set_tooltip_text(_("Emulation is inactive"))
		else:
			btDaemon.set_tooltip_text(_("Checking emulation status..."))
		mnuEmulationEnabled.set_active(daemon_runs)
		mnuEmulationEnabledTray.set_active(daemon_runs)
		self.recursing = False

	def on_btCloseDetails_clicked(self, *a) -> None:
		self.builder.get_object("dlgProfileDetails").hide()

	def on_buffProfileDescription_changed(self, buffer, *a) -> None:
		if self.recursing:
			return
		self.current.description = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
		self.on_profile_modified()

	def on_cbProfileIsTemplate_toggled(self, widget, *a) -> None:
		if self.recursing:
			return
		self.current.is_template = widget.get_active()
		self.on_profile_modified()

	def setup_commandline(self) -> None:
		def aso(long_name, short_name, description, arg=None, flags=GLib.OptionFlags.IN_MAIN):
			"""add_simple_option, adds program argument in simple way"""
			o = GLib.OptionEntry()
			if short_name:
				o.long_name = long_name
				o.short_name = short_name
			o.description = description
			o.flags = flags
			if arg is not None:
				o.arg = arg
			self.add_main_option_entries([o])

		self.connect("handle-local-options", self.do_local_options)

		aso("verbose", b"v", "Be verbose")
		aso("debug", b"d", "Be more verbose (debug mode)")
		aso("osd", b"o", "Open the OSD-keyboard bindings editor")

	def save_profile_selection(self, path) -> None:
		"""Saves name of profile into config file"""
		name = os.path.split(path)[-1]
		if name.endswith(".sccprofile"):
			name = name[0:-11]

		data = dict(current_profile=name)
		jstr = json.dumps(data, sort_keys=True, indent=4)

		open(os.path.join(get_config_path(), self.CONFIG), "w").write(jstr)

	def load_profile_selection(self):
		"""Returns name profile from config file or None if there is none saved"""
		try:
			return self.config["recent_profiles"][0]
		except Exception:
			return None

	@staticmethod
	def get_release(n: int = 4) -> str:
		"""Returns current version rounded to max. 'n' numbers.

		( v0.14.1.3 ; n=3 -> v0.14.1   )
		( v0.14.0.0 ; n=3 -> v0.14.0.0 )
		"""
		split = DAEMON_VERSION.split(".")[0:n]
		# Remove final zeroes ( v0.14.0.0 ; n=3 -> v0.14 ) - disabled, let's include them
		# while split[-1] == "0":
		# split = split[0:len(split) - 1]
		return ".".join(split)

	def release_notes_visible(self) -> bool:
		"""Returns True if release notes infobox is visible"""
		if not self.ribar:
			return False
		riNewRelease = self.builder.get_object("riNewRelease")
		return self.ribar._infobar == riNewRelease

	def check_release_notes(self) -> None:
		"""Silently downloads release notes from github

		displays infobar informing user that they are ready to be displayed
		"""
		url: str = App.RELEASE_URL % (App.get_release(),)
		# We're checking URLs such as https://github.com/C0rn3j/sc-controller/releases/tag/v0.6.2.dev6+gf4a040743
		if ".dev" in url:
			log.debug(f"Dev build - skipping loading release notes")
			return
		log.debug(f"Loading release notes from '{url}'")
		f = Gio.File.new_for_uri(url)
		buffer = b""

		def stream_ready(stream, task, buffer) -> None:
			try:
				bytes = stream.read_bytes_finish(task)
				if bytes.get_size() > 0:
					buffer += bytes.get_data()
					stream.read_bytes_async(102400, 0, None, stream_ready, buffer)
				else:
					self.on_got_release_notes(buffer.decode("utf-8"))
			except Exception as e:
				log.warning(f"Failed to read release notes at {url}, maybe your internet connection is down?")
				log.exception(e)
				return

		def http_ready(f, task, buffer) -> None:
			try:
				stream = f.read_finish(task)
				assert stream
				stream.read_bytes_async(102400, 0, None, stream_ready, buffer)
			except Exception:
				log.warning(f"Failed to read release notes at {url}, maybe your internet connection is down?")
				# log.exception(f"Following Traceback error is not fatal and can be ignored: {e}")
				return

		f.read_async(0, None, http_ready, buffer)

	def on_got_release_notes(self, data):
		"""Called after entire HTML page of release notes is downloaded"""
		# There is actually only one thing parsed here;
		# Sequence of words "see ... for more", in bold, containing <A> tag.
		# If such sequence is found, it's displayed with message about extended
		# release notes. Otherwise, shorter text and link to github is used.
		RE_EXTENDED = r"<strong>see.*href=\"([^\"]+).*for more.*</strong>"

		if self.ribar is not None:
			# There is already some error displayed, don't bother now...
			return

		msg = ""
		extended = re.search(RE_EXTENDED, data, re.IGNORECASE)
		if extended:
			msg += _("<a href='%s'>Click here</a> to check what's new!")
			msg = msg % (extended.group(1),)
		else:
			url = App.RELEASE_URL % (App.get_release(),)
			msg += _("Welcome to the version <b>%s</b>.")
			msg += " " + _("<a href='%s'>Click here</a> to read release notes.")
			msg = msg % (App.get_release(), url)

		infobar = self.builder.get_object("riNewRelease")
		lblNewRelease = self.builder.get_object("lblNewRelease")
		lblNewRelease.set_markup(msg)
		ribar = RIBar(None, infobar=infobar)
		ribar = self.show_error(None, ribar=ribar)
		self.ribar.connect("close", self.on_new_release_dismissed)
		self.ribar.connect("response", self.on_new_release_dismissed)

	def on_new_release_dismissed(self, *a):
		self.config["gui"]["news"]["last_version"] = App.get_release()
		self.config.save()

	def on_cbNewRelease_toggled(self, cb):
		self.app.config["gui"]["news"]["enabled"] = cb.get_active()
		self.config.save()

	def on_drag_data_received(self, widget, context, x, y, data, info, time) -> None:
		"""Drag-n-drop handler"""
		uri: str = ""
		data_type: str = str(data.get_data_type())
		log.debug("Drag and drop initiated with %s", data_type)
		if data_type == "text/uri-list":
			# Only file can be dropped here
			if len(data.get_uris()):
				uri = data.get_uris()[0]
		elif data_type == "text/plain":
			# This can be anything, so try to extract uri from it
			text_data = data.get_data()
			if isinstance(text_data, bytes):
				try:
					text = text_data.decode()
				except UnicodeDecodeError:
					log.warning("Dropped text is not valid UTF-8")
					return
				except Exception:
					log.exception("Dropped text could not be decoded")
					return
			else: # Should be string
				text = text_data

			lines: list[str] = str(text).split("\n")
			if len(lines) > 0:
				first = lines[0]
				if first.startswith(("http://", "https://")):
					uri = first
		log.debug("Parsed uri: %s", uri)
		if uri:
			from scc.gui.importexport.dialog import Dialog

			giofile = None
			if uri.startswith("file://"):
				giofile = Gio.File.new_for_uri(uri)
			else:
				# Local file can be used directly, remote has to be downloaded first
				if uri.startswith("https://github.com/"):
					# Convert link to repository display to link to raw file
					uri = uri.replace("https://github.com/", "https://raw.githubusercontent.com/").replace(
						"/blob/", "/",
					)
				name = unquote(".".join(uri.split("/")[-1].split(".")[0:-1]))
				remote = Gio.File.new_for_uri(uri)
				tmp, stream = Gio.File.new_tmp(f"{name}.XXXXXX")
				stream.close()
				if remote.copy(tmp, Gio.FileCopyFlags.OVERWRITE, None, None):
					# Sucessfully downloaded
					log.info("Downloaded '%s'", uri)
					giofile = tmp
				else:
					# Failed. Just do nothing
					log.debug("Failed downloading %s", uri)
					return
			if giofile.get_path():
				path = giofile.get_path()
				filetype = Dialog.determine_type(path)
				if filetype:
					log.info("Importing '%s'...", filetype)
					log.debug("(type %s)", filetype)
					ied = Dialog(self)
					ied.show(self.window)
					# Skip first screen and try to import this file
					ied.import_file(path, filetype=filetype)
				else:
					log.error("Unknown file type: '%s'...", path)

	def convert_old_profiles(self) -> None:
		"""Checks all available profiles and automatically converts anything with version 1.3 or lower."""
		from scc.parser import ActionParser

		to_convert = {}
		for name in os.listdir(get_profiles_path()):
			if name.endswith("~"):
				# Ignore backups - https://github.com/kozec/sc-controller/issues/440
				continue
			try:
				p = Profile(ActionParser())
				p.load(os.path.join(get_profiles_path(), name))
			except Exception:
				log.debug("Failed loading old profile %s for conversion", name)
				# Just ignore invalid profiles here
				continue
			if p.original_version < 1.4:
				to_convert[name] = p

		if to_convert:
			log.warning("Auto-converting old profile files to version 1.4. This should take only moment.")
			log.warning(
				"All files are modified in-place, but backup files are created. Feel free to remove them later.",
			)
			for name in to_convert:
				try:
					to_convert[name].save("%s/%s.convert" % (get_profiles_path(), name))
					os.rename("%s/%s" % (get_profiles_path(), name), "%s/%s~" % (get_profiles_path(), name))
					os.rename("%s/%s.convert" % (get_profiles_path(), name), "%s/%s" % (get_profiles_path(), name))
					log.warning("Converted %s (from v%s)", name, to_convert[name].original_version)
				except Exception as e:
					log.warning("Failed to convert %s: %s", name, e)


class UndoRedo:
	"""Just dummy container"""

	def __init__(self, id, before, after):
		self.id = id
		self.before = before
		self.after = after
