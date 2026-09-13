"""Startup visibility while the D-Bus tray registers asynchronously."""
from types import SimpleNamespace, MethodType
from unittest.mock import Mock

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
import scc.actions  # noqa: F401
from scc.gui.app import App


@pytest.fixture
def app(monkeypatch):
	app = SimpleNamespace(
		_activated=False, _startup_tray_timeout=None, osd_mode=False,
		config={"gui": {"minimize_on_start": True}},
		window=Mock(), statusicon=Mock(),
	)
	app.statusicon.get_property.return_value = False
	for name in ("do_activate", "_cancel_startup_tray_wait", "on_startup_tray_active",
		"_startup_tray_unavailable", "on_statusicon_clicked"):
		setattr(app, name, MethodType(getattr(App, name), app))
	monkeypatch.setattr("scc.gui.app.GLib.timeout_add_seconds", Mock(return_value=42))
	monkeypatch.setattr("scc.gui.app.GLib.source_remove", Mock())
	return app


def test_delayed_tray_registration_keeps_window_hidden(app):
	app.do_activate()
	app.window.set_visible.assert_called_once_with(False)
	assert app._startup_tray_timeout == 42
	app.statusicon.get_property.return_value = True
	app.on_startup_tray_active(app.statusicon)
	assert app._startup_tray_timeout is None
	app.window.present.assert_not_called()


def test_already_registered_tray_starts_hidden(app):
	app.statusicon.get_property.return_value = True
	app.do_activate()
	assert app._startup_tray_timeout is None
	app.window.set_visible.assert_called_once_with(False)
	app.window.present.assert_not_called()


def test_missing_tray_shows_fallback_window(app):
	app.do_activate()
	assert not app._startup_tray_unavailable()
	app.window.present.assert_called_once()
	assert app._startup_tray_timeout is None


@pytest.mark.parametrize("mode", ["disabled", "no_icon", "osd"])
def test_startup_without_minimizing(app, mode):
	if mode == "disabled":
		app.config["gui"]["minimize_on_start"] = False
	elif mode == "no_icon":
		app.statusicon = None
	else:
		app.osd_mode = True
	app.do_activate()
	app.window.present.assert_called_once()
	assert app._startup_tray_timeout is None


def test_reactivation_cancels_pending_startup_minimize(app):
	app.do_activate()
	app.do_activate()
	app.window.present.assert_called_once()
	assert app._startup_tray_timeout is None
	app.statusicon.get_property.return_value = True
	app.on_startup_tray_active(app.statusicon)
	app.window.set_visible.assert_called_once_with(False)


def test_tray_click_cancels_startup_wait(app):
	app.do_activate()
	app.window.get_visible.return_value = False
	app.on_statusicon_clicked()
	assert app._startup_tray_timeout is None
	app.window.set_visible.assert_called_with(True)
