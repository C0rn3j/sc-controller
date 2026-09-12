#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


def make_icon_button(icon_name, sensitive):
	button = Gtk.Button()
	button.add(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))
	button.set_sensitive(sensitive)
	return button


def make_text_button(text, icon_name, sensitive):
	box = Gtk.Box(spacing=6)
	box.pack_start(
		Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON),
		False,
		False,
		0,
	)
	box.pack_start(Gtk.Label(label=text), False, False, 0)
	button = Gtk.Button()
	button.add(box)
	button.set_sensitive(sensitive)
	return button


class Test(Gtk.Application):
	def __init__(self):
		super().__init__(application_id="org.example.HeaderIconsGtk3")

	def do_activate(self):
		window = Gtk.ApplicationWindow(application=self)
		window.set_title("GTK3 disabled icon test")
		window.set_default_size(700, 200)

		header = Gtk.HeaderBar()
		buttons = (
			make_icon_button("edit-undo-symbolic", False),
			make_icon_button("edit-redo-symbolic", True),
			make_text_button("Undo", "edit-undo-symbolic", False),
			make_text_button("Redo", "edit-redo-symbolic", True),
		)
		for button in buttons:
			header.pack_start(button)
		window.set_titlebar(header)

		undo_bare = make_text_button("Undo", "edit-undo-symbolic", False)
		redo_bare = make_text_button("Redo", "edit-redo-symbolic", True)
		undo_text = make_icon_button("edit-undo-symbolic", False)
		redo_text = make_icon_button("edit-redo-symbolic", True)
		buttons += (undo_bare, redo_bare)
		buttons += (undo_text, redo_text)

		content = Gtk.Box(
			orientation=Gtk.Orientation.VERTICAL,
			spacing=12,
			margin_top=30,
			margin_bottom=30,
			margin_start=10,
			margin_end=30,
		)
		edit_buttons = Gtk.Box(spacing=6, halign=Gtk.Align.START)
		edit_buttons.pack_start(undo_text, False, False, 0)
		edit_buttons.pack_start(redo_text, False, False, 0)
		edit_buttons.pack_start(undo_bare, False, False, 0)
		edit_buttons.pack_start(redo_bare, False, False, 0)
		content.pack_start(edit_buttons, False, False, 0)

		toggle = Gtk.Button(label="Swap enabled states")
		toggle.set_halign(Gtk.Align.CENTER)
		toggle.connect("clicked", lambda _button: [
			button.set_sensitive(not button.get_sensitive()) for button in buttons
		])
		content.pack_start(toggle, False, False, 0)
		window.add(content)
		window.show_all()
		window.present()


Test().run()
