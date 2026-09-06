"""SC Controller StatusNotifierItem and D-Bus menu implementation."""

import logging
import os

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, GObject, Gtk  # noqa: E402

from scc.tools import _  # noqa: E402  # gettext function

log = logging.getLogger("StatusIcon")

SNI_INTERFACE = "org.kde.StatusNotifierItem"
SNI_WATCHER = "org.kde.StatusNotifierWatcher"
SNI_PATH = "/StatusNotifierItem"
SNI_WATCHER_PATH = "/StatusNotifierWatcher"
MENU_INTERFACE = "com.canonical.dbusmenu"
MENU_PATH = "/StatusNotifierMenu"

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <method name="ProvideXdgActivationToken"><arg type="s" direction="in"/></method>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <signal name="NewTitle"/><signal name="NewIcon"/><signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/><signal name="NewMenu"/><signal name="NewToolTip"/>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/>
      <arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
    <method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/>
      <arg type="a(ia{sv})" direction="out"/></method>
    <method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="out"/></method>
    <method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="in"/><arg type="u" direction="in"/></method>
    <method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/>
      <arg type="ai" direction="out"/></method>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
    <signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
    <signal name="ItemActivationRequested"><arg type="i"/><arg type="u"/></signal>
  </interface>
</node>
"""

class StatusIcon(GObject.GObject):
	"""Base class for all status icon backends."""

	TRAY_TITLE = _("SC Controller")

	__gsignals__ = {
		"clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
	}

	__gproperties__ = {
		"active": (
			GObject.TYPE_BOOLEAN,
			"is the icon user-visible?",
			"does the icon back-end think that anything is might be shown to the user?",
			True,
			GObject.ParamFlags.READWRITE,
		),
	}

	def __init__(self, icon_path, popupmenu, force=False):
		GObject.GObject.__init__(self)
		self.__icon_path = os.path.normpath(os.path.abspath(icon_path))
		self.__popupmenu = popupmenu
		self.__active = True
		self.__visible = False
		self.__hidden = False
		self.__icon = "scc-unknown"
		self.__text = ""
		self.__force = force

	def get_active(self):
		"""Return whether there is at least a chance that the icon might be shown to the user

		If this returns `False` then the icon will definetely not be shown, but if it returns `True` it doesn't have to
		be visible...

		<em>Note:</em> This value is not directly influenced by calling `hide()` and `show()`.

		@return {bool}
		"""
		return self.get_property("active")

	def set(self, icon=None, text=None) -> None:
		"""Set the status icon image and descriptive text

		If either of these are `None` their previous value will be used.

		@param {String} icon
		       The name of the icon to show (i.e. `si-syncthing-idle`)
		@param {String} text
		       Some text that indicates what the application is currently doing (generally this be used for the tooltip)
		"""
		if not icon.endswith("-0"):  # si-syncthing-0
			# Ignore first syncing icon state to prevent the icon from flickering
			# into the main notification bar during initialization
			self.__visible = True

		if self.__hidden:
			self._set_visible(False)
		else:
			self._set_visible(self.__visible)

	def hide(self):
		"""Hide the icon

		This method tries its best to ensure the icon is hidden, but there are no guarantees as to how use well its
		going to work.
		"""
		self.__hidden = True
		self._set_visible(False)

	def show(self):
		"""Show a previously hidden icon

		This method tries its best to ensure the icon is hidden, but there are no guarantees as to how use well its
		going to work.
		"""
		self.__hidden = False
		self._set_visible(self.__visible)

	def is_clickable(self) -> bool:
		"""Return whether activating the icon can emit the clicked signal."""
		return True

	def _is_forced(self):
		return self.__force

	def _on_click(self, *a):
		self.emit("clicked")

	def _get_icon(self, icon=None):
		"""@internal

		Use `set()` instead.
		"""
		if icon:
			self.__icon = icon
		return self.__icon

	def _get_text(self, text=None):
		"""@internal

		Use `set()` instead.
		"""
		if text:
			self.__text = text
		return self.__text

	def _get_popupmenu(self):
		"""@internal
		"""
		return self.__popupmenu

	def _get_icon_path(self):
		return self.__icon_path

	def _set_visible(self, visible):
		"""@internal
		"""

	def do_get_property(self, property):
		if property.name == "active":
			return self.__active
		raise AttributeError("Unknown property %s" % property.name)

	def do_set_property(self, property, value):
		if property.name == "active":
			self.__active = value
		else:
			raise AttributeError("unknown property %s" % property.name)


class StatusIconDummy(StatusIcon):
	"""Dummy status icon implementation that does nothing"""

	def __init__(self, *args, **kwargs) -> None:
		StatusIcon.__init__(self, *args, **kwargs)

		# Pretty unlikely that this will be visible...
		self.set_property("active", False)

	def set(self, icon=None, text=None) -> None:
		StatusIcon.set(self, icon, text)

		self._get_icon(icon)
		self._get_text(text)

	def destroy(self):
		return

class DBusMenu:
	"""Export the GTK tray popover using Canonical's D-Bus menu protocol."""

	def __init__(self, connection, popupmenu) -> None:
		self.connection = connection
		self.popupmenu = popupmenu
		self.revision = 1
		self.items = {}
		self._signature = None
		info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
		self.registration_id = connection.register_object(
			MENU_PATH, info, self._method_call, self._get_property, None,
		)
		self._refresh()

	def destroy(self) -> None:
		if self.registration_id:
			self.connection.unregister_object(self.registration_id)
			self.registration_id = 0

	def _widgets(self):
		container = self.popupmenu.get_child()
		widget = container.get_first_child() if container else None
		while widget:
			yield widget
			widget = widget.get_next_sibling()

	@staticmethod
	def _label(widget) -> str:
		label = widget.get_label() or ""
		return label.replace("_", "") if widget.get_use_underline() else label

	def _refresh(self) -> bool:
		items = {}
		signature = []
		for item_id, widget in enumerate(self._widgets(), 1):
			properties = {"visible": GLib.Variant("b", widget.get_visible())}
			if isinstance(widget, Gtk.Separator):
				properties["type"] = GLib.Variant("s", "separator")
			else:
				properties.update({
					"label": GLib.Variant("s", self._label(widget)),
					"enabled": GLib.Variant("b", widget.get_sensitive()),
				})
				if isinstance(widget, Gtk.CheckButton):
					properties["toggle-type"] = GLib.Variant("s", "checkmark")
					properties["toggle-state"] = GLib.Variant("i", int(widget.get_active()))
			items[item_id] = (widget, properties)
			signature.append((item_id, tuple((key, value.print_(False)) for key, value in properties.items())))
		changed = self._signature is not None and signature != self._signature
		self.items = items
		self._signature = signature
		if changed:
			self.revision += 1
			parameters = GLib.Variant("(ui)", (self.revision, 0))
			self.connection.emit_signal(None, MENU_PATH, MENU_INTERFACE, "LayoutUpdated", parameters)
		return changed

	def _layout(self, parent_id, recursion_depth, property_names):
		if parent_id != 0:
			return (parent_id, self.items.get(parent_id, (None, {}))[1], [])
		children = [GLib.Variant("(ia{sv}av)", (item_id, props, [])) for item_id, (_, props) in self.items.items()]
		return (0, {"children-display": GLib.Variant("s", "submenu")}, children)

	def _method_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
		try:
			if method == "GetLayout":
				parent_id, depth, names = parameters.unpack()
				self._refresh()
				layout = self._layout(parent_id, depth, names)
				invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, layout)))
			elif method == "GetGroupProperties":
				ids, names = parameters.unpack()
				self._refresh()
				ids = ids or list(self.items)
				values = [(item_id, self.items[item_id][1]) for item_id in ids if item_id in self.items]
				invocation.return_value(GLib.Variant("(a(ia{sv}))", (values,)))
			elif method == "GetProperty":
				item_id, name = parameters.unpack()
				self._refresh()
				value = self.items[item_id][1][name]
				invocation.return_value(GLib.Variant("(v)", (value,)))
			elif method == "Event":
				item_id, event_id, data, timestamp = parameters.unpack()
				self._event(item_id, event_id)
				invocation.return_value(None)
			elif method == "EventGroup":
				failed = []
				for item_id, event_id, data, timestamp in parameters.unpack()[0]:
					if not self._event(item_id, event_id):
						failed.append(item_id)
				invocation.return_value(GLib.Variant("(ai)", (failed,)))
			elif method == "AboutToShow":
				changed = self._refresh()
				invocation.return_value(GLib.Variant("(b)", (changed,)))
			elif method == "AboutToShowGroup":
				ids = parameters.unpack()[0]
				changed = self._refresh()
				invocation.return_value(GLib.Variant("(aiai)", (ids if changed else [], [])))
			else:
				invocation.return_dbus_error("com.canonical.dbusmenu.Error.UnknownMethod", method)
		except (KeyError, TypeError, ValueError) as error:
			invocation.return_dbus_error("com.canonical.dbusmenu.Error", str(error))

	def _event(self, item_id, event_id) -> bool:
		if event_id != "clicked" or item_id not in self.items:
			return False
		widget = self.items[item_id][0]
		if not widget.get_visible() or not widget.get_sensitive() or isinstance(widget, Gtk.Separator):
			return False
		if isinstance(widget, Gtk.CheckButton):
			widget.set_active(not widget.get_active())
		else:
			widget.emit("clicked")
		return True

	def _get_property(self, connection, sender, path, interface, prop):
		return {
			"Version": GLib.Variant("u", 3),
			"TextDirection": GLib.Variant("s", "ltr"),
			"Status": GLib.Variant("s", "normal"),
			"IconThemePath": GLib.Variant("as", []),
		}.get(prop)


class StatusIconDBus(StatusIcon):
	"""StatusNotifierItem implementation using Gio's D-Bus API."""

	def __init__(self, *args, **kwargs) -> None:
		StatusIcon.__init__(self, *args, **kwargs)
		self._visible = False
		self._destroyed = False
		self._registered = False
		self._name_acquired = False
		self._name_owner_id = 0
		self._watcher_id = 0
		self._watcher_signal_ids = []
		try:
			self._connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
		except GLib.Error as error:
			log.warning("Failed to connect tray to the session bus: %s", error)
			raise NotImplementedError from error

		self._service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
		info = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
		self._registration_id = self._connection.register_object(
			SNI_PATH, info, self._method_call, self._get_property, None,
		)
		if not self._registration_id:
			raise NotImplementedError
		self._menu = DBusMenu(self._connection, self._get_popupmenu())
		self._name_owner_id = Gio.bus_own_name_on_connection(
			self._connection, self._service_name, Gio.BusNameOwnerFlags.NONE,
			self._on_name_acquired, self._on_name_lost,
		)
		self._watcher_id = Gio.bus_watch_name_on_connection(
			self._connection, SNI_WATCHER, Gio.BusNameWatcherFlags.NONE,
			self._on_watcher_appeared, self._on_watcher_vanished,
		)
		for signal in ("StatusNotifierHostRegistered", "StatusNotifierHostUnregistered"):
			self._watcher_signal_ids.append(self._connection.signal_subscribe(
				SNI_WATCHER, SNI_WATCHER, signal, SNI_WATCHER_PATH, None,
				Gio.DBusSignalFlags.NONE, self._on_watcher_signal,
			))
		self.set_property("active", False)

	def _on_name_acquired(self, *args) -> None:
		self._name_acquired = True
		self._register()

	def _on_name_lost(self, *args) -> None:
		self._name_acquired = False
		self._registered = False
		self.set_property("active", False)

	def _on_watcher_appeared(self, *args) -> None:
		self._register()

	def _on_watcher_vanished(self, *args) -> None:
		self._registered = False
		self.set_property("active", False)

	def _on_watcher_signal(self, connection, sender, path, interface, signal, parameters) -> None:
		if signal == "StatusNotifierHostRegistered":
			self._register()
		else:
			self._registered = False
			self.set_property("active", False)

	def _register(self) -> None:
		if self._destroyed or not self._name_acquired:
			return
		try:
			host_reply = self._connection.call_sync(
				SNI_WATCHER, SNI_WATCHER_PATH, "org.freedesktop.DBus.Properties", "Get",
				GLib.Variant("(ss)", (SNI_WATCHER, "IsStatusNotifierHostRegistered")),
				GLib.VariantType.new("(v)"), Gio.DBusCallFlags.NONE, 1000, None,
			)
			if not host_reply.unpack()[0]:
				return
			self._connection.call_sync(
				SNI_WATCHER, SNI_WATCHER_PATH, SNI_WATCHER, "RegisterStatusNotifierItem",
				GLib.Variant("(s)", (self._service_name,)), None, Gio.DBusCallFlags.NONE, 1000, None,
			)
		except GLib.Error as error:
			log.debug("Status notifier watcher is not ready: %s", error)
			return
		self._registered = True
		self.set_property("active", True)

	def _emit(self, signal, parameters=None) -> None:
		if not self._destroyed:
			self._connection.emit_signal(None, SNI_PATH, SNI_INTERFACE, signal, parameters)

	def _set_visible(self, visible) -> None:
		if self._visible == visible:
			return
		self._visible = visible
		self._emit("NewStatus", GLib.Variant("(s)", ("Active" if visible else "Passive",)))

	def set(self, icon=None, text=None) -> None:
		old_icon = self._get_icon()
		old_text = self._get_text()
		StatusIcon.set(self, icon, text)
		self._get_icon(icon)
		self._get_text(text)
		if self._get_icon() != old_icon:
			self._emit("NewIcon")
		if self._get_text() != old_text:
			self._emit("NewToolTip")

	def destroy(self) -> None:
		if self._destroyed:
			return
		self.hide()
		self._destroyed = True
		self._menu.destroy()
		self._connection.unregister_object(self._registration_id)
		if self._watcher_id:
			Gio.bus_unwatch_name(self._watcher_id)
		for subscription_id in self._watcher_signal_ids:
			self._connection.signal_unsubscribe(subscription_id)
		if self._name_owner_id:
			Gio.bus_unown_name(self._name_owner_id)
		self.set_property("active", False)

	def _method_call(self, connection, sender, path, interface, method, parameters, invocation) -> None:
		if method in ("Activate", "SecondaryActivate"):
			self._on_click()
		invocation.return_value(None)

	def _get_property(self, connection, sender, path, interface, prop):
		empty_pixmaps = GLib.Variant("a(iiay)", [])
		values = {
			"Category": GLib.Variant("s", "ApplicationStatus"),
			"Id": GLib.Variant("s", "sc-controller"),
			"Title": GLib.Variant("s", self.TRAY_TITLE),
			"Status": GLib.Variant("s", "Active" if self._visible else "Passive"),
			"WindowId": GLib.Variant("i", 0),
			"IconThemePath": GLib.Variant("s", self._get_icon_path()),
			"Menu": GLib.Variant("o", MENU_PATH),
			"ItemIsMenu": GLib.Variant("b", True),
			"IconName": GLib.Variant("s", self._get_icon()),
			"IconPixmap": empty_pixmaps,
			"OverlayIconName": GLib.Variant("s", ""),
			"OverlayIconPixmap": empty_pixmaps,
			"AttentionIconName": GLib.Variant("s", ""),
			"AttentionIconPixmap": empty_pixmaps,
			"AttentionMovieName": GLib.Variant("s", ""),
			"ToolTip": GLib.Variant("(sa(iiay)ss)", (self._get_icon(), [], self.TRAY_TITLE, self._get_text())),
		}
		return values.get(prop)


class StatusIconProxy(StatusIcon):
	def __init__(self, *args, **kwargs) -> None:
		StatusIcon.__init__(self, *args, **kwargs)

		self._arguments = (args, kwargs)
		self._status_fb = None
		self._status_gtk = None
		self.set("scc-unknown", "")

		# Do not ever force-show indicators when they do not think they'll work
		if "force" in self._arguments[1]:
			del self._arguments[1]["force"]

		# Directly load fallback implementation
		# TODO(Martin): This is no longer a "fallback" but the primary, after the GTK4 migration
		self._load_fallback()

	def _on_click(self, *args):
		self.emit("clicked")

	def _on_notify_active_gtk(self, *args):
		if self._status_fb:
			# Hide fallback icon if GTK icon is active and vice-versa
			if self._status_gtk.get_active():
				self._status_fb.hide()
			else:
				self._status_fb.show()
		elif not self._status_gtk.get_active():
			# Load fallback implementation
			self._load_fallback()

	def _on_notify_active_fb(self, *args):
		active = False
		if self._status_gtk and self._status_gtk.get_active():
			active = True
		if self._status_fb and self._status_fb.get_active():
			active = True
		self.set_property("active", active)

	def _load_fallback(self) -> None:
		status_icon_backends = [StatusIconDBus, StatusIconDummy]

		if not self._status_fb:
			for StatusIconBackend in status_icon_backends:
				try:
					self._status_fb = StatusIconBackend(*self._arguments[0], **self._arguments[1])
					self._status_fb.connect("clicked", self._on_click)
					self._status_fb.connect("notify::active", self._on_notify_active_fb)
					self._on_notify_active_fb()

					log.warning("StatusIcon: Using backend %s", StatusIconBackend.__name__)
					break
				except NotImplementedError:
					continue

			# At least the dummy backend should have been loaded at this point...
			assert self._status_fb

		# Update fallback icon
		self.set(self._icon, self._text)

	def is_clickable(self) -> bool:
		if self._status_gtk:
			return self._status_gtk.is_clickable()
		if self._status_fb:
			return self._status_fb.is_clickable()
		return False

	def set(self, icon=None, text=None):
		self._icon = icon
		self._text = text

		if self._status_gtk and self._status_gtk.get_active():
			self._status_gtk.set(icon, text)
		if self._status_fb:
			self._status_fb.set(icon, text)

	def hide(self):
		if self._status_gtk:
			self._status_gtk.hide()
		if self._status_fb:
			self._status_fb.hide()

	def destroy(self):
		if self._status_gtk:
			self._status_gtk.destroy()
		if self._status_fb:
			self._status_fb.destroy()

	def show(self):
		if self._status_gtk:
			self._status_gtk.show()
		if self._status_fb:
			self._status_fb.show()


def get_status_icon(*args, **kwargs):
	# Try selecting backend based on environment variable
	if "STATUS_BACKEND" in os.environ:
		kwargs["force"] = True

		status_icon_backend_name = "StatusIcon%s" % (os.environ.get("STATUS_BACKEND"))
		if status_icon_backend_name in globals():
			try:
				status_icon = globals()[status_icon_backend_name](*args, **kwargs)
				log.info("StatusIcon: Using requested backend %s" % (status_icon_backend_name))
				return status_icon
			except NotImplementedError:
				log.error("StatusIcon: Requested backend %s is not supported" % (status_icon_backend_name))
		else:
			log.error("StatusIcon: Requested backend %s does not exist" % (status_icon_backend_name))

		return StatusIconDummy(*args, **kwargs)

	# Use proxy backend to determine the correct backend while the application is running
	return StatusIconProxy(*args, **kwargs)
