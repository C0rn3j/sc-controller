"""OSD mode uses virtual input rather than removed GTK3 event APIs."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gtk

import scc.actions  # noqa: F401
from scc.gui.osd_mode import OSDModeMapper, OSDModeMappings
from scc.parser import ActionParser
from scc.profile import Profile
from scc.uinput import Keys


@pytest.fixture
def mapper(monkeypatch):
	keyboard = Mock()
	mouse = Mock()
	keyboard_factory = Mock(return_value=keyboard)
	mouse_factory = Mock(return_value=mouse)
	monkeypatch.setattr("scc.mapper.Keyboard", keyboard_factory)
	monkeypatch.setattr("scc.mapper.Mouse", mouse_factory)
	profile = Profile(ActionParser())
	profile.load(str(Path(__file__).resolve().parents[1] /
		"default_profiles/.scc-osd.profile_editor.sccprofile"))
	mapper = OSDModeMapper(Mock(), profile)
	keyboard_factory.assert_called_once_with(name=b"SCController OSD Keyboard")
	mouse_factory.assert_called_once_with(name=b"SCController OSD Mouse")
	return mapper


@pytest.mark.parametrize(("button", "key"), [
	("A", Keys.KEY_SPACE), ("B", Keys.KEY_ESC), ("Y", Keys.KEY_F2),
])
def test_keyboard_press_and_release(mapper, button, key):
	mapper.handle_event(None, button, (1,))
	mapper.handle_event(None, button, (0,))
	mapper.keyboard.pressEvent.assert_called_once_with([key])
	mapper.keyboard.releaseEvent.assert_called_once_with([key])


@pytest.mark.parametrize(("button", "key"), [
	("RPADPRESS", Keys.BTN_LEFT), ("LPADPRESS", Keys.BTN_RIGHT),
])
def test_mouse_press_and_release(mapper, button, key):
	mapper.handle_event(None, button, (1,))
	mapper.handle_event(None, button, (0,))
	assert mapper.mouse.keyEvent.call_args_list == [call(key, 1), call(key, 0)]
	assert mapper.mouse.synEvent.call_count == 2


def test_exit(mapper):
	mapper.handle_event(None, "C", (0,))
	mapper.app.quit.assert_called_once()


@pytest.mark.skipif(
	not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"),
	reason="needs a display; try xvfb-run",
)
def test_hints_are_embedded_in_editor():
	window = Gtk.Window()
	hints_window = Gtk.Window()
	content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
	hints = Gtk.Box()
	window.set_child(content)
	hints_window.set_child(hints)
	objects = {"content": content}
	for name in OSDModeMappings.MAIN_WINDOW_BUTTONS | OSDModeMappings.OTHER_WINDOW_BUTTONS:
		objects[name] = Gtk.Box()
		hints.append(objects[name])
	app = SimpleNamespace(window=window, builder=SimpleNamespace(get_object=objects.get))
	try:
		mappings = OSDModeMappings(app, None, hints_window)
		mappings.show()
		assert hints.get_parent() is content
		assert hints_window.get_child() is None
		assert not hints_window.get_visible()
		for name, widget in objects.items():
			if name != "content":
				assert widget.get_visible() == (name in mappings.MAIN_WINDOW_BUTTONS)
		mappings.on_main_window_focus_out_event()
		for name, widget in objects.items():
			if name != "content":
				assert widget.get_visible() == (name in mappings.OTHER_WINDOW_BUTTONS)
	finally:
		hints_window.destroy()
		window.destroy()
