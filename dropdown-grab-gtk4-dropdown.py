#!/usr/bin/env python3
"""GTK4 Gtk.DropDown comparison for the GtkComboBox input-grab bug."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


Gtk.init()
loop = GLib.MainLoop()
window = Gtk.Window()

options = Gtk.StringList.new(("First option", "Second option"))
dropdown = Gtk.DropDown(model=options)

box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
box.append(dropdown)
box.append(Gtk.Button(label="Hover or click me"))
window.set_child(box)

window.connect("close-request", lambda _window: loop.quit())
window.present()
loop.run()
