from unittest.mock import Mock, call, patch

from scc.constants import HapticPos
from scc.controller import HapticData
from scc.drivers import ds5drv


def test_hidraw_driver_registers_all_dualsense_products() -> None:
	daemon: Mock = Mock()
	monitor = daemon.get_device_monitor.return_value

	driver = ds5drv.DS5HidRawDriver(daemon, {})

	assert monitor.add_callback.call_args_list == [
		call("bluetooth", ds5drv.VENDOR_ID, product_id, driver.make_bt_hidraw_callback, None)
		for product_id in ds5drv.PRODUCT_IDS
	]


@patch.object(ds5drv, "DS5HidRawDriver")
@patch.object(ds5drv, "register_hotplug_device")
def test_init_registers_usb_products(register_hotplug_device: Mock, hidraw_driver: Mock) -> None:
	daemon: Mock = Mock()
	config = {"drivers": {"hiddrv": True, "evdevdrv": False}}

	assert ds5drv.init(daemon, config)
	assert [args.args[2] for args in register_hotplug_device.call_args_list] == list(ds5drv.PRODUCT_IDS)
	hidraw_driver.assert_called_once_with(daemon, config)


@patch.object(ds5drv, "HAVE_EVDEV", True)
@patch.object(ds5drv, "register_hotplug_device")
def test_init_registers_evdev_bluetooth_products(register_hotplug_device: Mock) -> None:
	daemon: Mock = Mock()
	monitor = daemon.get_device_monitor.return_value
	config = {"drivers": {"hiddrv": False, "evdevdrv": True}}

	assert ds5drv.init(daemon, config)
	assert [args.args[2] for args in register_hotplug_device.call_args_list] == list(ds5drv.PRODUCT_IDS)
	assert [args.args[2] for args in monitor.add_callback.call_args_list] == list(ds5drv.PRODUCT_IDS)


def test_hidraw_turnoff_disconnects_bluetooth_link() -> None:
	controller = object.__new__(ds5drv.DS5HidRawController)
	controller.daemon = Mock()
	controller.syspath = "/sys/devices/bluetooth/hci0/hci0:50"

	controller.turnoff()

	controller.daemon.get_device_monitor.return_value.disconnect_bluetooth.assert_called_once_with(controller.syspath)


def test_hidraw_read_error_disconnects_without_escaping() -> None:
	controller = object.__new__(ds5drv.DS5HidRawController)
	controller._device_file = Mock()
	controller._device_file.read.side_effect = OSError(5, "Input/output error")
	controller._fileno = 12
	controller._poller = Mock()
	controller.daemon = Mock()
	controller._closed = False

	controller._input()

	controller._poller.unregister.assert_called_once_with(12)
	controller.daemon.remove_controller.assert_called_once_with(controller)
	controller._device_file.close.assert_called_once_with()

	controller.close("/sys/devices/bluetooth/hci0/hci0:50", ds5drv.VENDOR_ID, ds5drv.PRODUCT_ID)

	controller._poller.unregister.assert_called_once_with(12)
	controller.daemon.remove_controller.assert_called_once_with(controller)
	controller._device_file.close.assert_called_once_with()


def make_evdev_controller() -> ds5drv.DS5EvdevController:
	controller = object.__new__(ds5drv.DS5EvdevController)
	controller.device = Mock()
	controller.device.upload_effect.return_value = 7
	controller._feedback_effect_id = None
	return controller
