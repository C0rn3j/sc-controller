"""SC Controller - X11.

Daemon-related stuff that really needs X server to work.
"""


def get_xdisplay():
	"""Return the Xlib display used by GTK4, or None on non-X11 backends."""
	from gi.repository import Gdk, GdkX11

	from scc.lib import xwrappers as X

	display = Gdk.Display.get_default()
	if not isinstance(display, GdkX11.X11Display):
		return None
	return X.Display(hash(display.get_xdisplay()))
