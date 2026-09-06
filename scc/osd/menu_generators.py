"""SC-Controller - OSD Menu Generators

Auto-generated menus with stuff like list of all available profiles...
"""

import logging
import os
import traceback
from ctypes import POINTER, cast

from gi.repository import Gdk, GdkX11, Gio

from scc.lib import xwrappers as X
from scc.menu_data import MENU_GENERATORS, MenuGenerator, MenuItem
from scc.paths import get_default_profiles_path, get_profiles_path
from scc.tools import _, find_profile

log = logging.getLogger("osd.menu_gen")


class ProfileListMenuGenerator(MenuGenerator):
	"""Generates list of all available profiles"""

	GENERATOR_NAME = "profiles"

	@staticmethod
	def callback(menu, daemon, controller, menuitem) -> None:
		controller.set_profile(menuitem.filename)
		menu.hide()

		def on_response(*a) -> None:
			menu.quit(-2)

		daemon.request(b"OSD: " + menuitem.label.encode("utf-8") + b"\n", on_response, on_response)

	def describe(self):
		return _("[ All Profiles ]")

	def generate(self, menuhandler) -> list[MenuItem]:
		# TODO: Cannot load directory content asynchronously here and I'm
		# TODO: not happy about it
		rv, all_profiles = [], {}
		for d in (get_default_profiles_path(), get_profiles_path()):
			for x in os.listdir(d):
				if x.endswith(".sccprofile") and not x.startswith("."):
					all_profiles[x] = os.path.join(d, x)
		for p in sorted(all_profiles, key=lambda s: s.lower()):
			menuitem = MenuItem("generated", p[0:-11])  # strips ".sccprofile"
			menuitem.filename = all_profiles[p]
			menuitem.callback = self.callback
			rv.append(menuitem)
		return rv


class RecentListMenuGenerator(MenuGenerator):
	"""Generates list of X recently used profiles"""

	GENERATOR_NAME = "recent"

	def __init__(self, rows: int = 5, **b) -> None:
		MenuGenerator.__init__(self)
		self.rows = rows

	def generate(self, menuhandler):
		return _("[ %s Recent Profiles ]") % (self.rows,)

	def encode(self) -> dict[str, str | int]:
		return {"generator": self.GENERATOR_NAME, "rows": self.rows}

	def callback(self, menu, daemon, controller, menuitem) -> None:
		controller.set_profile(menuitem.filename)
		menu.hide()

		def on_response(*a) -> None:
			menu.quit(-2)

		daemon.request(b"OSD: " + menuitem.label.encode("utf-8") + b"\n", on_response, on_response)

	def generate(self, menuhandler) -> list[MenuItem]:
		rv = []
		for p in menuhandler.config["recent_profiles"]:
			filename = find_profile(p)
			if filename:
				menuitem = MenuItem("generated", p)
				menuitem.filename = filename
				menuitem.callback = ProfileListMenuGenerator.callback
				rv.append(menuitem)
			if len(rv) >= self.rows:
				break
		return rv


class WindowListMenuGenerator(MenuGenerator):
	"""Generates list of all windows for the Switch To feature

	Switch To gives a list of application Windows and offers to focus them
	"""

	GENERATOR_NAME = "windowlist"
	MAX_LENGHT = 50

	# def generate(self, menuhandler):
	# return _("[ Window Lists ]")

	def encode(self) -> dict[str, str]:
		return {"generator": self.GENERATOR_NAME}

	@staticmethod
	def callback(menu, daemon, controller, menuitem) -> None:
		# Below is X11 path
		try:
			xid = int(menuitem.id)
			display = Gdk.Display.get_default()
			window = GdkX11.X11Window.foreign_new_for_display(display, xid)
			window.focus(0)
		except Exception:
			log.error("Failed to activate window")
			log.error(traceback.format_exc())
		menu.quit(-2)

	def generate(self, menuhandler) -> list[MenuItem]:
		rv: list[MenuItem] = []
		x11_dpy = None
		if isinstance(Gdk.Display.get_default(), GdkX11.X11Display):
			from scc.x11 import get_xdisplay

			x11_dpy = get_xdisplay()
		if x11_dpy is not None:
			root = X.get_default_root_window(x11_dpy)

			count, wlist = X.get_window_prop(x11_dpy, root, b"_NET_CLIENT_LIST", 1024)
			skip_taskbar = X.intern_atom(x11_dpy, b"_NET_WM_STATE_SKIP_TASKBAR", True)
			wlist = cast(wlist, POINTER(X.XID))[0:count]
			for win in wlist:
				if skip_taskbar not in X.get_wm_state(x11_dpy, win):
					title = X.get_window_title(x11_dpy, win)[0 : self.MAX_LENGHT]
					menuitem = MenuItem(str(win), title)
					menuitem.callback = WindowListMenuGenerator.callback
					rv.append(menuitem)
			return rv
		# Wayland generator - seems like it needs to be compositor specific - kwin has a scripting API we can use
		rv.append(MenuItem(None, _("Switch To is not currently supported in Wayland")))
		return rv


class GameListMenuGenerator(MenuGenerator):
	"""Generates list of applications known to XDG menu and belonging to 'Game' category"""

	GENERATOR_NAME = "games"
	MAX_LENGHT = 50

	_games = None  # Static list of know games

	# def generate(self, menuhandler):
	# return _("[ Games ]")

	def encode(self) -> dict[str, str]:
		return {"generator": self.GENERATOR_NAME}

	@staticmethod
	def callback(menu, daemon, controller, menuitem) -> None:
		menuitem._desktop_file.launch()
		menu.quit(-2)

	def generate(self, menuhandler) -> list[MenuItem]:
		if GameListMenuGenerator._games is None:
			GameListMenuGenerator._games = []
			games = [
				x
				for x in Gio.AppInfo.get_all()
				if x.get_categories() and "Game" in x.get_categories().split(";")
			]
			for item_id, game in enumerate(sorted(games, key=lambda x: x.get_display_name().casefold())):
				menuitem = MenuItem(str(item_id), game.get_display_name(), icon=game.get_icon())
				menuitem.callback = GameListMenuGenerator.callback
				menuitem._desktop_file = game
				GameListMenuGenerator._games.append(menuitem)
		return GameListMenuGenerator._games


def register_menu_generators() -> None:
	"""Add classes to MENU_GENERATORS dict

	Needs to be called from menu otherwise entries will be empty
	"""
	for cls in (
		ProfileListMenuGenerator,
		RecentListMenuGenerator,
		WindowListMenuGenerator,
		GameListMenuGenerator,
	):
		MENU_GENERATORS[cls.GENERATOR_NAME] = cls
