"""Steam Controller (2015) HIDAPI packets and transport lifecycle."""

import struct
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scc.constants import HapticPos, SCButtons
from scc.controller import HapticData
from scc.drivers import sc_by_bt_hidapi, sc_by_cable_hidapi, sc_dongle_hidapi
from scc.lib import sc_hidapi as sc


@pytest.fixture
def backend(monkeypatch):
	devices = []

	def make_device():
		device = Mock()
		device.read.return_value = []
		device.send_feature_report.side_effect = len
		device.get_feature_report.return_value = b"\x00\xae\x15\x01ABCDEFGHIJKL" + bytes(49)
		devices.append(device)
		return device

	monkeypatch.setattr(sc, "hid", SimpleNamespace(device=make_device, enumerate=lambda *args: []))
	active = []
	daemon = Mock()
	daemon.get_active_ids.side_effect = lambda: [c.get_id() for c in active]
	daemon.add_controller.side_effect = active.append
	daemon.remove_controller.side_effect = active.remove
	return daemon, devices


def usb_frame(status=1, buttons=0):
	report = bytearray(64)
	report[0] = 1
	report[2] = status
	struct.pack_into("<I", report, 7, buttons)
	return bytes(report)


def bt_reports(kind, data):
	payload = struct.pack("<H", kind) + data
	chunks = [payload[i:i + 18].ljust(18, b"\x00") for i in range(0, len(payload), 18)]
	return [bytes((3, i | (0x40 if i == len(chunks) - 1 else 0x80))) + chunk for i, chunk in enumerate(chunks)]


def open_slot(daemon, *, wired=False, bluetooth=False, path=b"controller", interface=1):
	driver = sc.HIDDriver(daemon, 0x1106 if bluetooth else 0x1102 if wired else 0x1142, (interface,), wired=wired, bluetooth=bluetooth)
	driver._apply_scan({path: {"path": path, "interface_number": interface, "serial_number": "AA:BB:CC"}})
	return driver, driver.slots[path]


@pytest.mark.parametrize("wired", [False, True])
def test_usb_serial_config_input_feedback_and_leds(backend, wired):
	daemon, devices = backend
	driver, slot = open_slot(daemon, wired=wired)
	daemon.add_controller.assert_not_called()
	slot._on_input(usb_frame(buttons=int(SCButtons.A)))
	slot._timer()
	controller = slot.controller
	assert controller.get_id() == ("sc" if wired else "") + "ABCDEFGHIJKL"
	daemon.add_controller.assert_called_once_with(controller)
	controller.mapper = Mock()
	slot._on_input(usb_frame(buttons=int(SCButtons.B)))
	slot._next_timer = 0
	slot._timer()
	old, new = controller.mapper.input.call_args.args[1:]
	assert old.buttons & SCButtons.A
	assert new.buttons & SCButtons.B
	controller.configure(idle_timeout=0x1234, enable_gyros=True, led_level=75)
	reports = [call.args[0] for call in devices[0].send_feature_report.call_args_list]
	assert all(len(report) == 65 and report[0] == 0 for report in reports)
	assert reports[-2][1:6] == bytes((0x87, 0x15, 0x32, 0x34, 0x12))
	assert reports[-2][19] == 0x1C
	assert reports[-1][1:5] == bytes((0x87, 3, 0x2D, 75))
	controller.feedback(HapticData(HapticPos.LEFT, amplitude=0x1234, period=3, count=4))
	assert devices[0].send_feature_report.call_args.args[0] == (b"\x00" + struct.pack("<BBBHHH", 0x8F, 7, HapticPos.LEFT, 0x1234, 3, 4)).ljust(65, b"\x00")
	controller.set_led_level(42)
	assert devices[0].send_feature_report.call_args.args[0][1:5] == bytes((0x87, 3, 0x2D, 42))
	driver.close()
	devices[0].close.assert_called_once()
	daemon.remove_controller.assert_called_once_with(controller)


def test_receiver_hotplug_and_slots_are_independent(backend):
	daemon, devices = backend
	driver = sc.HIDDriver(daemon, 0x1142, (1, 2, 3, 4))
	driver._apply_scan({bytes((i,)): {"path": bytes((i,)), "interface_number": i} for i in range(1, 5)})
	for slot in driver.slots.values():
		slot._on_input(usb_frame())
	assert len({slot.controller.get_id() for slot in driver.slots.values()}) == 4
	slot = driver.slots[b"\x01"]
	controller = slot.controller
	slot._on_input(usb_frame(status=3))
	assert slot.controller is None
	assert len(driver.slots) == 4
	assert all(s.controller for p, s in driver.slots.items() if p != b"\x01")
	slot._on_input(usb_frame())
	assert slot.controller is not controller
	devices[0].read.side_effect = OSError("unplugged")
	slot.poll()
	assert len(driver.slots) == 3


def test_bluetooth_commands_and_input(backend):
	daemon, devices = backend
	driver, slot = open_slot(daemon, bluetooth=True)
	controller = slot.controller
	assert controller.is_bluetooth()
	assert controller.get_type() == "scbt"
	assert controller.get_id() == "AABBCC"
	controller.configure(enable_gyros=True, led_level=60)
	reports = [call.args[0] for call in devices[0].send_feature_report.call_args_list]
	assert all(len(report) == 21 and report[:2] == b"\x03\xc0" for report in reports)
	assert reports[-2][2:5] == b"\x87\x0f\x18"
	assert reports[-2][17] == 0x1C
	controller.set_led_level(70)
	assert devices[0].send_feature_report.call_args.args[0][2:6] == bytes((0x87, 3, 0x2D, 70))
	controller.mapper = Mock()
	for report in bt_reports(0x10 | 0x80, b"\x80\x00\x00" + struct.pack("<hh", 12000, -23000)):
		slot._on_input(report)
	state = controller.mapper.input.call_args.args[2]
	assert state.buttons == SCButtons.A
	assert (state.lstick_x, state.lstick_y) == (12000, -23000)
	controller.feedback(HapticData(HapticPos.RIGHT, amplitude=128))
	assert devices[0].send_feature_report.call_args.args[0][:5] == b"\x03\xc0\x8f\x07\x00"


def test_bluetooth_partial_updates_and_fragmented_imu():
	decoder = sc.BluetoothDecoder()
	state = decoder.feed(bt_reports(0x10, b"\x80\x00\x00")[0])
	assert state.buttons == SCButtons.A
	values = tuple(range(-10, 0))
	reports = bt_reports(0x1800 | 0x20 | 0x100 | 0x200, b"\x7b\xea" + struct.pack("<4h10h", 1, 2, 3, 4, *values))
	for report in reports[:-1]:
		assert decoder.feed(report) is None
	state = decoder.feed(reports[-1])
	assert state.buttons == SCButtons.A
	assert (state.ltrig, state.rtrig) == (123, 234)
	assert (state.lpad_x, state.lpad_y, state.rpad_x, state.rpad_y) == (1, 2, 3, 4)
	assert tuple(getattr(state, name) for name in sc.BT_FIELDS[10:]) == values
	assert decoder.feed(bt_reports(0x5000, b"")[0]) is None
	assert decoder.state == state


def test_bluetooth_rejects_lost_fragments_and_truncated_updates():
	decoder = sc.BluetoothDecoder()
	reports = bt_reports(0x1800, bytes(20))
	assert decoder.feed(reports[1]) is None
	assert decoder.feed(reports[0]) is None
	assert decoder.feed(b"\x03\x42" + bytes(18)) is None  # missing segment 1
	assert decoder.feed(bt_reports(0x1800, b"")[0]) is None  # needs two segments
	assert decoder.state == sc.BT_NULL
	assert decoder.feed(b"\x03") is None


def test_serial_retry_and_ignore_serials(backend):
	daemon, devices = backend
	driver, slot = open_slot(daemon)
	devices[0].get_feature_report.return_value = b"\x00" + bytes(64)
	slot._on_input(usb_frame())
	daemon.add_controller.assert_not_called()
	devices[0].get_feature_report.return_value = b"\x00\xae\x15\x01ABCDEFGHIJKL" + bytes(49)
	slot._on_input(usb_frame())
	daemon.add_controller.assert_called_once()
	driver.close()
	driver.ignore_serials = True
	driver._apply_scan({b"other": {"path": b"other", "interface_number": 1}})
	slot = driver.slots[b"other"]
	slot._on_input(usb_frame())
	devices[-1].get_feature_report.assert_not_called()


def test_turnoff_and_wired_noop(backend, monkeypatch):
	daemon, devices = backend
	driver, slot = open_slot(daemon)
	slot._on_input(usb_frame())
	controller = slot.controller
	clock = Mock(return_value=1.0)
	monkeypatch.setattr(sc.time, "monotonic", clock)
	controller.turnoff()
	assert devices[0].send_feature_report.call_args.args[0][1:7] == b"\x9f\x04off!"
	assert slot.controller is None
	clock.return_value = 1.1
	slot._on_input(usb_frame())
	assert slot.controller is None
	clock.return_value = 2.0
	slot._on_input(usb_frame())
	assert slot.controller is not None
	driver, wired = open_slot(daemon, wired=True)
	wired._on_input(usb_frame())
	wired.controller.turnoff()
	assert wired.controller is not None


@pytest.mark.parametrize("module,legacy,pid", [
	(sc_dongle_hidapi, "sc_dongle", 0x1142),
	(sc_by_cable_hidapi, "sc_by_cable", 0x1102),
	(sc_by_bt_hidapi, "sc_by_bt", 0x1106),
])
def test_driver_selection(backend, monkeypatch, module, legacy, pid):
	daemon, _ = backend
	monkeypatch.setattr(sc.sys, "platform", "linux")
	assert not module.init(daemon, {"drivers": {legacy: True}})
	assert module.init(daemon, {"drivers": {legacy: False}})
	assert module._driver.product == pid
	daemon.add_mainloop.assert_called_once()
	daemon.add_on_exit.assert_called_once()
	daemon.add_on_rescan.assert_called_once()
	monkeypatch.setattr(sc, "hid", None)
	assert not module.init(Mock(), {"drivers": {legacy: False}})


def test_import_without_linux_dependencies():
	subprocess.run([sys.executable, "-c", '''
import sys
for name in ("usb1", "evdev", "scc.drivers.usb", "scc.drivers.linux.sc_dongle", "scc.drivers.linux.sc_by_bt"):
    sys.modules[name] = None
from scc.drivers import sc_dongle_hidapi, sc_by_cable_hidapi, sc_by_bt_hidapi
'''], check=True)


def test_cable_idle_timer_and_input_coalescing(backend, monkeypatch):
	daemon, _ = backend
	clock = Mock(return_value=1.0)
	monkeypatch.setattr(sc.time, "monotonic", clock)
	driver, slot = open_slot(daemon, wired=True)
	slot._on_input(usb_frame(buttons=int(SCButtons.A)))
	slot.controller.mapper = Mock()
	slot._on_input(usb_frame(buttons=int(SCButtons.B)))
	slot._timer()
	mapper = slot.controller.mapper
	assert mapper.input.call_args.args[2].buttons == SCButtons.B
	slot._timer()
	mapper.generate_events.assert_not_called()
	clock.return_value = 1.02
	slot._timer()
	mapper.generate_events.assert_called_once()
	mapper.generate_feedback.assert_called_once()


def test_failed_open_and_partial_command_close_resources(backend):
	daemon, devices = backend
	driver = sc.HIDDriver(daemon, 0x1142, (1,))
	original = sc.hid.device

	def failed_open():
		device = original()
		device.set_nonblocking.side_effect = OSError("open failed")
		return device

	sc.hid.device = failed_open
	driver._apply_scan({b"bad": {"path": b"bad", "interface_number": 1}})
	assert not driver.slots
	devices[0].close.assert_called_once()
	sc.hid.device = original
	driver._apply_scan({b"good": {"path": b"good", "interface_number": 1}})
	devices[-1].send_feature_report.side_effect = lambda report: len(report) - 1
	driver.slots[b"good"].poll()  # empty read is harmless
	devices[-1].read.side_effect = [usb_frame()]
	driver.slots[b"good"].poll()
	assert not driver.slots
	devices[-1].close.assert_called_once()
	daemon.add_controller.assert_not_called()


def test_periodic_discovery_does_not_block_input(backend, monkeypatch):
	from threading import Event, get_ident

	daemon, devices = backend
	driver, slot = open_slot(daemon)
	started, release = Event(), Event()
	main_thread = get_ident()

	def enumerate_devices(*args):
		assert get_ident() != main_thread
		started.set()
		assert release.wait(5)
		return []

	monkeypatch.setattr(sc.hid, "enumerate", enumerate_devices)
	try:
		driver.mainloop()
		assert started.wait(2)
		pending = driver._scan_result
		driver.mainloop()
		assert devices[0].read.call_count == 2
		assert driver._scan_result is pending
	finally:
		release.set()
	pending.result(timeout=2)
	driver.mainloop()
	assert slot._closed


@pytest.mark.parametrize("product,interfaces", [(0x1142, (1, 2, 3, 4)), (0x1102, (2,))])
def test_discovery_filters_lizard_interfaces(backend, product, interfaces):
	daemon, _ = backend
	driver = sc.HIDDriver(daemon, product, interfaces)
	sc.hid.enumerate = lambda vendor, pid: [
		{"path": bytes((i,)), "interface_number": i, "usage_page": 0xFF00} for i in range(6)
	] + [{"path": b"keyboard", "interface_number": interfaces[0], "usage_page": 7}]
	assert {info["interface_number"] for info in driver._enumerate().values()} == set(interfaces)


def test_bluetooth_rotation_persists_across_partial_updates(backend):
	from math import pi

	daemon, _ = backend
	driver, slot = open_slot(daemon, bluetooth=True)
	controller = slot.controller
	controller.mapper = Mock()
	controller._input_rotation_l = pi / 2
	for report in bt_reports(0x100, struct.pack("<hh", 1000, 2000)):
		slot._on_input(report)
	state = controller.mapper.input.call_args.args[2]
	assert (state.lpad_x, state.lpad_y) == (-2000, 1000)
	for report in bt_reports(0x20, b"\x80\x00"):
		slot._on_input(report)
	state = controller.mapper.input.call_args.args[2]
	assert (state.lpad_x, state.lpad_y) == (-2000, 1000)
