"""Controller LED editor."""

from __future__ import annotations

import colorsys

from gi.repository import Gdk, GLib, Gtk

from scc.gui.editor import Editor


class LEDEditor(Editor):
	GLADE = "led_editor.ui"
	PLAYER_LED_MODES = ("on", "off", "controller-count")
	PLAYER_LED_PATTERNS = (0x04, 0x0A, 0x15, 0x1B, 0x1F)

	def __init__(self, app, controller) -> None:
		self.app = app
		self.controller = controller
		self._loading = True
		self._save_timer = None
		self._controller_count_handler = None
		self._css_provider = Gtk.CssProvider()
		self.setup_widgets()
		Gtk.StyleContext.add_provider_for_display(
			Gdk.Display.get_default(), self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
		)
		self.window.connect("close-request", self.on_close_request)

		controller_type = controller.get_type() or ""
		self._has_rgb_led = controller_type.startswith(("ds4", "ds5"))
		self._has_player_leds = controller_type.startswith("ds5")
		self.builder.get_object("sclLEDHue").set_visible(self._has_rgb_led)
		self.builder.get_object("lblLEDHue").set_visible(self._has_rgb_led)
		self.builder.get_object("sclLEDSaturation").set_visible(self._has_rgb_led)
		self.builder.get_object("lblLEDSaturation").set_visible(self._has_rgb_led)
		self.builder.get_object("boxPlayerLEDs").set_visible(self._has_player_leds)
		self.builder.get_object("lblPlayerLEDs").set_visible(self._has_player_leds)

		cfg = self.app.config.get_controller_config(controller.get_id())
		self.builder.get_object("adjLEDHue").set_value(float(cfg["led_hue"]))
		self.builder.get_object("adjLEDSaturation").set_value(float(cfg["led_saturation"]))
		self.builder.get_object("adjLEDBrightness").set_value(float(cfg["led_level"]))
		mode = cfg.get("player_led_mode", "controller-count")
		self.builder.get_object("ddPlayerLEDs").set_selected(
			self.PLAYER_LED_MODES.index(mode) if mode in self.PLAYER_LED_MODES else 2,
		)
		if self._has_player_leds:
			self._controller_count_handler = self.app.dm.connect(
				"controller-count-changed", self.on_controller_count_changed,
			)
		self._loading = False
		self.update_gradients()
		self.update_player_leds(send=False)

	def _get_hsv(self) -> tuple[float, float, float]:
		return (
			self.builder.get_object("adjLEDHue").get_value() / 360.0,
			self.builder.get_object("adjLEDSaturation").get_value() / 100.0,
			self.builder.get_object("adjLEDBrightness").get_value() / 100.0,
		)

	def _get_rgb(self) -> tuple[int, int, int]:
		return tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(*self._get_hsv()))

	@staticmethod
	def _css_rgb(rgb: tuple[float, float, float]) -> str:
		return "rgb(%d,%d,%d)" % tuple(round(channel * 255) for channel in rgb)

	def update_gradients(self) -> None:
		hue, saturation, brightness = self._get_hsv()
		saturation_color = self._css_rgb(colorsys.hsv_to_rgb(hue, 1.0, brightness))
		brightness_color = self._css_rgb(colorsys.hsv_to_rgb(hue, saturation, 1.0))
		css = f"""
			scale.led-hue trough {{ background-image: linear-gradient(to right, #f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00); }}
			scale.led-saturation trough {{ background-image: linear-gradient(to right, #fff, {saturation_color}); }}
			scale.led-brightness trough {{ background-image: linear-gradient(to right, #000, {brightness_color}); }}
			scale.led-hue highlight, scale.led-saturation highlight, scale.led-brightness highlight {{ background: transparent; }}
			.player-led {{ color: alpha(currentColor, 0.20); }}
			.player-led.lit {{ color: white; text-shadow: 0 0 4px white; }}
		"""
		self._css_provider.load_from_data(css.encode("utf-8"))

	def on_led_value_changed(self, *args) -> None:
		if self._loading:
			return
		self.update_gradients()
		hue, saturation, brightness = self._get_hsv()
		cfg = self.app.config.get_controller_config(self.controller.get_id())
		cfg["led_hue"] = round(hue * 360)
		cfg["led_saturation"] = round(saturation * 100)
		cfg["led_level"] = round(brightness * 100)
		if self._has_rgb_led:
			self.controller.set_led_color(*self._get_rgb())
		else:
			self.controller.set_led_level(round(brightness * 100))
		self.schedule_save()

	def _player_led_mask(self) -> int:
		mode = self.PLAYER_LED_MODES[self.builder.get_object("ddPlayerLEDs").get_selected()]
		if mode == "on":
			return 0x1F
		if mode == "off":
			return 0
		count = max(1, min(len(self.app.dm.get_controllers()), len(self.PLAYER_LED_PATTERNS)))
		return self.PLAYER_LED_PATTERNS[count - 1]

	def update_player_leds(self, send=True) -> None:
		if not self._has_player_leds:
			return
		mask = self._player_led_mask()
		for index in range(5):
			led = self.builder.get_object(f"ledPlayer{index + 1}")
			if mask & (1 << index):
				led.add_css_class("lit")
			else:
				led.remove_css_class("lit")
		if send:
			self.controller.set_player_leds(mask)

	def on_player_led_mode_changed(self, *args) -> None:
		if self._loading or not self._has_player_leds:
			return
		selected = self.builder.get_object("ddPlayerLEDs").get_selected()
		cfg = self.app.config.get_controller_config(self.controller.get_id())
		cfg["player_led_mode"] = self.PLAYER_LED_MODES[selected]
		self.update_player_leds()
		self.schedule_save()

	def on_controller_count_changed(self, *args) -> None:
		if self.PLAYER_LED_MODES[self.builder.get_object("ddPlayerLEDs").get_selected()] == "controller-count":
			self.update_player_leds()

	def schedule_save(self) -> None:
		if self._save_timer is not None:
			GLib.source_remove(self._save_timer)
		self._save_timer = GLib.timeout_add_seconds(1, self._save_config)

	def _save_config(self) -> bool:
		self._save_timer = None
		self.app.save_config()
		return GLib.SOURCE_REMOVE

	def on_close_request(self, *args) -> bool:
		if self._save_timer is not None:
			GLib.source_remove(self._save_timer)
			self._save_timer = None
			self.app.save_config()
		if self._controller_count_handler is not None:
			self.app.dm.disconnect(self._controller_count_handler)
			self._controller_count_handler = None
		return False
