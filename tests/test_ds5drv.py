from unittest.mock import Mock, call, patch

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
