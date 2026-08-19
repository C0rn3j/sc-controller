"""DWSNC - Doing Weird Things in Name of Compatibility

This module, when imported, applies various fixes and monkey-patching to allow
application to run with older versions of GLib and/or GTK.
"""

import os

from gi.repository import GObject, Gtk


def child_get_property(parent, child, propname) -> int:
	"""Wrapper for child_get_property, which pygobject doesn't properly introspect"""
	value = GObject.Value()
	value.init(GObject.TYPE_INT)
	parent.child_get_property(child, propname, value)
	return value.get_int()


def headerbar(bar) -> None:
	"""Moves all buttons from left to right (and vice versa) if user's desktop environment is identified as Unity.

	Removes 'icon' button otherwise
	"""
	bar.set_decoration_layout(":minimize,close")
	# Not outside of Unity


IS_UNITY = False
IS_GNOME = False
IS_KDE = False

if "XDG_CURRENT_DESKTOP" in os.environ:
	if "GNOME" in os.environ["XDG_CURRENT_DESKTOP"].split(":"):
		IS_GNOME = True

	if "KDE" in os.environ["XDG_CURRENT_DESKTOP"].split(":"):
		IS_KDE = True

	if "Unity" in os.environ["XDG_CURRENT_DESKTOP"].split(":"):
		# User runs Unity
		IS_UNITY = True

		def _headerbar(bar) -> None:
			children = [] + bar.get_children()
			pack_start = []
			pack_end = []
			for c in children:
				if child_get_property(bar, c, "pack-type") == Gtk.PackType.END:
					bar.remove(c)
					pack_start.append(c)
				else:
					bar.remove(c)
					pack_end.append(c)
			if len(pack_end) > 1:
				c, pack_end = pack_end[0], pack_end[1:]
				pack_end.append(c)
			# Extremely old versions of Ubuntu had this in order, today's Ubuntu has it reversed
			pack_end = reversed(pack_end)
			for c in pack_start:
				bar.pack_start(c)
			for c in pack_end:
				bar.pack_end(c)

		headerbar = _headerbar
