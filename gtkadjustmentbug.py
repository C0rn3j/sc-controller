import os
import sys
from pathlib import Path
from types import SimpleNamespace
import subprocess

# Match the application's DLL lookup setup without importing application code.
if sys.platform == "win32":
	_dll_directory = os.add_dll_directory(r"C:\msys64\clang64\bin")

if "--bisect-dlls" in sys.argv:
	for stage in ("baseline", "ctypes", "ctypes-util", "intl-load", "gtk-before-ctypes", "gtk-before-intl"):
		print(f"\n=== Fresh process: {stage} ===", flush=True)
		subprocess.run([sys.executable, str(Path(__file__).resolve()), "--probe-stage", stage], check=True)
	sys.exit(0)

if "--bisect-init" in sys.argv:
	for stage in ("baseline", "locale", "intl-load", "intl-bind", "glib-env", "scc"):
		print(f"\n=== Fresh process: {stage} ===", flush=True)
		subprocess.run([sys.executable, str(Path(__file__).resolve()), "--probe-stage", stage], check=True)
	sys.exit(0)

if "--bisect-imports" in sys.argv:
	for stage in ("baseline", "scc", "tools", "logging", "app"):
		print(f"\n=== Fresh process: {stage} ===", flush=True)
		subprocess.run([sys.executable, str(Path(__file__).resolve()), "--probe-stage", stage], check=True)
	sys.exit(0)

if "--probe-stage" in sys.argv:
	stage = sys.argv[sys.argv.index("--probe-stage") + 1]
	if stage in ("gtk-before-ctypes", "gtk-before-intl"):
		import gi
		gi.require_version("Gtk", "4.0")
		from gi.repository import Gtk
		before = Gtk.Adjustment(value=50, lower=0, upper=100)
		print("before ctypes getter:", before.get_value(), "property:", before.props.value, flush=True)
	if stage in ("ctypes", "ctypes-util", "gtk-before-ctypes"):
		import ctypes
		print("ctypes:", ctypes.__file__, flush=True)
	if stage == "ctypes-util":
		import ctypes.util
	if stage == "locale":
		import locale
		print("System locale:", locale.setlocale(locale.LC_ALL, ""), flush=True)
	if stage in ("intl-load", "intl-bind", "gtk-before-intl"):
		import ctypes
		import ctypes.util
		library = "libintl-8.dll" if sys.platform == "win32" else ctypes.util.find_library("intl")
		if library:
			native_gettext = ctypes.CDLL(library)
			if stage == "intl-bind":
				for symbol, arguments in (
					("libintl_bindtextdomain", (b"sc-controller", os.fsencode(Path(__file__).resolve().parent / "scc/locale"))),
					("libintl_bind_textdomain_codeset", (b"sc-controller", b"UTF-8")),
					("libintl_textdomain", (b"sc-controller",)),
				):
					function = getattr(native_gettext, symbol)
					function.argtypes = [ctypes.c_char_p] * len(arguments)
					function.restype = ctypes.c_char_p
					print(symbol, function(*arguments), flush=True)
		else:
			print("No separate libintl library on this platform", flush=True)
	if stage == "glib-env":
		import gi
		from gi.repository import GLib
		GLib.setenv("LANGUAGE", "cs", True)
	if stage in ("scc", "tools", "logging", "app"):
		import scc
		print("scc:", scc.__file__, flush=True)
	if stage in ("tools", "logging", "app"):
		from scc.tools import init_logging
	if stage in ("logging", "app"):
		init_logging()
	if stage == "app":
		import scc.gui.app
	import gi
	gi.require_version("Gtk", "4.0")
	from gi.repository import Gtk
	adj = Gtk.Adjustment(value=50, lower=0, upper=100)
	print("initial getter:", adj.get_value(), "property:", adj.props.value, flush=True)
	adj.props.value = 75
	print("changed getter:", adj.get_value(), "property:", adj.props.value, flush=True)
	sys.exit(0)

if "--app-imports" in sys.argv:
	# Match the GUI's initialization order without starting its daemon manager.
	from scc.tools import init_logging

	init_logging()
	import scc.gui.app

	print("Loaded application imports:", scc.gui.app.__file__, flush=True)

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

adj = Gtk.Adjustment(value=50, lower=0, upper=100)
print("getter:", adj.get_value())
print("property:", adj.props.value)

print("Python:", sys.version)
print("Executable:", sys.executable)
print("PyGObject:", gi.__version__, gi.__file__)
print("GTK:", Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())


class AdjustmentTest(Gtk.Application):
	def do_activate(self):
		self.adjustment = Gtk.Adjustment(value=50, lower=0, upper=100, step_increment=1, page_increment=10)
		self.scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adjustment)
		self.scale.set_draw_value(True)
		self.scale.connect("value-changed", self.on_changed)
		window = Gtk.ApplicationWindow(application=self, title="Drag the slider and compare terminal output")
		window.set_default_size(600, 100)
		window.set_child(self.scale)
		window.present()
		self.show_values("initial")

	def show_values(self, where):
		print(
			where,
			"adjustment getter:", self.adjustment.get_value(),
			"property:", self.adjustment.props.value,
			"scale getter:", self.scale.get_value(),
			"same adjustment:", self.scale.get_adjustment() == self.adjustment,
			flush=True,
		)
		return GLib.SOURCE_REMOVE

	def on_changed(self, scale):
		self.show_values("inside callback")
		GLib.idle_add(self.show_values, "after callback")


if "--editor" in sys.argv:
	import scc.gui.led_editor as led_module
	from scc.gui.led_editor import LEDEditor

	class ProbeEditor(LEDEditor):
		def show_values(self, where):
			print(
				where,
				"getters:", tuple(adj.get_value() for adj in self._led_adjustments),
				"properties:", tuple(adj.props.value for adj in self._led_adjustments),
				"sliders:", tuple(self.builder.get_object(f"sclLED{axis}").get_value()
					for axis in ("Hue", "Saturation", "Brightness")),
				flush=True,
			)
			return GLib.SOURCE_REMOVE

		def on_led_value_changed(self, *args):
			if not self._loading:
				self.show_values("inside editor callback")
				GLib.idle_add(self.show_values, "after editor callback")
			super().on_led_value_changed(*args)


	class EditorTest(Gtk.Application):
		def do_activate(self):
			cfg = {"led_hue": 240, "led_saturation": 100, "led_level": 80}
			controller = SimpleNamespace(
				get_type=lambda: "ds5", get_id=lambda: "reproducer",
				set_led_color=lambda *rgb: print("RGB request:", rgb, flush=True),
				set_player_leds=lambda mask: None,
			)
			app = SimpleNamespace(
				gladepath=str(Path(__file__).resolve().parent / "ui"),
				config=SimpleNamespace(get_controller_config=lambda _id: cfg),
				dm=SimpleNamespace(connect=lambda *args: 1, disconnect=lambda *args: None,
					get_controllers=lambda: [controller]),
				save_config=lambda: print("Configuration in memory:", cfg, flush=True),
			)
			print("Editor module:", led_module.__file__, flush=True)
			self.editor = ProbeEditor(app, controller)
			self.editor.window.set_application(self)
			self.editor.window.present()
			self.editor.show_values("initial editor values")


	EditorTest().run([sys.argv[0]])
else:
	AdjustmentTest().run([sys.argv[0]])
