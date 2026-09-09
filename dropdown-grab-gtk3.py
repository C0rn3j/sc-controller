#!/usr/bin/env python3
"""GTK3 comparison for the GTK4 combobox mouse-input reproducer."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


window = Gtk.Window()

combo = Gtk.ComboBoxText()
combo.append_text("First option")
combo.append_text("Second option")

box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
box.pack_start(combo, True, True, 0)
box.pack_start(Gtk.Button(label="Hover or click me"), True, True, 0)
window.add(box)

window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
