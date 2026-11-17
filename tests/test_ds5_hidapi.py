"""Shared DualSense HIDAPI discovery and transport lifecycle."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scc.drivers import ds5drv_hidapi as ds5drv


@pytest.mark.parametrize("platform", ["linux", "win32", "darwin"])
@pytest.mark.parametrize("bluetooth", [False, True])
def test_shared_driver_lifecycle(monkeypatch, platform, bluetooth, caplog):
	device = Mock()
	device.read.return_value = []
	device.write.side_effect = lambda report: len(report)
	info = {
		"path": b"opaque-device-path",
		"bus_type": 2 if bluetooth else 1,
		"usage_page": 1,
		"usage": 5,
	}
	monkeypatch.setattr(ds5drv, "sys", SimpleNamespace(platform=platform))
	monkeypatch.setattr(ds5drv, "hid", SimpleNamespace(
		device=lambda: device,
		enumerate=lambda vendor, product: [info] if product == ds5drv.PRODUCT_IDS[0] else [],
	))
	daemon = Mock()
	daemon.get_active_ids.return_value = []
	assert ds5drv.init(daemon, {})
	daemon.add_on_rescan.assert_called_once_with(ds5drv._driver.scan)
	with caplog.at_level(logging.WARNING):
		ds5drv.start(daemon)
	assert ("HidHide" in caplog.text) == (platform == "win32")
	controller = ds5drv._driver.controllers[info["path"]]
	assert controller.is_bluetooth() == bluetooth
	device.open_path.assert_called_once_with(info["path"])
	controller.set_led_color(1, 2, 3)
	report = device.write.call_args.args[0]
	assert report[0] == (0x31 if bluetooth else 0x02)
	assert len(report) == (78 if bluetooth else 48)
	ds5drv._driver.mainloop()
	device.read.assert_called()
	ds5drv._driver.close()
	device.close.assert_called_once()
	daemon.remove_controller.assert_called_once_with(controller)


def test_missing_optional_hidapi(monkeypatch):
	monkeypatch.setattr(ds5drv, "hid", None)
	daemon = Mock()
	assert not ds5drv.init(daemon, {})
	daemon.add_mainloop.assert_not_called()


def test_failed_open_releases_device(monkeypatch):
	device = Mock()
	device.set_nonblocking.side_effect = OSError("Cannot enable nonblocking reads")
	monkeypatch.setattr(ds5drv, "hid", SimpleNamespace(device=lambda: device))
	driver = ds5drv.DualSenseDriver(Mock())
	with pytest.raises(OSError):
		ds5drv.DualSenseController(driver, {"path": b"device", "bus_type": 1})
	device.close.assert_called_once()
	driver.daemon.add_controller.assert_not_called()


@pytest.mark.parametrize("platform,expected", [("linux", False), ("darwin", False), ("win32", True)])
def test_windows_path_fallback(monkeypatch, platform, expected):
	monkeypatch.setattr(ds5drv, "sys", SimpleNamespace(platform=platform))
	assert ds5drv.DualSenseController._detect_bluetooth({"path": b"BTH-device"}) == expected
