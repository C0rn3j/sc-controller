from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, TRIGGER_MAX, TRIGGER_MIN
from unittest.mock import Mock

from scc.drivers.evdevdrv import AxisCalibrationData, EvdevController, EvdevDriver, parse_axis
from scc.tools import clamp


def calibrated_value(calibration: AxisCalibrationData, value: int) -> float:
	value = (float(value) * calibration.scale) + calibration.offset
	return clamp(
		calibration.clamp_min,
		int(value * calibration.clamp_max),
		calibration.clamp_max,
	)


def test_parse_unsigned_trigger_axis() -> None:
	calibration = parse_axis({"axis": "ltrig", "min": 0, "max": 255})

	assert calibration.clamp_min == TRIGGER_MIN
	assert calibration.clamp_max == TRIGGER_MAX
	assert calibrated_value(calibration, 0) == 0
	assert calibrated_value(calibration, 128) == 128
	assert calibrated_value(calibration, 255) == 255


def test_parse_signed_trigger_axis() -> None:
	calibration = parse_axis({"axis": "rtrig", "min": -32767, "max": 32767})

	assert calibrated_value(calibration, -32767) == 0
	assert calibrated_value(calibration, 0) == 127
	assert calibrated_value(calibration, 32767) == 255


def test_parse_stick_axis_remains_bipolar() -> None:
	calibration = parse_axis({"axis": "stick_x", "min": 0, "max": 255})

	assert calibration.clamp_min == STICK_PAD_MIN
	assert calibration.clamp_max == STICK_PAD_MAX
	# Bipolar scaling uses the positive magnitude for both endpoints.
	assert calibrated_value(calibration, 0) == -STICK_PAD_MAX
	assert calibrated_value(calibration, 255) == STICK_PAD_MAX


def test_get_event_node_accepts_kernel_event_device() -> None:
	assert EvdevDriver.get_event_node("/sys/devices/input/input1/event17") == "/dev/input/event17"


def test_get_event_node_rejects_event_count_attribute() -> None:
	assert EvdevDriver.get_event_node("/sys/devices/wakeup/wakeup1/event_count") is None


def test_generic_bluetooth_turnoff_disconnects_bluez_device() -> None:
	controller = object.__new__(EvdevController)
	controller.daemon = Mock()
	controller.device = Mock()
	controller.device.info.bustype = controller.ECODES.BUS_BLUETOOTH
	controller.device.uniq = "A0:5A:5D:87:82:17"
	monitor = controller.daemon.get_device_monitor.return_value
	monitor.get_bluetooth_syspath.return_value = "hci0:50"

	controller.turnoff()

	monitor.get_bluetooth_syspath.assert_called_once_with(controller.device.uniq)
	monitor.disconnect_bluetooth.assert_called_once_with("hci0:50")


def test_generic_wired_turnoff_does_not_disconnect() -> None:
	controller = object.__new__(EvdevController)
	controller.daemon = Mock()
	controller.device = Mock()
	controller.device.info.bustype = controller.ECODES.BUS_USB

	controller.turnoff()

	controller.daemon.get_device_monitor.assert_not_called()
