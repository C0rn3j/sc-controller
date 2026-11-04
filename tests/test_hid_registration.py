"""Exercise raw HID registration without requiring a physical controller."""

import json
from types import SimpleNamespace

from scc.constants import SCButtons, STICK_PAD_MAX
from scc.device_config import DEVICE_CONFIG_VERSION
from scc.lib.hid_registration import RawHIDInput, map_inputs, path_token, registration_device

# Eight buttons, two signed eight-bit axes, and an eight-direction hat.
DESCRIPTOR = bytes.fromhex(
	"05010905a101050919012908150025017501950881020501093009311581257f750895028102093915002507750495018142750495018101c0"
)


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


def test_registered_unknown_controller_is_loaded_polled_and_removed(tmp_path, monkeypatch):
	from scc.drivers.windows import hiddrv

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
	monkeypatch.setattr(hiddrv, "hid", SimpleNamespace(enumerate=lambda: [info], device=lambda: device))
	monkeypatch.setattr(hiddrv, "get_config_path", lambda: str(tmp_path))
	monkeypatch.setattr(hiddrv, "load_gamecontroller_mapping", lambda *args: None)
	devices = tmp_path / "devices"
	devices.mkdir()
	filename = devices / "hid-1234_5678-Unknown.json"
	filename.write_text(json.dumps(configuration()))
	active = []
	daemon = SimpleNamespace(add_controller=active.append, remove_controller=active.remove, get_active_ids=lambda: [])
	driver = hiddrv.WindowsHIDDriver(daemon)
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
