"""SC-Controller - OSD.

Common methods for OSD-related stuff
"""
import argparse
import logging
import os
import traceback
import cairo

import gi
gi.require_version("Gtk",    "3.0")
gi.require_version("Gdk",    "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gdk, GLib, GObject, Gtk

from scc.config import Config
from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN
from scc.controller import Controller
from scc.gui.daemon_manager import DaemonManager
from scc.osd.timermanager import TimerManager
from scc.paths import get_share_path
from scc.tools import set_logging_level

log = logging.getLogger("osd")


class OSDWindow(Gtk.Window):
	# TODO: Get rid of CSS_3_20, maybe just by dropping support
	CSS_3_20 = """
		#osd-menu-item-big-icon, #osd-menu-item-big-icon-selected {
			min-width: 48pt;
			min-height: 48pt;
		}

		#osd-dialog-buttons #osd-menu-item,
		#osd-dialog-buttons #osd-menu-item-selected {
			min-width: 100px;
			margin: 0px 5px 0px 5px;
		}
	"""

	EPILOG = ""
	css_provider = None # Used by staticmethods

	def __init__(self, wmclass, layer = None) -> None:
		Gtk.Window.__init__(self)
		OSDWindow._apply_css(Config())

		self.argparser = argparse.ArgumentParser(description=__doc__,
			formatter_class=argparse.RawDescriptionHelpFormatter,
			epilog=self.EPILOG)
		self._add_arguments()
		self.exit_code = -1
		self.position = (20, -20)
		self.mainloop = None
		self._controller = None
		self.set_name(wmclass)
		self.set_wmclass(wmclass, wmclass)
		self.using_wlroots = False
		try:
			import gi
			gi.require_version("GtkLayerShell", "0.1")
			from gi.repository import GtkLayerShell
			if GtkLayerShell.is_supported():
				self.using_wlroots=True
				self.x_layer_anchor = GtkLayerShell.Edge.LEFT
				self.y_layer_anchor = GtkLayerShell.Edge.BOTTOM
				GtkLayerShell.init_for_window(self)
				GtkLayerShell.set_layer(self, layer if layer is not None else GtkLayerShell.Layer.TOP)
				GtkLayerShell.set_anchor(self, self.x_layer_anchor, True)
				GtkLayerShell.set_anchor(self, self.y_layer_anchor, True)
				self.layer_shell = GtkLayerShell
		except (ImportError):
			pass
		if not self.using_wlroots:
			self.set_decorated(False)
			self.stick()
			self.set_skip_taskbar_hint(True)
			self.set_skip_pager_hint(True)
			self.set_keep_above(True)
			self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)


	@staticmethod
	def _apply_css(config: dict) -> None:
		if OSDWindow.css_provider:
			Gtk.StyleContext.remove_provider_for_screen(
				Gdk.Screen.get_default(), OSDWindow.css_provider)

		colors = {}
		for x in config['osk_colors'] : colors["osk_%s" % (x,)] = config['osk_colors'][x]
		for x in config['osd_colors'] : colors[x] = config['osd_colors'][x]
		colors = OSDCssMagic(colors)
		try:
			css_file = os.path.join(get_share_path(), "osd-styles", config["osd_style"])
			with open(css_file, "r") as file:
				css = file.read()
			if ((Gtk.get_major_version(), Gtk.get_minor_version()) > (3, 20)):
				css += OSDWindow.CSS_3_20
			OSDWindow.css_provider = Gtk.CssProvider()
			OSDWindow.css_provider.load_from_data((css % colors).encode("utf-8"))
			Gtk.StyleContext.add_provider_for_screen(
					Gdk.Screen.get_default(),
					OSDWindow.css_provider,
					Gtk.STYLE_PROVIDER_PRIORITY_USER)
		except GLib.Error as e:
			log.error("Failed to apply css with user settings:")
			log.error(e)
			log.error("Retrying with default values")

			OSDWindow.css_provider = Gtk.CssProvider()
			css_file = os.path.join(get_share_path(), "osd-styles", "Classic.gtkstyle.css")
			with open(css_file, "r") as file:
				css = file.read()
			if ((Gtk.get_major_version(), Gtk.get_minor_version()) > (3, 20)):
				css += OSDWindow.CSS_3_20
			OSDWindow.css_provider.load_from_data((css % colors).encode("utf-8"))
			Gtk.StyleContext.add_provider_for_screen(
					Gdk.Screen.get_default(),
					OSDWindow.css_provider,
					Gtk.STYLE_PROVIDER_PRIORITY_USER)


	def _add_arguments(self) -> None:
		"""Should be overriden AND called by child class."""
		self.argparser.add_argument('-x', type=int, metavar="pixels", default=20,
			help="""horizontal position in pixels, from left side of screen.
			Use negative value to specify as distance from right side (default: 20)""")
		self.argparser.add_argument('-y', type=int, metavar="pixels", default=-20,
			help="""vertical position in pixels, from top side of screen.
			Use negative value to specify as distance from bottom side (default: -20)""")
		self.argparser.add_argument('--controller', type=str,
			help="""id of controller to use""")
		self.argparser.add_argument('-d', action='store_true',
			help="""display debug messages""")


	def choose_controller(self, daemonmanager: DaemonManager) -> Controller:
		"""Return first available controller, or, if --controller argument was specified, controller with a matching ID."""
		if self.args.controller:
			self._controller = self.daemon.get_controller(self.args.controller)
		elif self.daemon.has_controller():
			self._controller = self.daemon.get_controllers()[0]
		return self._controller


	def get_controller(self) -> Controller:
		"""Return controller chosen by choose_controller."""
		return self._controller


	def parse_argumets(self, argv) -> bool:
		"""Returns True on success."""
		try:
			self.args = self.argparser.parse_args(argv[1:])
		except SystemExit:
			return False
		except BaseException as e:	# Includes SystemExit
			log.error(traceback.format_exc())
			return False
		del self.argparser
		self.position = (self.args.x, self.args.y)
		if self.args.d:
			set_logging_level(True, True)
		return True


	def make_window_clicktrough(self):
		(width, height) = self.get_size()
		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
		surface_ctx = cairo.Context(surface)
		surface_ctx.set_source_rgba(0.0, 0.0, 0.0, 0.0)
		surface_ctx.set_operator(cairo.OPERATOR_SOURCE)
		surface_ctx.paint()
		reg = Gdk.cairo_region_create_from_surface(surface)
		self.input_shape_combine_region(reg)



	def get_active_screen_geometry(self):
		"""Return geometry of active screen or None if active screen cannot be determined."""
		screen = self.get_window().get_screen()
		active_window = screen.get_active_window()
		if active_window:
			monitor = screen.get_monitor_at_window(active_window)
			if monitor is not None:
				return screen.get_monitor_geometry(monitor)
		return None


	def compute_position(self):
		"""Adjust position for currently active screen (display)."""
		x, y = self.position
		width, height = self.get_window_size()
		geometry = self.get_active_screen_geometry()
		if geometry:
			if x < 0:
				x = x + geometry.x + geometry.width - width
			else:
				x = x + geometry.x
			if y < 0:
				y = y + geometry.y + geometry.height - height
			else:
				y = geometry.y + y

		return x, y


	def get_window_size(self):
		return self.get_window().get_width(), self.get_window().get_height()


	def show(self) -> None:
		self.get_children()[0].show_all()
		self.realize()
		self.get_window().set_override_redirect(True)

		x, y = self.compute_position()
		if self.using_wlroots:
			if x < 0:
				self.layer_shell.set_anchor(self, self.x_layer_anchor, False)
				self.x_layer_anchor = self.layer_shell.Edge.RIGHT
				self.layer_shell.set_anchor(self, self.x_layer_anchor, True)
				x = -x
			if y < 0:
				self.layer_shell.set_anchor(self, self.y_layer_anchor, False)
				self.y_layer_anchor = self.layer_shell.Edge.BOTTOM
				self.layer_shell.set_anchor(self, self.y_layer_anchor, True)
				y = -y
			self.layer_shell.set_margin(self, self.x_layer_anchor, x)
			self.layer_shell.set_margin(self, self.y_layer_anchor, y)
		else: # X11
			if x < 0:	# Negative X position is counted from right border
				x = Gdk.Screen.width() - self.get_allocated_width() + x + 1
			if y < 0:	# Negative Y position is counted from bottom border
				y = Gdk.Screen.height() - self.get_allocated_height() + y + 1
			self.move(x, y)

		Gtk.Window.show(self)
		self.make_window_clicktrough()


	def on_controller_lost(self, *a) -> None:
		log.error("Controller lost")
		self.quit(2)


	def on_daemon_died(self, *a) -> None:
		log.error("Daemon died")
		self.quit(2)


	def on_failed_to_lock(self, error: str) -> None:
		log.error("Failed to lock input: %s", error)
		self.quit(3)


	def get_exit_code(self) -> int:
		return self.exit_code


	def run(self) -> None:
		self.mainloop = GLib.MainLoop()
		self.show()
		self.mainloop.run()


	def quit(self, code: int = -1) -> None:
		self.exit_code = code
		if self.mainloop:
			self.mainloop.quit()
		else:
			self.destroy()


class OSDCssMagic(dict):
	"""Basically, I reinvented templating.

	This is passed to string.format, allowing to use some simple expressions in
	addition to normal %(placeholder)s.

	Supported magic:
		%(background)s			- just color
		%(background+10)s		- color, 10 values brighter
		%(background-10)s		- color, 10 values darker
	"""

	def __init__(self, dict_to_wrap) -> None:
		self._dict = dict_to_wrap


	def __getitem__(self, a) -> str:
		if "+" in a:
			key, number = a.rsplit("+", 1)
			rgba = parse_rgba(self[key])
			number = float(number) / 255.0
			rgba.red = min(1.0, rgba.red + number)
			rgba.green = min(1.0, rgba.green + number)
			rgba.blue = min(1.0, rgba.blue + number)
			return "%s%s%s" % (
				hex(int(rgba.red * 255)).split("x")[-1].zfill(2),
				hex(int(rgba.green * 255)).split("x")[-1].zfill(2),
				hex(int(rgba.blue * 255)).split("x")[-1].zfill(2))
		elif "-" in a:
			key, number = a.rsplit("-", 1)
			rgba = parse_rgba(self[key])
			number = float(number) / 255.0
			rgba.red = max(0.0, rgba.red - number)
			rgba.green = max(0.0, rgba.green - number)
			rgba.blue = max(0.0, rgba.blue - number)
			return "%s%s%s" % (
				hex(int(rgba.red * 255)).split("x")[-1].zfill(2),
				hex(int(rgba.green * 255)).split("x")[-1].zfill(2),
				hex(int(rgba.blue * 255)).split("x")[-1].zfill(2))
		return self._dict[a]


class StickController(GObject.GObject, TimerManager):
	"""Simple utility class that gets fed by with position and emits 'direction' signal that can be used as input for menu navigation.

	Signals:
		direction(horisontal, vertical)

		Both values are one of -1, 0, 1 for left/none/right.
	"""

	__gsignals__ = {
		"direction": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
	}
	REPEAT_DELAY = 0.2
	DIRECTION_TO_XY = {
		0: (0, 0),
		4: (1, 0),
		6: (-1, 0),
		2: (0, 1),
		8: (0, -1),
	}

	def __init__(self):
		GObject.GObject.__init__(self)
		TimerManager.__init__(self)
		self._direction = 0


	def _move(self, *a):
		self.emit("direction", *self.DIRECTION_TO_XY[self._direction])
		if self._direction != 0:
			self.timer("move", self.REPEAT_DELAY, self._move)
		else:
			self.cancel_timer("move")


	def set_stick(self, *data):
		direction = 0
		# Y
		if data[1] < STICK_PAD_MIN / 2:
			direction = 2
		elif data[1] > STICK_PAD_MAX / 2:
			direction = 8
		# X
		elif data[0] < STICK_PAD_MIN / 2:
			direction = 4
		elif data[0] > STICK_PAD_MAX / 2:
			direction = 6

		if direction != self._direction:
			self._direction = direction
			self._move()


def parse_rgba(col: str) -> Gdk.RGBA:
	"""Parse color specified by a #RRGGBBAA string.

	'#' and 'AA' is optional.
	"""
	# Because GTK can parse everything but theese :(
	alpha = "FF"
	if not col.startswith("#"):
		col = "#" + col
	if len(col) > 7:
		col, alpha = col[0:7], col[7:]
	rgba = Gdk.RGBA()
	if not rgba.parse(col):
		log.warning("Failed to parse RGBA color: %s", col)
	rgba.alpha = float(int(alpha, 16)) / 255.0
	return rgba
