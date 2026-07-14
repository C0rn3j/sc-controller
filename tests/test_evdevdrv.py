from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, TRIGGER_MAX, TRIGGER_MIN
from scc.drivers.evdevdrv import AxisCalibrationData, parse_axis
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
