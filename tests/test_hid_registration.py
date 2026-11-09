"""Exercise raw HID registration without requiring a physical controller."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scc.constants import SCButtons, STICK_PAD_MAX
from scc.device_config import DEVICE_CONFIG_VERSION
from scc.lib.hid_registration import RawHIDInput, map_inputs, path_token, registration_device

# Eight buttons, two signed eight-bit axes, and an eight-direction hat.
DESCRIPTOR = bytes.fromhex(
	"05010905a101050919012908150025017501950881020501093009311581257f750895028102093915002507750495018142750495018101c0"
)

# Captured DualSense USB: X,Y,Z,Rz,Rx,Ry in wire order, followed by the hat.
DUALSENSE_DESCRIPTOR = bytes.fromhex(
	"05010905a1018501093009310932093509330934150026ff007508950681020600ff09209501810205010939150025073500"
	"463b016514750495018142650005091901290f150025017501950f81020600ff0921950d81020600ff0922150026ff007508"
	"9534810285020923952f9102850509339528b10285080934952fb102850909249513b102850a0925951ab102850b09419529"
	"b102850c09429529b10285200926953fb102852109279504b10285220940953fb10285800928953fb10285810929953fb102"
	"8582092a9509b1028583092b953fb1028584092c953fb1028585092d9502b10285a0092e9501b10285e0092f953fb10285f0"
	"0930953fb10285f10931953fb10285f20932950fb10285f40935953fb10285f509369503b102c0"
)


def test_dualsense_database_mapping_separates_hat_and_triggers():
	raw = RawHIDInput(DUALSENSE_DESCRIPTOR)
	config = raw.sdl_mapping({"vendor_id": 0x054C, "product_id": 0x0CE6}, Path(__file__).parents[1] / "gamecontrollerdb.txt")
	assert config is not None
	assert {code: axis["axis"] for code, axis in config["axes"].items()} == {
		"0": "lstick_x", "1": "lstick_y", "2": "rstick_x", "3": "rstick_y",
		"4": "ltrig", "5": "rtrig", "6": "dpad_x", "7": "dpad_y",
	}
	# Right on the hat; sticks centered, triggers released.
	report = bytearray(64)
	report[:9] = bytes([1, 128, 128, 128, 128, 0, 0, 0, 2])
	assert raw.read(report)
	state = map_inputs(raw, config)
	assert state["dpad_x"] == STICK_PAD_MAX
	assert state["dpad_y"] == state["ltrig"] == state["rtrig"] == 0
	# Neutral hat, full L2/R2 and Cross (HID button 2).
	report[5:7] = bytes([255, 255])
	report[8] = 8 | 0x20
	assert raw.read(report)
	state = map_inputs(raw, config)
	assert state["dpad_x"] == state["dpad_y"] == 0
	assert state["ltrig"] == state["rtrig"] == 255
	assert state["buttons"] & SCButtons.A


@pytest.mark.parametrize("platform,guid", [
	("Linux", "03000000341200007856000000000000"),
	("Windows", "03000000341200007856000000006800"),
])
def test_raw_hid_mapping_rejects_other_numbering(tmp_path, platform, guid):
	db = tmp_path / "db.txt"
	db.write_text(f"{guid},Test,a:b0,leftx:a0,platform:{platform},\n")
	assert RawHIDInput(DESCRIPTOR).sdl_mapping({"vendor_id": 0x1234, "product_id": 0x5678}, db) is None


@pytest.mark.parametrize("binding", ["a99", "+a0", "b99", "h9.1"])
def test_raw_hid_mapping_rejects_untranslatable_bindings(tmp_path, binding):
	db = tmp_path / "db.txt"
	db.write_text(f"03000000341200007856000000000000,Test,a:b0,leftx:{binding},platform:Windows,\n")
	assert RawHIDInput(DESCRIPTOR).sdl_mapping({"vendor_id": 0x1234, "product_id": 0x5678}, db) is None


def test_raw_hid_mapping_inversion_and_button_dpad(tmp_path):
	db = tmp_path / "db.txt"
	db.write_text("03000000341200007856000000000000,Test,leftx:a0~,dpup:b0,lefttrigger:b1,platform:Windows,\n")
	raw = RawHIDInput(DESCRIPTOR)
	config = raw.sdl_mapping({"vendor_id": 0x1234, "product_id": 0x5678}, db)
	assert raw.read(bytes([3, 127, 0, 8]))
	state = map_inputs(raw, config)
	assert state["lstick_x"] == -STICK_PAD_MAX
	assert state["dpad_y"] == STICK_PAD_MAX
	assert state["ltrig"] == 255


def test_database_numbering_uses_usages_not_wire_order(tmp_path):
	# Buttons arrive as usage 3,1,2; axes as Y,X.
	descriptor = bytes.fromhex(
		"05010905a101050909030901090215002501750195038102750595018101"
		"050109310930150026ff00750895028102c0"
	)
	db = tmp_path / "db.txt"
	db.write_text("03000000341200007856000000000000,Test,a:b0,b:b2,leftx:a0,lefty:a1,platform:Windows,\n")
	config = RawHIDInput(descriptor).sdl_mapping({"vendor_id": 0x1234, "product_id": 0x5678}, db)
	assert config["buttons"] == {"289": "A", "288": "B"}
	assert config["axes"]["0"]["axis"] == "lstick_y"
	assert config["axes"]["1"]["axis"] == "lstick_x"


def configuration():
	return {
		"version": DEVICE_CONFIG_VERSION,
		"input_backend": "hidapi",
		"buttons": {"288": "A", "289": "RT"},
		"axes": {
			"0": {"axis": "lstick_x", "min": -127, "max": 127, "deadzone": 4},
			"1": {"axis": "rstick_y", "min": 127, "max": -127},
			"2": {"axis": "dpad_x", "min": -1, "max": 1},
			"3": {"axis": "dpad_y", "min": 1, "max": -1},
		},
		"dpads": {"290": {"axis": "ltrig", "positive": True}},
		"gui": {"background": "x360"},
	}


def test_signed_axes_hat_neutral_and_manual_mapping():
	raw = RawHIDInput(DESCRIPTOR)
	assert list(raw.buttons) == list(range(288, 296))
	assert list(raw.axes) == [0, 1, 2, 3]
	assert raw.read(bytes([3, 127, 129, 1]))
	state = map_inputs(raw, configuration())
	assert state["buttons"] == int(SCButtons.A | SCButtons.RT)
	assert state["rtrig"] == 255
	assert state["lstick_x"] == STICK_PAD_MAX
	assert state["rstick_y"] == STICK_PAD_MAX
	assert state["dpad_x"] == STICK_PAD_MAX
	assert state["dpad_y"] == STICK_PAD_MAX
	assert raw.read(bytes([0, 1, 0, 8]))
	state = map_inputs(raw, configuration())
	assert state["buttons"] == state["lstick_x"] == state["dpad_x"] == state["dpad_y"] == 0
	assert state.get("rtrig", 0) == 0
	assert raw.read(bytes([4, 0, 0, 8]))
	assert map_inputs(raw, configuration())["ltrig"] == 255


def test_separate_report_ids_preserve_buttons_and_reject_short_reports():
	descriptor = bytes.fromhex("05010905a10185010509190129081500250175019508810285020501093009311581257f750895028102c0")
	raw = RawHIDInput(descriptor)
	assert raw.read(bytes([1, 1]))
	assert raw.read(bytes([2, 127, 129]))
	assert raw.buttons[288]
	assert raw.axes == {0: 127, 1: -127}
	assert not raw.read(bytes([2, 0]))
	assert not raw.read(bytes([3, 0, 0]))
	assert raw.buttons[288]


def test_hidapi_paths_are_lossless_and_safe_command_arguments():
	path = b"\\\\?\\hid#vid_1234&pid_abcd#something with spaces"
	device = registration_device({"path": path, "vendor_id": 0x1234, "product_id": 0xABCD})
	assert bytes.fromhex(device.path) == path
	assert device.path == path_token(path)
	assert device.info.product == 0xABCD


def test_descriptor_global_push_pop_restores_axis_range():
	descriptor = bytes.fromhex("05010905a1011500257f75089501a41581257f09308102b409318102c0")
	raw = RawHIDInput(descriptor)
	assert raw.read(bytes([255, 127]))
	assert raw.axes == {0: -1, 1: 127}
	assert [field.minimum for field in raw.fields] == [-127, 0]


@pytest.mark.parametrize("autodetect,prefix", [(True, "hid"), (False, "hidapi")])
def test_registered_unknown_controller_is_loaded_polled_and_removed(tmp_path, monkeypatch, autodetect, prefix):
	from scc.drivers.windows import hidapi

	class Device:
		def __init__(self):
			self.reports = [[3, 127, 129, 1], [0, 0, 0, 8]]
			self.closed = False

		def open_path(self, path):
			assert path == b"unknown-controller"

		def set_nonblocking(self, value):
			pass

		def get_report_descriptor(self):
			return DESCRIPTOR

		def read(self, size):
			return self.reports.pop(0) if self.reports else []

		def close(self):
			self.closed = True

	device = Device()
	info = {"path": b"unknown-controller", "vendor_id": 0x1234, "product_id": 0x5678}
	monkeypatch.setattr(hidapi, "hid", SimpleNamespace(enumerate=lambda: [info], device=lambda: device))
	monkeypatch.setattr(hidapi, "get_config_path", lambda: str(tmp_path))
	monkeypatch.setattr(hidapi, "load_gamecontroller_mapping", lambda *args: None)
	devices = tmp_path / "devices"
	devices.mkdir()
	filename = devices / f"{prefix}-1234_5678-Unknown.json"
	filename.write_text(json.dumps(configuration()))
	active = []
	daemon = SimpleNamespace(add_controller=active.append, remove_controller=active.remove, get_active_ids=lambda: [])
	driver = hidapi.WindowsHIDDriver(daemon, autodetect=autodetect)
	driver.start()
	assert len(active) == 1
	controller = active[0]
	assert controller.get_gui_config_file() == str(filename)
	events = []
	controller.mapper = SimpleNamespace(input=lambda controller, old, new: events.append((bytes(old), bytes(new))))
	controller.poll()
	assert len(events) == 2
	assert events[1][0] == events[0][1]
	assert controller._decoder.state.buttons == 0
	assert controller._decoder.state.rtrig == 0
	# Saving revised assignments takes effect on rescan without restarting SCC.
	config = configuration()
	config["buttons"]["288"] = "B"
	filename.write_text(json.dumps(config))
	driver.rescan()
	assert len(active) == 1
	assert active[0] is not controller
	assert active[0].config["buttons"]["288"] == "B"
	filename.unlink()
	driver.rescan()
	assert active == []
	assert device.closed


def test_optional_linux_backend_never_autodetects(monkeypatch):
	from scc.drivers.linux import hidapi
	from scc.drivers.windows import hidapi as windows_hidapi

	info = {"path": b"mapped-device", "vendor_id": 0x1234, "product_id": 0x5678}
	monkeypatch.setattr(windows_hidapi, "hid", SimpleNamespace(enumerate=lambda: [info]))

	def database_lookup(*args):
		pytest.fail("Linux HIDAPI backend must not look up automatic mappings")

	monkeypatch.setattr(windows_hidapi, "load_gamecontroller_mapping", database_lookup)
	callbacks = []
	daemon = SimpleNamespace(
		add_mainloop=callbacks.append, add_on_exit=callbacks.append, add_on_rescan=callbacks.append
	)
	monkeypatch.setattr(hidapi, "_driver", None)
	assert hidapi.init(daemon, {})
	assert not hidapi._driver.autodetect
	assert len(callbacks) == 3
	hidapi._driver.scan()
	assert hidapi._driver.controllers == {}


def test_optional_linux_backend_handles_missing_dependency(monkeypatch):
	from scc.drivers.linux import hidapi

	monkeypatch.setattr(hidapi.hidapi, "hid", None)
	assert not hidapi.init(SimpleNamespace(), {})
