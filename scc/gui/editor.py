"""SC Controller - Action Editor

Allows to edit button or trigger action.
"""

import logging
import os

from gi.repository import Gdk, Gtk

log = logging.getLogger("Editor")


class ComboSetter:
	def set_cb(self, cb: Gtk.ComboBox | None, key: str, keyindex: int = 0) -> bool:
		"""Set combobox value.

		Returns True on success or False if key is not found.
		"""
		model = cb.get_model()
		self._recursing = True
		for row in model:
			if key == row[keyindex]:
				cb.set_active_iter(row.iter)
				self._recursing = False
				return True
		log.warning("Failed to set combobox value, key '%s' not found", key)
		self._recursing = False
		return False


class Editor(ComboSetter):
	"""Common stuff for all editor windows"""

	ERROR_CSS = " #error {background-color:green; color:red;} "
	_error_css_provider = None

	def __init__(self):
		self.added_widget = None  # See add_widget method

	def on_window_key_press_event(self, controller, keyval, keycode, state):
		"""Checks if pressed key was escape and if yes, closes window"""
		if keyval == Gdk.KEY_Escape:
			self.close()

	def setup_widgets(self):
		self.builder = Gtk.Builder(self)
		self.builder.add_from_file(os.path.join(self.app.gladepath, self.GLADE))
		self.window = self.builder.get_object("Dialog")

	@staticmethod
	def install_error_css():
		if Editor._error_css_provider is None:
			Editor._error_css_provider = Gtk.CssProvider()
			Editor._error_css_provider.load_from_data(Editor.ERROR_CSS.encode("utf-8"))
			Gtk.StyleContext.add_provider_for_display(
				Gdk.Display.get_default(), Editor._error_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER,
			)

	def hide_dont_destroy(self, w, *a):
		"""When used as a 'close-request' handler, hide the window instead of destroying it."""
		w.hide()
		return True

	def set_title(self, title):
		self.window.set_title(title)
		self.set_headerbar_title(self.builder.get_object("header"), title)

	@staticmethod
	def set_headerbar_title(headerbar, title):
		"""Set a GTK4 header bar's title-widget label."""
		title_widget = headerbar.get_title_widget()
		if not isinstance(title_widget, Gtk.Label):
			title_widget = Gtk.Label()
			title_widget.add_css_class("title")
			headerbar.set_title_widget(title_widget)
		title_widget.set_label(title)

	def close(self, *a):
		self.window.destroy()

	def get_transient_for(self):
		"""Return parent window for this editor. Usually main application window"""
		return self._transient_for

	def show(self, transient_for):
		if transient_for:
			self._transient_for = transient_for
			self.window.set_transient_for(transient_for)
			self.window.set_modal(True)
		self.window.show()

	def add_widget(self, label, widget):
		"""Add new widget into row before Action Name.

		Widget is automatically passed to Macro Editor or Modeshift Editor
		if either one is opened from editor window.

		When editor window is closed or destroyed, widget is automatically
		deattached to keep it from destroying.
		"""
		lblAddedWidget = self.builder.get_object("lblAddedWidget")
		vbAddedWidget = self.builder.get_object("vbAddedWidget")
		lblAddedWidget.set_label(label)
		lblAddedWidget.set_visible(True)
		for ch in vbAddedWidget.observe_children():
			vbAddedWidget.remove(ch)
		self.added_widget = widget
		vbAddedWidget.append(widget)
		vbAddedWidget.set_visible(True)

	def remove_added_widget(self):
		"""Remove added widget, if any.

		Should be called from on_destory handlers.
		"""
		vbAddedWidget = self.builder.get_object("vbAddedWidget")
		for ch in vbAddedWidget.observe_children():
			vbAddedWidget.remove(ch)
		self.added_widget = None

	def send_added_widget(self, target):
		"""Transfer added widget to new editor window"""
		if self.added_widget:
			vbAddedWidget = self.builder.get_object("vbAddedWidget")
			lblAddedWidget = self.builder.get_object("lblAddedWidget")
			label = lblAddedWidget.get_label()
			w = self.added_widget
			self.remove_added_widget()
			target.add_widget(label, w)
