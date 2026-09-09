#!/usr/bin/env python3
"""Minimal reproduction for a GTK4 combobox retaining mouse input."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


Gtk.init()
loop = GLib.MainLoop()
window = Gtk.Window()

combo = Gtk.ComboBoxText()
combo.append_text("First option")
combo.append_text("Second option")

box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
box.append(combo)
box.append(Gtk.Button(label="Hover or click me"))
window.set_child(box)

window.connect("close-request", lambda _window: loop.quit())
window.present()
loop.run()
