"""Periodic HID discovery must not block input on the daemon thread."""

from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scc.drivers import ds4drv_hidapi, ds5drv_hidapi, hidapi


@pytest.mark.parametrize("module,driver_class", [
	(ds4drv_hidapi, ds4drv_hidapi.DS4Driver),
	(ds5drv_hidapi, ds5drv_hidapi.DualSenseDriver),
	(hidapi, hidapi.HIDAPIDriver),
])
def test_slow_discovery_does_not_block_input(monkeypatch, module, driver_class):
	started, release = Event(), Event()
	main_thread = get_ident()

	def enumerate_devices(*args):
		assert get_ident() != main_thread
		started.set()
		assert release.wait(5)
		return []

	monkeypatch.setattr(module, "hid", SimpleNamespace(enumerate=enumerate_devices))
	driver = driver_class(Mock())
	if module is hidapi:
		driver.configs[(1, 2)] = ("mapping.json", {})
	controller = Mock()
	driver.controllers[b"existing"] = controller
	try:
		driver.mainloop()
		assert started.wait(2)
		pending = driver._scan_result
		driver.mainloop()
		assert controller.poll.call_count == 2
		assert driver._scan_result is pending
		controller.close.assert_not_called()
	finally:
		release.set()
	pending.result(timeout=2)
	driver.mainloop()
	controller.close.assert_called_once()


def test_no_generic_discovery_without_registrations(monkeypatch):
	enumerate_devices = Mock(side_effect=AssertionError("Unnecessary enumeration"))
	monkeypatch.setattr(hidapi, "hid", SimpleNamespace(enumerate=enumerate_devices))
	driver = hidapi.HIDAPIDriver(Mock())
	driver.scan()
	driver.mainloop()
	enumerate_devices.assert_not_called()
