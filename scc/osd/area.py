"""SC-Controller - OSD Menu.

Displays border around area.
"""

from __future__ import annotations

import logging

from gi.repository import Gtk, GLib, GdkX11

from scc.constants import LEFT, RIGHT, STICK, STICK_PAD_MAX, STICK_PAD_MIN
from scc.gui.daemon_manager import DaemonManager
from scc.lib import xwrappers as X
from scc.osd import OSDWindow
from scc.osd.timermanager import TimerManager
from scc.tools import _

log = logging.getLogger("osd.area")


class Area(OSDWindow, TimerManager):
	BORDER_WIDTH = 2

	def __init__(self) -> None:
		OSDWindow.__init__(self, "osd-area")
		TimerManager.__init__(self)
		self.size = (100, 100)
		self.add(Gtk.Fixed())

	def _add_arguments(self) -> None:
		OSDWindow._add_arguments(self)
		self.argparser.add_argument("--width", type=int, metavar="pixels", default=20, help="""area width in pixels""")
		self.argparser.add_argument(
			"--height", type=int, metavar="pixels", default=-20, help="""area height in pixels"""
		)

	def parse_argumets(self, argv) -> bool:
		if not OSDWindow.parse_argumets(self, argv):
			return False
		self.position = (self.position[0] - self.BORDER_WIDTH, self.position[1] - self.BORDER_WIDTH)
		self.size = (self.args.width + 2 * self.BORDER_WIDTH, self.args.height + 2 * self.BORDER_WIDTH)
		return True

	def compute_position(self) -> tuple[int, int]:
		# Overrides compute_position as Area is requested with exact position
		# on X screen.
		return self.position

	def show(self) -> None:
		OSDWindow.show(self)
		self.realize()
		self.resize(*self.size)
		self.make_hole(self.BORDER_WIDTH)

	def update(self, x: int, y: int, width: int, height: int) -> None:
		"""Update area size and position."""
		self.position = x, y
		self.size = max(1, width), max(1, height)  # Size can't be <1 or GTK will crash
		self.move(*self.position)
		self.resize(*self.size)
		self.make_hole(self.BORDER_WIDTH)

	def make_hole(self, border_width: int) -> None:
		"""Use shape extension to create a hole in the window...

		Area needs only border, rest should be transparent.
		"""
		width, height = self.size
		dpy = X.Display(hash(GdkX11.x11_get_default_xdisplay()))  # I have no idea why this works...
		wid = X.XID(self.get_window().get_xid())

		mask = X.create_pixmap(dpy, wid, width, height, 1)
		xgcv = X.c_void_p()
		gc = X.create_gc(dpy, mask, 0, xgcv)

		X.set_foreground(dpy, gc, 1)
		X.fill_rectangle(dpy, mask, gc, 0, 0, width, height)

		X.set_foreground(dpy, gc, 0)
		X.fill_rectangle(dpy, mask, gc, border_width, border_width, width - 2 * border_width, height - 2 * border_width)

		SHAPE_BOUNDING = 0
		SHAPE_SET = 0
		X.shape_combine_mask(dpy, wid, SHAPE_BOUNDING, 0, 0, mask, SHAPE_SET)

		X.free_gc(dpy, gc)
		X.free_pixmap(dpy, mask)
