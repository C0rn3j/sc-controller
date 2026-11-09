"""DS4 HIDAPI protocol and lifecycle tests."""

import struct
import zlib
from types import SimpleNamespace

import pytest

pytest.importorskip("hid")

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, HapticPos, SCButtons
from scc.controller import HapticData
from scc.drivers.windows import ds4drv


class HIDDevice:
	def __init__(self):
		self.reports = []
		self.writes = []
		self.closed = False
		self.open_error = False

	def open_path(self, path):
		if self.open_error:
			raise OSError("Cannot open")
		self.path = path

	def set_nonblocking(self, enabled):
		assert enabled

	def read(self, size):
		if self.reports:
			report = self.reports.pop(0)
			if isinstance(report, Exception):
				raise report
			return report
		return []

	def write(self, report):
		self.writes.append(bytes(report))
		return len(report)

	def close(self):
		self.closed = True


@pytest.fixture
def controller(monkeypatch):
	device = HIDDevice()
	monkeypatch.setattr(ds4drv, "hid", SimpleNamespace(device=lambda: device))
	active = []
	daemon = SimpleNamespace(
		add_controller=active.append,
		remove_controller=active.remove,
		get_active_ids=lambda: [c.get_id() for c in active],
	)
	driver = ds4drv.DS4WindowsDriver(daemon)
	controller = ds4drv.WindowsDS4Controller(driver, {"path": b"usb-gamepad", "bus_type": 1})
	driver.controllers[controller.path] = controller
	return controller, device, driver, active


def usb_report():
	report = bytearray(64)
	report[:10] = bytes([1, 128, 128, 128, 128, 8, 0, 0, 0, 0])
	report[33] = 1  # One touch sample containing two finger slots.
	report[35] = report[39] = 0x80
	return report


def bluetooth_report(usb):
	report = bytearray(78)
	report[:3] = bytes([0x11, 0x80, 0])
	report[3:66] = usb[1:64]
	report[74:78] = zlib.crc32(b"\xa1" + report[:74]).to_bytes(4, "little")
	return report


@pytest.mark.parametrize("bluetooth", [False, True])
def test_usb_and_bluetooth_controls_motion_and_touch(controller, bluetooth):
	pad, device, _, _ = controller
	report = usb_report()
	report[1:5] = bytes([255, 0, 0, 255])
	report[5:10] = bytes([0xF1, 0xFF, 3, 91, 201])
	struct.pack_into("<6h", report, 13, 1000, -2000, 3000, -4000, 5000, -6000)
	report[35] = 1
	x, y = 1880, 940
	report[36:39] = bytes([x & 255, (x >> 8) | ((y & 15) << 4), y >> 4])
	device.reports = [bluetooth_report(report) if bluetooth else report]
	events = []
	pad.mapper = SimpleNamespace(input=lambda _, old, new: events.append((old, new)))
	pad.poll()
	assert len(events) == 1
	old, state = events[0]
	assert old.buttons == 0
	assert (state.lstick_x, state.lstick_y) == (STICK_PAD_MAX, STICK_PAD_MAX)
	assert (state.rstick_x, state.rstick_y) == (STICK_PAD_MIN, STICK_PAD_MIN)
	assert (state.dpad_x, state.dpad_y) == (STICK_PAD_MAX, STICK_PAD_MAX)
	assert (state.ltrig, state.rtrig) == (91, 201)
	for button in (
		SCButtons.A,
		SCButtons.B,
		SCButtons.X,
		SCButtons.Y,
		SCButtons.LB,
		SCButtons.RB,
		SCButtons.LT,
		SCButtons.RT,
		SCButtons.BACK,
		SCButtons.START,
		SCButtons.LSTICKPRESS,
		SCButtons.RSTICKPRESS,
		SCButtons.C,
		SCButtons.CPADPRESS,
		SCButtons.CPADTOUCH,
	):
		assert state.buttons & button
	assert (state.gpitch, state.gyaw, state.groll) == (1000, -2000, 3000)
	assert (state.accel_x, state.accel_y, state.accel_z) == (-4000, 5000, -6000)
	assert (state.q1, state.q2, state.q3) == (6000, 4000, -5000)
	assert (state.cpad_x, state.cpad_y) == (STICK_PAD_MAX - 1, STICK_PAD_MIN + 1)
	assert pad.get_gyro_enabled()
	assert pad.is_bluetooth() is bluetooth
	assert pad.get_type() == "ds4"
	assert pad.get_gui_config_file() == "ds4-config.json"


@pytest.mark.parametrize(
	"hat,x,y",
	[
		(0, 0, STICK_PAD_MAX),
		(2, STICK_PAD_MAX, 0),
		(4, 0, STICK_PAD_MIN),
		(6, STICK_PAD_MIN, 0),
		(8, 0, 0),
	],
)
def test_dpad_directions(controller, hat, x, y):
	pad, _, _, _ = controller
	report = usb_report()
	report[5] = hat
	pad._handle_report(report)
	assert (pad._old_state.dpad_x, pad._old_state.dpad_y) == (x, y)


def test_second_finger_and_touch_release(controller):
	pad, _, _, _ = controller
	report = usb_report()
	report[39] = 2
	pad._handle_report(report)
	assert pad._old_state.buttons & SCButtons.CPADTOUCH
	report[33] = 0
	pad._handle_report(report)
	assert not pad._old_state.buttons & SCButtons.CPADTOUCH


def test_simple_bluetooth_report_and_bad_packets(controller):
	pad, _, _, _ = controller
	pad._handle_report(usb_report()[:10])
	assert not pad.get_gyro_enabled()
	state = pad._old_state
	bad_crc = bluetooth_report(usb_report())
	bad_crc[10] ^= 1
	for invalid in (b"", b"\x01", b"\x02" + bytes(63), bad_crc, bluetooth_report(usb_report())[:-1]):
		pad._handle_report(invalid)
		assert pad._old_state is state


@pytest.mark.parametrize("bluetooth", [False, True])
def test_led_rumble_expiry_and_stop_preserve_each_other(controller, monkeypatch, bluetooth):
	pad, device, _, _ = controller
	pad._bluetooth = bluetooth
	now = [10.0]
	monkeypatch.setattr(ds4drv.time, "monotonic", lambda: now[0])
	pad.set_led_color(11, 22, 33)
	pad.feedback(HapticData(HapticPos.LEFT, amplitude=0x8000, period=0x8000, count=2))
	pad.feedback(HapticData(HapticPos.RIGHT, amplitude=0x4000, period=0x8000, count=4))
	offset = 2 if bluetooth else 0
	report = device.writes[-1]
	assert len(report) == (78 if bluetooth else 32)
	assert report[0] == (0x11 if bluetooth else 0x05)
	assert report[1 + offset] == 3
	assert report[4 + offset : 6 + offset] == bytes([128, 255])
	assert report[6 + offset : 9 + offset] == bytes([11, 22, 33])
	if bluetooth:
		assert report[1] == 0xC4
		assert int.from_bytes(report[74:78], "little") == zlib.crc32(b"\xa2" + report[:74])
	now[0] = 11.1
	pad.poll()
	assert device.writes[-1][4 + offset : 6 + offset] == bytes([128, 0])
	pad.feedback(HapticData(HapticPos.RIGHT, amplitude=0x8000, count=0))
	assert device.writes[-1][4 + offset : 6 + offset] == bytes([0, 0])
	assert device.writes[-1][6 + offset : 9 + offset] == bytes([11, 22, 33])


def test_close_and_read_error_release_device(controller):
	pad, device, driver, active = controller
	device.reports = [OSError("Disconnected")]
	pad.poll()
	pad.close()
	assert device.closed
	assert not driver.controllers
	assert active == []


def test_discovery_hotplug_filtering_failure_retry_and_cleanup(monkeypatch):
	device = HIDDevice()
	infos = []
	calls = []

	def enumerate_devices(vendor, product):
		calls.append((vendor, product))
		return [info for info in infos if info["product_id"] == product]

	monkeypatch.setattr(ds4drv, "hid", SimpleNamespace(device=lambda: device, enumerate=enumerate_devices))
	active = []
	daemon = SimpleNamespace(add_controller=active.append, remove_controller=active.remove, get_active_ids=lambda: [])
	driver = ds4drv.DS4WindowsDriver(daemon)
	info = {"path": b"pad", "product_id": 0x05C4, "usage_page": 1, "usage": 5}
	infos.extend([info, dict(info, path=b"keyboard", usage=6)])
	device.open_error = True
	driver.scan()
	assert active == []
	assert device.closed
	device.open_error = False
	device.closed = False
	driver.scan()
	assert len(active) == 1
	assert set(calls) == {(ds4drv.VENDOR_ID, pid) for pid in ds4drv.PRODUCT_IDS}
	driver.scan()
	assert len(active) == 1
	infos.clear()
	driver.scan()
	assert active == []
	assert driver.controllers == {}
	assert device.closed


def test_bluetooth_open_enables_extended_reports_and_unique_ids(monkeypatch):
	devices = [HIDDevice(), HIDDevice()]
	monkeypatch.setattr(ds4drv, "hid", SimpleNamespace(device=lambda: devices.pop(0)))
	active = []
	daemon = SimpleNamespace(
		add_controller=active.append,
		remove_controller=active.remove,
		get_active_ids=lambda: [p.get_id() for p in active],
	)
	driver = ds4drv.DS4WindowsDriver(daemon)
	first = ds4drv.WindowsDS4Controller(driver, {"path": b"bth-pad1", "bus_type": 2})
	second = ds4drv.WindowsDS4Controller(driver, {"path": b"bth-pad2", "bus_type": 2})
	assert first.get_id() == "ds4"
	assert second.get_id() == "ds4:1"
	assert first.device.writes[0][0] == second.device.writes[0][0] == 0x11
