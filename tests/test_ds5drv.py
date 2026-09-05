from unittest.mock import Mock, call, patch

from scc.constants import DUALSENSE_CPAD_X_MAX, DUALSENSE_CPAD_Y_MAX, STICK_PAD_MAX, STICK_PAD_MIN, HapticPos
from scc.controller import HapticData
from scc.drivers import ds5drv
from scc.drivers.hiddrv import AxisMode, AxisType


def test_dualsense_decoders_use_dedicated_dpad_axes() -> None:
	controller = object.__new__(ds5drv.DS5USBController)
	controller._load_hid_descriptor(None, None, None, None, None)

	assert controller._decoder.axes[AxisType.AXIS_DPAD_X].mode == AxisMode.HATSWITCH
	assert controller._decoder.axes[AxisType.AXIS_DPAD_X].data.hatswitch.button == 0
	assert controller._decoder.axes[AxisType.AXIS_LPAD_X].mode == AxisMode.DISABLED
	assert controller._decoder.axes[AxisType.AXIS_GPITCH].mode == AxisMode.DS4ACCEL
	assert controller._decoder.axes[AxisType.AXIS_GYAW].mode == AxisMode.DS4ACCEL
	assert controller._decoder.axes[AxisType.AXIS_GROLL].mode == AxisMode.DS4ACCEL

	hidraw = object.__new__(ds5drv.DS5BluetoothHIDRawController)
	hidraw._delta_time = 0
	hidraw._previous_quat = [1.0, 0.0, 0.0, 0.0]
	data = bytearray(64)
	data[9] = 2  # D-pad right
	state = hidraw._convert_input_data(data)
	assert not hasattr(state, "lpad_x")
	assert state.dpad_x > 0
	assert state.dpad_y == 0


def test_bluetooth_hidraw_gyro_preserves_sensor_directions() -> None:
	controller = object.__new__(ds5drv.DS5BluetoothHIDRawController)
	controller._delta_time = 0
	controller._previous_quat = [1.0, 0.0, 0.0, 0.0]
	data = bytearray(64)
	data[17:23] = (100).to_bytes(2, "little", signed=True) + (200).to_bytes(
		2, "little", signed=True
	) + (-300).to_bytes(2, "little", signed=True)

	state = controller._convert_input_data(data)

	assert state.gpitch == 100
	assert state.gyaw == 200
	assert state.groll == -300


def test_bluetooth_hidraw_touchpad_uses_full_normalized_range() -> None:
	controller = object.__new__(ds5drv.DS5BluetoothHIDRawController)
	controller._delta_time = 0
	controller._previous_quat = [1.0, 0.0, 0.0, 0.0]
	data = bytearray(64)

	state = controller._convert_input_data(data)
	assert (state.cpad_x, state.cpad_y) == (STICK_PAD_MIN, STICK_PAD_MAX)

	raw_x = DUALSENSE_CPAD_X_MAX
	raw_y = DUALSENSE_CPAD_Y_MAX
	data[35] = raw_x & 0xFF
	data[36] = ((raw_x >> 8) & 0x0F) | ((raw_y & 0x0F) << 4)
	data[37] = raw_y >> 4

	state = controller._convert_input_data(data)
	assert (state.cpad_x, state.cpad_y) == (STICK_PAD_MAX, STICK_PAD_MIN)


def test_hidraw_driver_registers_all_dualsense_products() -> None:
	daemon: Mock = Mock()
	monitor = daemon.get_device_monitor.return_value

	driver = ds5drv.DS5BluetoothHIDRawDriver(daemon, {})

	assert monitor.add_callback.call_args_list == [
		call("bluetooth", ds5drv.VENDOR_ID, product_id, driver.make_bt_hidraw_callback, None)
		for product_id in ds5drv.PRODUCT_IDS
	]


@patch.object(ds5drv, "DS5BluetoothHIDRawDriver")
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
	controller = object.__new__(ds5drv.DS5BluetoothHIDRawController)
	controller.daemon = Mock()
	controller.syspath = "/sys/devices/bluetooth/hci0/hci0:50"

	controller.turnoff()

	controller.daemon.get_device_monitor.return_value.disconnect_bluetooth.assert_called_once_with(controller.syspath)


def test_hidraw_read_error_disconnects_without_escaping() -> None:
	controller = object.__new__(ds5drv.DS5BluetoothHIDRawController)
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


def test_evdev_ds5_feedback_uploads_and_plays_rumble_effect() -> None:
	controller = make_evdev_controller()

	controller.feedback(HapticData(HapticPos.BOTH, amplitude=0x4000, period=1024, count=64))

	controller.device.upload_effect.assert_called_once()
	effect = controller.device.upload_effect.call_args.args[0]
	assert effect.type == controller.ECODES.FF_RUMBLE
	assert effect.u.ff_rumble_effect.strong_magnitude == 0x8000
	assert effect.u.ff_rumble_effect.weak_magnitude == 0x8000
	assert effect.ff_replay.length == 1000
	controller.device.write.assert_called_once_with(controller.ECODES.EV_FF, 7, 1)


def test_evdev_ds5_feedback_stop_stops_and_erases_effect() -> None:
	controller = make_evdev_controller()
	controller._feedback_effect_id = 7

	controller.feedback(HapticData(HapticPos.BOTH, amplitude=0, count=0))

	controller.device.write.assert_called_once_with(controller.ECODES.EV_FF, 7, 0)
	controller.device.erase_effect.assert_called_once_with(7)
	controller.device.upload_effect.assert_not_called()
	assert controller._feedback_effect_id is None
