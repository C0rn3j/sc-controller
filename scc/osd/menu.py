"""SC-Controller - OSD Menu.

Display menu that user can navigate through and prints chosen item id to stdout
"""

import logging
import os
import sys
from math import sqrt

from gi.repository import Gdk, GdkPixbuf, GdkX11, Gio, GLib, Gtk

from scc.config import Config
from scc.constants import DEFAULT, LEFT, RIGHT, SAME, STICK, STICK_PAD_MAX, ControllerFlags, SCButtons
from scc.gui.daemon_manager import DaemonManager
from scc.lib import xwrappers as X
from scc.menu_data import MenuData, Separator, Submenu
from scc.osd import OSDWindow, StickController
from scc.paths import get_share_path
from scc.tools import _, circle_to_square, clamp, find_icon, find_menu

log = logging.getLogger("osd.menu")

# Fill MENU_GENERATORS dict


class Menu(OSDWindow):
	EPILOG = """Exit codes:
   0  - clean exit, user selected option
  -1  - clean exit, user canceled menu
  -2  - clean exit, menu closed from callback method
   1  - error, invalid arguments
   2  - error, failed to access sc-daemon, sc-daemon reported error or died while menu is displayed.
   3  - erorr, failed to lock input stick, pad or button(s)
	"""
	SUBMENU_OFFSET = 50
	PREFER_BW_ICONS = True

	def __init__(self, cls="osd-menu", layer=None):
		OSDWindow.__init__(self, cls, layer)
		self.daemon = None
		self.config = None
		self.feedback = None
		self.controller = None
		if isinstance(Gdk.Display.get_default(), GdkX11.X11Display):
			self.xdisplay = X.Display(hash(GdkX11.x11_get_default_xdisplay()))  # Magic
		else:
			self.xdisplay = None

		cursor = os.path.join(get_share_path(), "images", "menu-cursor.svg")
		self.cursor = Gtk.Image.new_from_file(cursor)
		self.cursor.set_name("osd-menu-cursor")

		self.parent = self.create_parent()
		self.f = Gtk.Fixed()
		self.f.add(self.scroll_wrap(self.parent))
		self.add(self.f)

		self._submenu = None
		self._scon = StickController()
		self._scon.connect("direction", self.on_stick_direction)
		self._is_submenu = False
		self._selected = None
		self._menuid = None
		self._use_cursor = False
		self._eh_ids = []
		# Reveal-after-lock state: the menu is not made visible until inputs are
		# locked, so a button press can't reach the normal mapping before the
		# (asynchronous) lock lands. A fallback reveals anyway if the lock is
		# slow, so the menu can never get stuck invisible.
		self._inputs_locked = False
		self._show_pending = False
		self._reveal_timer = None
		self._quit_done = False
		self._control_with = STICK
		self._control_with_dpad = False
		self._confirm_with = "A"
		self._cancel_with = "B"

	def set_is_submenu(self):
		"""Marks menu as submenu. This changes behaviour of some methods,
		especially disables (un)locking of input stick and buttons.
		"""
		self._is_submenu = True

	def create_parent(self):
		v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		v.set_name("osd-menu")
		return v

	def scroll_wrap(self, parent: Gtk.Widget) -> Gtk.Widget:
		"""Wrap the vertical item list in a scrolled viewport capped to the screen
		height, so very long menus (e.g. hundreds of profiles) don't run off-screen.
		Overridden to a no-op by grid/radial/horizontal menus."""
		sw = Gtk.ScrolledWindow()
		sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
		try:
			sw.set_shadow_type(Gtk.ShadowType.NONE)
		except Exception:
			pass
		sw.add(parent)
		self._scrollwindow = sw
		return sw

	def _max_menu_height(self) -> int:
		"""Largest the menu may grow before scrolling (monitor height minus margin)."""
		try:
			display = Gdk.Display.get_default()
			monitor = display.get_primary_monitor() or display.get_monitor(0)
			return max(240, monitor.get_geometry().height - 80)
		except Exception:
			return 720

	def _fit_scroll(self) -> None:
		"""Size the scrolled viewport to the packed items, capped to the screen.
		The item box is empty when scroll_wrap() runs and a GtkFixed won't expand
		the viewport afterwards, so the size is set here once items are present."""
		sw = getattr(self, "_scrollwindow", None)
		if sw is None:
			return
		self.parent.show_all()
		nath = self.parent.get_preferred_height()[1]
		natw = self.parent.get_preferred_width()[1]
		cap = self._max_menu_height()
		if nath > cap:
			sw.set_size_request(natw + 24, cap)
		else:
			sw.set_size_request(natw, nath)

	def _ensure_visible(self, widget: Gtk.Widget) -> None:
		"""Scroll the viewport (if any) so the selected item stays on screen."""
		sw = getattr(self, "_scrollwindow", None)
		if sw is None or widget is None:
			return
		adj = sw.get_vadjustment()
		if adj is None:
			return
		alloc = widget.get_allocation()
		page = adj.get_page_size()
		if alloc.height <= 0 or page <= 0:
			return
		val = adj.get_value()
		if alloc.y < val:
			adj.set_value(alloc.y)
		elif alloc.y + alloc.height > val + page:
			adj.set_value(alloc.y + alloc.height - page)

	def pack_items(self, parent, items):
		for item in items:
			parent.pack_start(item.widget, True, True, 0)

	def use_daemon(self, d):
		"""Allows (re)using already existing DaemonManager instance in same process.
		use_config() should be be called before parse_argumets() if this is used.
		"""
		self.daemon = d
		if not self._is_submenu:
			self._connect_handlers()
			self.on_daemon_connected(self.daemon)
		else:
			# A submenu reuses the parent menu's input lock (the parent forwards
			# events to it), so it never requests its own lock and
			# _on_inputs_locked() is never called. Treat its inputs as already
			# locked; otherwise the reveal-when-locked gate added for the
			# dead-menu fix keeps the submenu window permanently hidden (it is
			# navigable via forwarded input but never shown).
			self._inputs_locked = True

	def use_config(self, c):
		"""Allows reusing already existin Config instance in same process.
		Has to be called before parse_argumets()
		"""
		self.config = c

	def get_menuid(self):
		"""Returns ID of used menu.
		"""
		return self._menuid

	def get_selected_item_id(self):
		"""Returns ID of selected item or None if nothing is selected.
		"""
		if self._selected:
			return self._selected.id
		return None

	def _add_arguments(self):
		OSDWindow._add_arguments(self)
		self.argparser.add_argument(
			"--control-with",
			"-c",
			type=str,
			metavar="option",
			default=DEFAULT,
			choices=(DEFAULT, LEFT, RIGHT, STICK),
			help="which pad or stick should be used to navigate menu",
		)
		self.argparser.add_argument(
			"--confirm-with", type=str, metavar="button", default=DEFAULT, help="button used to confirm choice",
		)
		self.argparser.add_argument(
			"--cancel-with", type=str, metavar="button", default=DEFAULT, help="button used to cancel menu",
		)
		self.argparser.add_argument(
			"--confirm-with-release",
			action="store_true",
			help="confirm choice with button release instead of button press",
		)
		self.argparser.add_argument(
			"--cancel-with-release", action="store_true", help="cancel menu with button release instead of button press",
		)
		self.argparser.add_argument("--use-cursor", "-u", action="store_true", help="display and use cursor")
		self.argparser.add_argument("--size", type=int, help="sets prefered width or height")
		self.argparser.add_argument(
			"--feedback-amplitude",
			type=int,
			help="enables and sets power of feedback effect generated when active menu option is changed",
		)
		self.argparser.add_argument(
			"--from-profile", "-p", type=str, metavar="profile_file menu_name", help="load menu items from profile file",
		)
		self.argparser.add_argument(
			"--from-file", "-f", type=str, metavar="filename", help="load menu items from json file",
		)
		self.argparser.add_argument("--print-items", action="store_true", help="prints menu items to stdout")
		self.argparser.add_argument("items", type=str, nargs="*", metavar="id title", help="Menu items")

	@staticmethod
	def _get_on_screen_position(w):
		a = w.get_allocation()
		parent = w.get_parent()
		if parent:
			if isinstance(parent, Menu) and parent.get_window() is not None:
				x, y = parent.get_window().get_position()
			else:
				x, y = Menu._get_on_screen_position(parent)
			return a.x + x, a.y + y
		return a.x, a.y

	def parse_menu(self):
		if self.args.from_profile:
			try:
				self._menuid = self.args.items[0]
				self.items = MenuData.from_profile(self.args.from_profile, self._menuid)
			except OSError:
				print("%s: error: profile file not found" % (sys.argv[0]), file=sys.stderr)
				return False
			except ValueError:
				print("%s: error: menu not found" % (sys.argv[0]), file=sys.stderr)
				return False
		elif self.args.from_file:
			try:
				self._menuid = self.args.from_file
				self.items = MenuData.from_file(self.args.from_file)
			except:
				print("%s: error: failed to load menu file" % (sys.argv[0]), file=sys.stderr)
				return False
		else:
			try:
				self.items = MenuData.from_args(self.args.items)
				self._menuid = None
			except ValueError:
				print("%s: error: invalid number of arguments" % (sys.argv[0]), file=sys.stderr)
				return False
		return True

	def parse_argumets(self, argv):
		if not OSDWindow.parse_argumets(self, argv):
			return False
		if not self.parse_menu():
			return False
		if not self.config:
			self.config = Config()

		# Parse simpler arguments
		self._size = self.args.size

		# Create buttons that are displayed on screen
		items = self.items.generate(self)
		self.items = []
		for item in items:
			item.widget = self.generate_widget(item)
			if item.widget is not None:
				self.items.append(item)
		self.pack_items(self.parent, self.items)
		if len(self.items) == 0:
			print("%s: error: no items in menu" % (sys.argv[0]), file=sys.stderr)
			return False

		if self.args.print_items:
			max_id_len = max(*[len(x.id) for x in self.items])
			row_format = "{:>%s}:\t{}" % (max_id_len,)
			for item in self.items:
				print(row_format.format(item.id, item.label))
		return True

	def enable_cursor(self):
		if not self._use_cursor:
			self.f.add(self.cursor)
			self.f.show_all()
			self._use_cursor = True

	def generate_widget(self, item):
		"""Generates gtk widget for specified menutitem"""
		if isinstance(item, Separator) and item.label:
			widget = Gtk.Button.new_with_label(item.label)
			widget.set_relief(Gtk.ReliefStyle.NONE)
			widget.set_name("osd-menu-separator")
			return widget
		if isinstance(item, Separator):
			widget = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
			widget.set_name("osd-menu-separator")
			return widget
		widget = Gtk.Button.new_with_label(item.label)
		widget.set_relief(Gtk.ReliefStyle.NONE)
		if hasattr(widget.get_children()[0], "set_xalign"):
			widget.get_children()[0].set_xalign(0)
		else:
			widget.get_children()[0].set_halign(Gtk.Align.START)
		if isinstance(item, Submenu):
			item.callback = self.show_submenu
			label1 = widget.get_children()[0]
			label2 = Gtk.Label(_(">>"))
			label2.set_property("margin-left", 30)
			box = Gtk.Box(Gtk.Orientation.HORIZONTAL)
			widget.remove(label1)
			box.pack_start(label1, True, True, 1)
			box.pack_start(label2, False, True, 1)
			widget.add(box)
			widget.set_name("osd-menu-item")
		elif item.id is None:
			widget.set_name("osd-menu-dummy")
		else:
			widget.set_name("osd-menu-item")

		if isinstance(item.icon, Gio.FileIcon):
			icon_file = item.icon.get_file().get_path()
			has_colors = True
		elif isinstance(item.icon, Gio.ThemedIcon):
			icon = Gtk.IconTheme.get_default().choose_icon(item.icon.get_names(), 64, 0)
			icon_file = icon.get_filename() if icon else None
			has_colors = True
		else:
			icon_file, has_colors = find_icon(item.icon, self.PREFER_BW_ICONS)

		if icon_file:
			icon = MenuIcon(icon_file, has_colors)
			label = widget.get_children()[0]
			for c in [] + widget.get_children():
				widget.remove(c)
			box = Gtk.Box()
			box.pack_start(icon, False, True, 0)
			box.pack_start(label, True, True, 10)
			widget.add(box)

		return widget

	def select(self, index):
		if self._selected:
			self._selected.widget.set_name(self._selected.widget.get_name().replace("-selected", ""))
		if self.items[index].id:
			if self._selected != self.items[index]:
				if self.feedback and self.controller:
					self.controller.feedback(*self.feedback)
			self._selected = self.items[index]
			self._selected.widget.set_name(self._selected.widget.get_name() + "-selected")
			self._ensure_visible(self._selected.widget)
			GLib.timeout_add(2, self._check_on_screen_position)
			return True
		return False

	def _check_on_screen_position(self, quick=False):
		if self.using_wlroots:
			return
		x, y = Menu._get_on_screen_position(self._selected.widget)
		try:
			m = self.get_window().get_display().get_monitor_at_window(self.get_window())
			assert m
			y_offset = m.get_geometry().y
			screen_height = m.get_geometry().height
		except:
			y_offset = 0
			screen_height = self.get_window().get_screen().get_height()
		y -= y_offset
		if y < 50:
			wx, wy = self.get_window().get_position()
			if quick:
				wy = 50 - (y - wy)
			else:
				wy += 5
				GLib.timeout_add(2, self._check_on_screen_position)
			self.get_window().move(wx, wy)
		if y > screen_height - 100:
			wx, wy = self.get_window().get_position()
			if quick:
				wy = screen_height - 100 - (y - wy)
			else:
				wy -= 5
				GLib.timeout_add(2, self._check_on_screen_position)
			self.get_window().move(wx, wy)

	def _connect_handlers(self):
		self._eh_ids += [
			(self.daemon, self.daemon.connect("dead", self.on_daemon_died)),
			(self.daemon, self.daemon.connect("error", self.on_daemon_died)),
			(self.daemon, self.daemon.connect("alive", self.on_daemon_connected)),
		]

	def run(self):
		self.daemon = DaemonManager()
		self._connect_handlers()
		OSDWindow.run(self)

	def show(self, *a):
		if not self.select(0):
			self.next_item(1)
		self._fit_scroll()
		# Reveal only once inputs are locked, so a button press can never reach
		# the normal mapping before the lock lands. That matters for more than a
		# stray keystroke: if the press is handled by the old action (e.g. a key
		# goes DOWN) and the release is then captured by the menu, the key never
		# goes UP and gets stuck. So we must never show the menu while unlocked:
		# if the lock does not land within the timeout, give up and CLOSE the
		# menu rather than revealing it.
		self._show_pending = True
		if self._reveal_timer is None:
			self._reveal_timer = GLib.timeout_add(2000, self._lock_timed_out)
		self._reveal_if_locked()

	def _on_inputs_locked(self, *a: object) -> None:
		"""Called from the lock-success callback, once inputs are diverted to
		this menu and it is safe to reveal it."""
		self._inputs_locked = True
		self._reveal_if_locked()

	def _reveal_if_locked(self) -> None:
		"""Reveal the menu, but only once it is both requested and locked."""
		if not (self._show_pending and self._inputs_locked):
			return
		self._show_pending = False
		if self._reveal_timer is not None:
			GLib.source_remove(self._reveal_timer)
			self._reveal_timer = None
		OSDWindow.show(self)
		GLib.timeout_add(1, self._check_on_screen_position, True)

	def _lock_timed_out(self, *a: object) -> None:
		"""The lock never landed; close the menu instead of revealing it while
		unlocked (which could leak input or strand a key)."""
		self._reveal_timer = None
		if self._show_pending:
			self._show_pending = False
			self.quit(3)
		return False

	def on_daemon_connected(self, *a):
		if not self.config:
			self.config = Config()
		self.controller = self.choose_controller(self.daemon)
		if self.controller is None or not self.controller.is_connected():
			# There is no controller connected to daemon
			self.on_failed_to_lock("Controller not connected")
			return
		self.use_controller(self.controller)

		self._eh_ids += [
			(self.controller, self.controller.connect("event", self.on_event)),
			(self.controller, self.controller.connect("lost", self.on_controller_lost)),
		]
		self.lock_inputs()

	def use_controller(self, controller):
		ccfg = self.config.get_controller_config(controller.get_id())
		self._control_with = getattr(self.args, "control_with", DEFAULT)
		self._cancel_with = getattr(self.args, "cancel_with", DEFAULT)
		if self._control_with == DEFAULT:
			self._control_with = ccfg["menu_control"]
		if self._cancel_with == DEFAULT:
			self._cancel_with = ccfg["menu_cancel"]

		self._confirm_with = getattr(self.args, "confirm_with", DEFAULT)
		if self._confirm_with == DEFAULT:
			self._confirm_with = ccfg["menu_confirm"]
		elif self._confirm_with == SAME:
			if self._control_with == RIGHT:
				self._confirm_with = SCButtons.RPADTOUCH.name
			else:
				self._confirm_with = SCButtons.LPADTOUCH.name

		if getattr(self.args, "use_cursor", False):
			# As special case, using LEFT pad on controller with
			# actual DPAD should not display cursor
			if self._control_with != LEFT or (controller.get_flags() & ControllerFlags.HAS_DPAD) == 0:
				self.enable_cursor()

		if getattr(self.args, "feedback_amplitude", None):
			side = "LEFT"
			if self._control_with == "RIGHT":
				side = "RIGHT"
			elif self._control_with == "STICK":
				side = "BOTH"
			self.feedback = side, int(self.args.feedback_amplitude)

	def lock_inputs(self):
		def success(*a):
			self._on_inputs_locked()

		locks = [self._control_with, self._confirm_with, self._cancel_with]
		if self._control_with == "STICK":
			if self.controller.get_flags() & ControllerFlags.HAS_DPAD != 0:
				self._control_with_dpad = True
				locks += ["LEFT"]
		self.controller.lock(success, self.on_failed_to_lock, *locks)

	def quit(self, code=-2):
		# A menu must unlock exactly once. quit() can be re-entered — most
		# importantly by a *previous* menu's leftover timeout firing after this
		# object should be gone — and unlock_all() is per-CLIENT: it clears every
		# lock the OSD daemon holds, not just this menu's. Re-running it would
		# strip the locks of whatever menu is open *now*, leaving it visible but
		# dead (it stops responding and leaks input to the normal mapping). So
		# make quit idempotent: a menu that already quit never unlocks again.
		if self._quit_done:
			return
		self._quit_done = True
		if self._reveal_timer is not None:
			GLib.source_remove(self._reveal_timer)
			self._reveal_timer = None
		if not self._is_submenu:
			if self.get_controller():
				self.get_controller().unlock_all()
			for source, eid in self._eh_ids:
				source.disconnect(eid)
			self._eh_ids = []
		OSDWindow.quit(self, code)

	def next_item(self, direction):
		"""Selects next menu item, based on self._direction"""
		start, i = -1, 0
		try:
			start = self.items.index(self._selected)
			i = start + direction
		except:
			pass
		while True:
			if i == start:
				# Cannot find valid menu item
				self.select(start)
				break
			if i >= len(self.items):
				i = 0
				GLib.timeout_add(1, self._check_on_screen_position, True)
				continue
			if i < 0:
				i = len(self.items) - 1
				GLib.timeout_add(1, self._check_on_screen_position, True)
				continue
			if self.select(i):
				# Not a separator
				break
			i += direction
			start = max(start, 0)

	def on_submenu_closed(self, *a):
		self.set_name("osd-menu")
		if self._submenu.get_exit_code() in (0, -2):
			self._menuid = self._submenu._menuid
			self._selected = self._submenu._selected
			self.quit(self._submenu.get_exit_code())
		self._submenu = None
		if self.using_wlroots:
			self.layer_shell.set_layer(self, self.layer_shell.Layer.OVERLAY)

	def show_submenu(self, trash, trash2, trash3, menuitem):
		"""Called when user chooses menu item pointing to submenu"""
		filename = find_menu(menuitem.filename)
		if filename:
			layer = None
			if self.using_wlroots:
				if self.layer_shell.is_supported():
					layer = self.layer_shell.Layer.OVERLAY
					self.layer_shell.set_layer(self, self.layer_shell.Layer.TOP)
			self._submenu = self.__class__(layer=layer)
			sub_pos = list(self.position)
			for i in (0, 1):
				sub_pos[i] = sub_pos[i] - self.SUBMENU_OFFSET if sub_pos[i] < 0 else sub_pos[i] + self.SUBMENU_OFFSET

			self._submenu.use_config(self.config)
			self._submenu.parse_argumets(
				[
					"menu.py",
					"-x",
					str(sub_pos[0]),
					"-y",
					str(sub_pos[1]),
					"--from-file",
					filename,
					"--control-with",
					self._control_with,
					"--confirm-with",
					self._confirm_with,
					"--cancel-with",
					self._cancel_with,
				],
			)
			self._submenu.set_is_submenu()
			self._submenu.use_daemon(self.daemon)
			self._submenu.use_controller(self.controller)
			self._submenu.controller = self.controller
			self._submenu.connect("destroy", self.on_submenu_closed)
			self._submenu.show()
			self.set_name("osd-menu-inactive")

	def _control_equals_cancel(self, daemon, x, y):
		"""Called by on_event in that very special case when both confirm_with
		and cancel_with are set to STICK.

		Separated because RadialMenu overrides on_event and still
		needs to call this.

		Returns True if menu was canceled.
		"""
		distance = sqrt(x * x + y * y)
		if distance < STICK_PAD_MAX / 8:
			self.quit(-1)
			return True
		return False

	def on_stick_direction(self, trash, x, y):
		if y != 0:
			self.next_item(y)

	def on_event(self, daemon, what, data):
		if self._submenu:
			return self._submenu.on_event(daemon, what, data)
		if what == self._control_with or (what == "LEFT" and self._control_with_dpad):
			x, y = data
			if self._use_cursor:
				# Special case, both confirm_with and cancel_with
				# can be set to STICK
				if self._cancel_with == STICK and self._control_with == STICK:
					if self._control_equals_cancel(daemon, x, y):
						return None

				pad_w = self.cursor.get_allocation().width * 0.5
				pad_h = self.cursor.get_allocation().height * 0.5
				max_w = self.get_allocation().width - 2 * pad_w
				max_h = self.get_allocation().height - 2 * pad_h

				x, y = circle_to_square(x / (STICK_PAD_MAX * 2.0), y / (STICK_PAD_MAX * 2.0))
				x = clamp(pad_w, (pad_w + max_w) * 0.5 + x * max_w, max_w - pad_w)
				y = clamp(pad_h, (pad_h + max_h) * 0.5 + y * max_h * -1, max_h - pad_h)
				self.f.move(self.cursor, int(x), int(y))

				# for i in self.items:
				# if point_in_gtkrect(i.widget.get_allocation(), x, y):
				# self.select(self.items.index(i))
			else:
				self._scon.set_stick(x, y)
		elif what == self._confirm_with:
			if data[0] == 0:  # Button released
				if self._selected and self._selected.callback:
					self._selected.callback(self, self.daemon, self.controller, self._selected)
				elif self._selected:
					self.quit(0)
				else:
					self.quit(-1)
		elif what == self._cancel_with:
			if data[0] == 0:  # Button released
				self.quit(-1)


class MenuIcon(Gtk.DrawingArea):
	"""Auti-sized, auto-recolored icon for menus"""

	def __init__(self, filename, has_colors=False):
		Gtk.DrawingArea.__init__(self)
		self.connect("size_allocate", self.on_size_allocate)
		self.has_colors = has_colors
		self.set_filename(filename)

	def set_filename(self, filename):
		if filename is None:
			self.pb = None
		else:
			self.pb = GdkPixbuf.Pixbuf.new_from_file(filename)

	def on_size_allocate(self, trash, allocation):
		if allocation.width < allocation.height:
			self.set_size_request(allocation.height, -1)

	def do_draw(self, cr):
		allocation = self.get_allocation()
		if allocation.width >= allocation.height:
			context = Gtk.Widget.get_style_context(self)
			Gtk.render_background(context, cr, 0, 0, allocation.width, allocation.height)
			if self.pb is None:
				# No icon set
				return
			scaled = self.pb.scale_simple(allocation.height, allocation.height, GdkPixbuf.InterpType.BILINEAR)
			surf = Gdk.cairo_surface_create_from_pixbuf(scaled, 1)
			if self.has_colors:
				cr.set_source_surface(surf, 1.0, 1.0)
				# allocation.height, allocation.height)
				cr.rectangle(0, 0, allocation.height, allocation.height)
			else:
				Gdk.cairo_set_source_rgba(cr, context.get_color(Gtk.StateFlags.NORMAL))
				cr.mask_surface(surf, 0, 0)
			cr.fill()
