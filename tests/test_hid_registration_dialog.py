"""Check the HIDAPI wizard's saved format without creating GTK windows."""

import sys

import pytest

if sys.platform != "linux":
	pytest.skip("Requires Linux drivers", allow_module_level=True)

import json
from types import SimpleNamespace

import pytest

from scc.constants import SCButtons
from scc.gui.creg import dialog
from scc.gui.creg.constants import AXIS_ORDER
from scc.gui.creg.data import AxisData
from scc.lib.hid_registration import registration_device


@pytest.mark.parametrize("area,button", [("LSTICK", SCButtons.LSTICKPRESS), ("RSTICK", SCButtons.RSTICKPRESS), ("DPAD", None)])
def test_registration_stick_press_mapping(monkeypatch, area, button):
	registration = object.__new__(dialog.ControllerRegistration)
	registration._axis_data = [AxisData(name, xy) for name, xy in AXIS_ORDER]
	page = object()
	stack = SimpleNamespace(observe_children=lambda: [object(), object(), page], get_visible_child=lambda: page)
	menu = SimpleNamespace()
	image = SimpleNamespace(_click_position=(123.0, 456.0))
	popups = []
	registration.app = SimpleNamespace(_popup_at=lambda *args: popups.append(args))
	sensitivity = []
	widgets = {"stDialog": stack, "mnuStick": menu, "mnuStickPress": SimpleNamespace(set_sensitive=sensitivity.append)}
	registration.builder = SimpleNamespace(get_object=widgets.get)
	grabbed = []
	monkeypatch.setattr(dialog, "InputGrabber", lambda parent, what, **kwargs: grabbed.append(what))
	registration.on_area_click(image, area)
	assert popups == [(menu, image, 123.0, 456.0)]
	registration.on_mnuStickPress_activate()
	assert sensitivity == [button is not None]
	assert grabbed == ([] if button is None else [button])
	# Reopening the menu must restore the press option for a stick.
	registration.on_area_click(image, "LSTICK")
	assert sensitivity[-1] is True


@pytest.mark.parametrize(
	"platform,driver,prefix", [("win32", "hid", "hid"), ("darwin", "hid", "hid"), ("linux", "hidapi", "hidapi")]
)
def test_registration_saves_safe_filename_and_backend(tmp_path, monkeypatch, platform, driver, prefix):
	monkeypatch.setattr(dialog, "sys", SimpleNamespace(platform=platform))
	monkeypatch.setattr(dialog, "get_config_path", lambda: str(tmp_path))
	monkeypatch.setattr(dialog.GLib, "timeout_add_seconds", lambda *args: None)
	registration = object.__new__(dialog.ControllerRegistration)
	registration._axis_data = [AxisData(name, xy) for name, xy in AXIS_ORDER]
	registration._mappings = {288: SCButtons.A}
	registration._groups = {"test": ["A", "B", "X", "Y"]}
	registration._evdevice = registration_device(
		{
			"path": b"some HID path",
			"vendor_id": 0x1234,
			"product_id": 0x5678,
			"product_string": 'Controller: "USB"',
		}
	)
	registration._tester = SimpleNamespace(driver=driver)
	registration.kill_tester = lambda: None
	registration.window = SimpleNamespace(close=lambda: None)
	registration.app = SimpleNamespace(dm=SimpleNamespace(rescan=lambda: None))
	buffer = SimpleNamespace()
	buffer.set_text = lambda text: setattr(buffer, "text", text)
	buffer.get_text = lambda *args: buffer.text
	buffer.get_start_iter = lambda: None
	buffer.get_end_iter = lambda: None
	combo = SimpleNamespace(get_model=lambda: [["test"]], get_active=lambda: 0)
	widgets = {"cbControllerButtons": combo, "cbControllerType": combo, "buffRawData": buffer}
	registration.builder = SimpleNamespace(get_object=widgets.get)
	registration.save_registration()
	files = list((tmp_path / "devices").iterdir())
	assert len(files) == 1
	assert files[0].name == f"{prefix}-1234_5678-Controller_ _USB_.json"
	config = json.loads(files[0].read_text())
	assert config["input_backend"] == "hidapi"
	assert config["buttons"] == {"288": "A"}
	assert config["gui"]["buttons"] == ["A", "B", "X", "Y"]


def test_linux_hidapi_device_selection_and_probe(monkeypatch):
	monkeypatch.setattr(dialog, "sys", SimpleNamespace(platform="linux"))
	monkeypatch.setattr(dialog, "evdev", SimpleNamespace(list_devices=lambda: []))
	info = {
		"path": b"linux-hidraw",
		"vendor_id": 0x1234,
		"product_id": 0x5678,
		"product_string": "USB Gamepad",
		"usage_page": 1,
		"usage": 5,
	}
	monkeypatch.setattr(dialog, "hid", SimpleNamespace(enumerate=lambda: [info]))
	registration = object.__new__(dialog.ControllerRegistration)
	registration.app = SimpleNamespace(config={"drivers": {"hidapi": True}})
	registration._gamepad_icon = "gamepad-icon"
	registration._other_icon = "other-icon"
	devices = []
	widgets = {"lstDevices": devices, "cbShowAllDevices": SimpleNamespace(get_active=lambda: False)}
	registration.builder = SimpleNamespace(get_object=widgets.get)
	registration.refresh_devices()
	assert len(devices) == 1
	assert devices[0][1] == "USB Gamepad (HIDAPI)"
	dev = registration._open_selected_device(devices[0][0])
	assert dev.input_backend == "hidapi"
	started = []

	def tester(driver, path):
		assert driver == "hidapi"
		assert path == dev.path
		return SimpleNamespace(driver=driver, connect=lambda *args: 1, start=lambda: started.append(path))

	monkeypatch.setattr(dialog, "Tester", tester)
	registration.set_hid_enabled = lambda enabled: None
	registration.prepare_registration(dev)
	assert started == [dev.path]
	assert not registration.load_sdl_mappings()
	# Disabling the optional backend removes its devices from the wizard.
	registration.app.config["drivers"]["hidapi"] = False
	registration.refresh_devices()
	assert devices == []
