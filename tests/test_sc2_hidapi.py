"""SC2 HIDAPI transport, independent receiver slots, and controller lifecycle."""

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scc.constants import HapticPos, SCButtons
from scc.controller import HapticData
from scc.drivers import sc2_hidapi
from scc.lib import sc2 as protocol


def frame(seq=1, buttons=0):
	report = bytearray(protocol.INPUT_SIZE)
	report[0:2] = bytes((0x42, seq))
	report[2:6] = buttons.to_bytes(4, "little")
	return bytes(report)


@pytest.fixture
def backend(monkeypatch):
	devices = []

	def make_device():
		device = Mock()
		device.read.return_value = []
		device.send_feature_report.side_effect = len
		device.write.side_effect = len
		devices.append(device)
		return device

	monkeypatch.setattr(sc2_hidapi, "hid", SimpleNamespace(device=make_device, enumerate=lambda *args: []))
	daemon = Mock()
	daemon.get_active_ids.return_value = []
	return sc2_hidapi.SC2Driver(daemon), devices


def open_slot(driver, path=b"slot", interface=2):
	driver._apply_scan({**{p: d.info for p, d in driver.devices.items()}, path: {
		"path": path, "product_id": protocol.PID_PUCK, "interface_number": interface, "serial_number": "puck",
	}})
	return driver.devices[path]


def test_input_and_configuration(backend):
	driver, devices = backend
	slot = open_slot(driver)
	driver.daemon.add_controller.assert_not_called()
	slot._on_input(b"\x43\x00")
	assert slot.controller is None
	slot._on_input(frame(buttons=protocol.SC2Button.A))
	controller = slot.controller
	assert controller.get_type() == "sc2"
	assert controller.get_gui_config_file() == "sc2-config.json"
	assert controller._old_state.buttons & SCButtons.A
	driver.daemon.add_controller.assert_called_once_with(controller)
	reports = [call.args[0] for call in devices[0].send_feature_report.call_args_list]
	assert reports == [
		b"\x01\x81\x00".ljust(64, b"\x00"),
		bytes.fromhex("01 87 0f 30 18 00 07 07 00 08 07 00 31 02 00 52 03").ljust(64, b"\x00"),
		b"\x01\x87\x03\x2d\x0a".ljust(64, b"\x00"),
	]
	controller.mapper = Mock()
	slot._on_input(frame(seq=100, buttons=protocol.SC2Button.LPADPRESS))
	controller.mapper.input.assert_called_once()
	assert controller.mapper.send_feedback.call_args.args[0].data[:2] == (HapticPos.LEFT, protocol.PAD_CLICK_PRESS)
	assert devices[0].send_feature_report.call_args.args[0] == reports[0]
	slot._on_input(frame(seq=101))
	assert controller.mapper.send_feedback.call_args.args[0].data[:2] == (HapticPos.LEFT, protocol.PAD_CLICK_RELEASE)


def test_haptics_use_interrupt_output_and_leds_use_features(backend):
	driver, devices = backend
	slot = open_slot(driver)
	slot._on_input(frame())
	controller = slot.controller
	controller.feedback(HapticData(HapticPos.BOTH, amplitude=0x4000))
	devices[0].write.assert_called_once_with(b"\x82\x02\x01\x80")
	controller.set_led_level(75)
	assert devices[0].send_feature_report.call_args.args[0] == b"\x01\x87\x03\x2d\x4b".ljust(64, b"\x00")


def test_four_slots_and_removal_are_independent(backend):
	driver, devices = backend
	slots = [open_slot(driver, bytes((i,)), 2 + i) for i in range(4)]
	for slot in slots:
		slot._on_input(frame())
	assert len({s.controller.get_id() for s in slots}) == 4
	first_controller = slots[0].controller
	devices[0].send_feature_report.side_effect = OSError("slot powered off")
	slots[0]._on_input(frame(seq=100))
	assert slots[0].controller is None
	driver.daemon.remove_controller.assert_called_once_with(first_controller)
	assert all(s.controller for s in slots[1:])
	assert len(driver.devices) == 4
	devices[0].send_feature_report.side_effect = len
	slots[0]._on_input(frame())
	assert slots[0].controller is not None
	assert slots[0].controller is not first_controller
	driver.close()
	assert not driver.devices
	for device in devices:
		device.close.assert_called_once()


def test_turnoff_suppresses_residual_frames(backend, monkeypatch):
	driver, devices = backend
	slot = open_slot(driver)
	slot._on_input(frame())
	controller = slot.controller
	clock = Mock(return_value=1.0)
	monkeypatch.setattr(sc2_hidapi.time, "monotonic", clock)
	controller.turnoff()
	assert devices[0].send_feature_report.call_args.args[0] == b"\x01\x9f\x04off!".ljust(64, b"\x00")
	clock.return_value = 1.1
	slot._on_input(frame())
	assert slot.controller is None
	clock.return_value = 2.0
	slot._on_input(frame())
	assert slot.controller is not None
	assert slot.controller is not controller


def test_failed_setup_does_not_register_controller(backend):
	driver, devices = backend
	slot = open_slot(driver)
	devices[0].send_feature_report.side_effect = lambda report: len(report) - 1
	slot._on_input(frame())
	assert slot.controller is None
	driver.daemon.add_controller.assert_not_called()
	devices[0].send_feature_report.side_effect = len
	slot._on_input(frame())
	assert slot.controller is not None


def test_read_error_closes_only_its_interface(backend):
	driver, devices = backend
	slot = open_slot(driver)
	slot._on_input(frame())
	devices[0].read.side_effect = OSError("unplugged")
	slot.poll()
	assert not driver.devices
	devices[0].close.assert_called_once()
	driver.daemon.remove_controller.assert_called_once()


def test_failed_open_closes_handle(backend):
	driver, devices = backend
	original = sc2_hidapi.hid.device

	def failing_device():
		device = original()
		device.set_nonblocking.side_effect = OSError("open failed")
		return device

	sc2_hidapi.hid.device = failing_device
	driver._apply_scan({b"slot": {"path": b"slot", "interface_number": 2}})
	assert not driver.devices
	devices[0].close.assert_called_once()


def test_discovery_filters_interfaces_and_transport(backend):
	driver, _ = backend

	def enumerate_devices(vendor, product):
		assert vendor == protocol.VENDOR_ID
		assert product in (protocol.PID_WIRED, protocol.PID_PUCK)
		return [{
			"path": f"{product}:{interface}:{page}", "interface_number": interface, "usage_page": page,
		} for interface in range(6) for page in (0, 0xFF00, 1)]

	sc2_hidapi.hid.enumerate = enumerate_devices
	found = driver._enumerate()
	assert len(found) == 10  # wired interface 0 and four Puck slots, two collection variants each
	assert all(info["usage_page"] != 1 for info in found.values())


def test_noquat_warns_once(backend, caplog):
	driver, _ = backend
	slot = open_slot(driver)
	slot._on_input(b"\x45")
	slot._on_input(b"\x45")
	assert caplog.text.count("NoQuat") == 1
	assert slot.controller is None


def test_driver_registration_and_backend_conflict(backend, monkeypatch):
	driver, _ = backend
	monkeypatch.setattr(sc2_hidapi.sys, "platform", "linux")
	assert not sc2_hidapi.init(driver.daemon, {"drivers": {"sc2": True}})
	driver.daemon.add_mainloop.assert_not_called()
	assert sc2_hidapi.init(driver.daemon, {"drivers": {"sc2": False}})
	driver.daemon.add_mainloop.assert_called_once()
	driver.daemon.add_on_exit.assert_called_once()
	driver.daemon.add_on_rescan.assert_called_once()
	monkeypatch.setattr(sc2_hidapi, "hid", None)
	assert not sc2_hidapi.init(Mock(), {"drivers": {"sc2": False}})


def test_import_without_linux_dependencies():
	script = '''
import sys
for name in ("usb1", "evdev", "scc.drivers.usb", "scc.drivers.linux.sc2", "scc.drivers.linux.sc_dongle"):
    sys.modules[name] = None
from scc.drivers import sc2_hidapi
assert sc2_hidapi.protocol.parse_input(bytes(54)) is None
'''
	subprocess.run([sys.executable, "-c", script], check=True)


def test_periodic_discovery_does_not_block_input(backend, monkeypatch):
	from threading import Event, get_ident

	driver, _ = backend
	slot = open_slot(driver)
	started, release = Event(), Event()
	main_thread = get_ident()

	def slow_enumeration(*args):
		assert get_ident() != main_thread
		started.set()
		assert release.wait(5)
		return []

	monkeypatch.setattr(sc2_hidapi.hid, "enumerate", slow_enumeration)
	try:
		driver.mainloop()
		assert started.wait(2)
		pending = driver._scan_result
		driver.mainloop()
		assert driver._scan_result is pending
		assert not slot._closed
	finally:
		release.set()
	pending.result(timeout=2)
	driver.mainloop()
	assert slot._closed


def test_enumeration_failure_keeps_existing_slots(backend, monkeypatch):
	driver, _ = backend
	slot = open_slot(driver)
	monkeypatch.setattr(sc2_hidapi.hid, "enumerate", Mock(side_effect=OSError("enumeration failed")))
	driver.scan()
	assert not slot._closed
	assert driver.devices[slot.path] is slot
