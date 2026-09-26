"""SC Controller - X11.

Daemon-related stuff that really needs X server to work.
"""
import os
import sys

_dll_directories = []

if sys.platform == "win32":
	_dll_directories.append(
		os.add_dll_directory(r"C:\msys64\mingw64\bin"),
	)

def get_xdisplay():
	"""Return the Xlib display used by GTK4, or None on non-X11 backends."""
	if sys.platform != "linux":
		return None

	import gi
	gi.require_version("Gdk", "4.0")
	gi.require_version("GdkX11", "4.0")
	from gi.repository import Gdk, GdkX11

	from scc.lib import xwrappers as X

	display = Gdk.Display.get_default()
	if not isinstance(display, GdkX11.X11Display):
		return None
	return X.Display(hash(display.get_xdisplay()))
