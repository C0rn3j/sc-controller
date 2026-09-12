#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk


CSS = b"""
.foreground-swatch {
	background-color: currentColor;
	background-image: none;
	min-width: 24px;
	min-height: 24px;
}
"""


def make_button(label, icon_name, sensitive):
	content = Gtk.Box(spacing=6)
	content.append(Gtk.Image.new_from_icon_name(icon_name))
	content.append(Gtk.Label(label=label))

	button = Gtk.Button(child=content)
	button.set_sensitive(sensitive)
	return button


def make_swatch_button(sensitive):
	button = Gtk.Button()
	button.add_css_class("foreground-swatch")
	button.set_sensitive(sensitive)
	button.set_tooltip_text("Enabled foreground" if sensitive else "Disabled foreground")
	return button


class Test(Gtk.Application):
	def __init__(self):
		super().__init__(application_id="org.example.HeaderbarDisabledBackdropGtk4")
		self.windows = []

	def make_window(self, number):
		window = Gtk.ApplicationWindow(application=self)
		window.set_title(f"Backdrop test {number}")
		window.set_default_size(620, 260)

		header = Gtk.HeaderBar()
		header.pack_start(make_button("Enabled", "edit-redo-symbolic", True))
		header.pack_start(make_button("Disabled", "edit-undo-symbolic", False))
		header.pack_end(make_swatch_button(False))
		header.pack_end(make_swatch_button(True))
		window.set_titlebar(header)

		content = Gtk.Box(
			orientation=Gtk.Orientation.VERTICAL,
			spacing=12,
			margin_top=24,
			margin_bottom=24,
			margin_start=24,
			margin_end=24,
		)
		content.append(
			Gtk.Label(
				label=(
					"Click this window, then the other one.\n"
					"Compare enabled and disabled buttons in the header bar\n"
					"with the equivalent buttons in the regular window area."
				),
				justify=Gtk.Justification.CENTER,
			)
		)

		content.append(Gtk.Label(label="Regular window-area buttons"))
		regular_buttons = Gtk.Box(
			spacing=6,
			halign=Gtk.Align.CENTER,
		)
		regular_buttons.append(
			make_button("Enabled", "edit-redo-symbolic", True)
		)
		regular_buttons.append(
			make_button("Disabled", "edit-undo-symbolic", False)
		)
		regular_buttons.append(make_swatch_button(True))
		regular_buttons.append(make_swatch_button(False))
		content.append(regular_buttons)

		focus_button = Gtk.Button(label="Focus the other window")
		focus_button.connect("clicked", self.focus_other_window, window)
		content.append(focus_button)
		window.set_child(content)
		return window

	def focus_other_window(self, _button, current_window):
		for window in self.windows:
			if window is not current_window:
				window.present()
				break

	def do_activate(self):
		if self.windows:
			self.windows[0].present()
			return

		provider = Gtk.CssProvider()
		provider.load_from_data(CSS)
		Gtk.StyleContext.add_provider_for_display(
			Gdk.Display.get_default(),
			provider,
			Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
		)

		self.windows = [self.make_window(1), self.make_window(2)]
		for window in self.windows:
			window.present()


Test().run()
