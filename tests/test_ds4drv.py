import pytest
import struct
import zlib

# BT disconnect needs it
pytest.importorskip("gi", reason="PyGObject is required for GUI tests")

from unittest.mock import Mock

from scc.constants import HapticPos
from scc.controller import HapticData
from scc.drivers.ds4drv import (
	DS4_BT_OUTPUT_CRC_SEED,
	DS4_BT_OUTPUT_HW_CONTROL,
	DS4_BT_OUTPUT_REPORT_ID,
	DS4_BT_OUTPUT_REPORT_SIZE,
	DS4_BT_OUTPUT_VALID_MOTOR,
	DS4_USB_OUTPUT_ENDPOINT,
	DS4_USB_OUTPUT_REPORT_ID,
	DS4_USB_OUTPUT_REPORT_SIZE,
	DS4_USB_OUTPUT_VALID_MOTOR,
	DS4HIDController,
	DS4HIDRawController,
	DS4EvdevController,
)


def make_controller() -> DS4HIDController:
	controller = object.__new__(DS4HIDController)
	controller.handle = Mock()
	controller.mapper = Mock()
	controller._cmsg = []
	controller._rmsg = []
	controller._feedback_output = bytearray(DS4_USB_OUTPUT_REPORT_SIZE)
	controller._feedback_output[0] = DS4_USB_OUTPUT_REPORT_ID
	controller._feedback_output[1] = DS4_USB_OUTPUT_VALID_MOTOR
	controller._feedback_endpoint = DS4_USB_OUTPUT_ENDPOINT
	controller._feedback_pending = False
	controller._feedback_cancel_tasks = [None, None]
	return controller


def test_wired_ds4_feedback_writes_usb_output_report() -> None:
	controller = make_controller()

	controller.feedback(HapticData(HapticPos.BOTH, amplitude=0x8000))
	controller.flush()

	controller.handle.interruptWrite.assert_called_once()
	endpoint, report = controller.handle.interruptWrite.call_args.args
	assert endpoint == DS4_USB_OUTPUT_ENDPOINT
	assert len(report) == DS4_USB_OUTPUT_REPORT_SIZE
	assert report[0] == DS4_USB_OUTPUT_REPORT_ID
	assert report[1] == DS4_USB_OUTPUT_VALID_MOTOR
	assert report[4] == 0xFF
	assert report[5] == 0xFF
	assert report[6:9] == b"\x00\x00\x00"


def test_wired_ds4_feedback_clear_stops_selected_motor() -> None:
	controller = make_controller()
	scheduled = []
	controller.mapper.schedule.side_effect = (
		lambda duration, callback: scheduled.append((duration, callback)) or Mock()
	)

	controller.feedback(HapticData(HapticPos.RIGHT, amplitude=0x4000, period=1024, count=2))
	assert controller._feedback_output[4] == 0x7F
	assert controller._feedback_output[5] == 0
	assert scheduled[0][0] == 0.03125

	scheduled[0][1](controller.mapper)
	assert controller._feedback_output[4] == 0
	assert controller._feedback_pending


def test_wired_ds4_stop_is_written_without_scheduling() -> None:
	controller = make_controller()
	controller._feedback_output[4] = 0xFF
	old_task = Mock()
	controller._feedback_cancel_tasks[1] = old_task

	controller.feedback(HapticData(HapticPos.RIGHT, amplitude=0, period=0, count=0))
	controller.flush()

	old_task.cancel.assert_called_once_with()
	controller.mapper.schedule.assert_not_called()
	assert controller.handle.interruptWrite.call_args.args[1][4] == 0


def test_ds4_finds_interrupt_output_on_hid_interface() -> None:
	audio_endpoint = Mock()
	audio_endpoint.getAddress.return_value = 3
	audio_endpoint.getAttributes.return_value = 1
	audio = Mock()
	audio.getClass.return_value = 1
	audio.__iter__ = Mock(return_value=iter([audio_endpoint]))
	hid_endpoint = Mock()
	hid_endpoint.getAddress.return_value = 2
	hid_endpoint.getAttributes.return_value = 3
	hid = Mock()
	hid.getClass.return_value = 3
	hid.__iter__ = Mock(return_value=iter([hid_endpoint]))

	assert DS4HIDController._find_feedback_endpoint([[[audio], [hid]]]) == 2


def test_bluetooth_read_error_disconnects_without_escaping() -> None:
	controller = object.__new__(DS4HIDRawController)
	controller._hidrawdev = Mock()
	controller._device_file = Mock()
	controller._device_file.read.side_effect = OSError(5, "Input/output error")
	controller._packet_size = 78
	controller._fileno = 12
	controller._poller = Mock()
	controller.daemon = Mock()
	controller._closed = False

	controller._input()

	controller._poller.unregister.assert_called_once_with(12)
	controller.daemon.remove_controller.assert_called_once_with(controller)
	controller._device_file.close.assert_called_once_with()


def make_bluetooth_controller() -> DS4HIDRawController:
	controller = object.__new__(DS4HIDRawController)
	controller._hidrawdev = Mock()
	controller._device_file = Mock()
	controller.mapper = Mock()
	controller._feedback_output = bytearray(DS4_BT_OUTPUT_REPORT_SIZE)
	controller._feedback_output[0] = DS4_BT_OUTPUT_REPORT_ID
	controller._feedback_output[1] = DS4_BT_OUTPUT_HW_CONTROL
	controller._feedback_output[3] = DS4_BT_OUTPUT_VALID_MOTOR
	controller._feedback_cancel_tasks = [None, None]
	return controller


def test_bluetooth_ds4_feedback_writes_output_report_with_crc() -> None:
	controller = make_bluetooth_controller()

	controller.feedback(HapticData(HapticPos.BOTH, amplitude=0x8000))

	controller._device_file.write.assert_called_once()
	report = controller._device_file.write.call_args.args[0]
	assert len(report) == DS4_BT_OUTPUT_REPORT_SIZE
	assert report[0] == DS4_BT_OUTPUT_REPORT_ID
	assert report[1] == DS4_BT_OUTPUT_HW_CONTROL
	assert report[3] == DS4_BT_OUTPUT_VALID_MOTOR
	assert report[6] == 0xFF
	assert report[7] == 0xFF
	assert report[8:11] == b"\x00\x00\x00"
	assert struct.unpack_from("<I", report, DS4_BT_OUTPUT_REPORT_SIZE - 4)[0] == zlib.crc32(
		bytes((DS4_BT_OUTPUT_CRC_SEED,)) + report[:-4],
	)


def test_bluetooth_ds4_feedback_clear_writes_stopped_motor() -> None:
	controller = make_bluetooth_controller()
	scheduled = []
	controller.mapper.schedule.side_effect = (
		lambda duration, callback: scheduled.append((duration, callback)) or Mock()
	)

	controller.feedback(HapticData(HapticPos.RIGHT, amplitude=0x4000, period=1024, count=2))
	assert controller._device_file.write.call_args.args[0][6] == 0x7F
	assert scheduled[0][0] == 0.03125

	scheduled[0][1](controller.mapper)
	assert controller._device_file.write.call_count == 2
	assert controller._device_file.write.call_args.args[0][6] == 0


def test_bluetooth_turnoff_disconnects_hci_link() -> None:
	controller = object.__new__(DS4HIDRawController)
	controller.daemon = Mock()
	controller.syspath = "/sys/devices/bluetooth/hci0/hci0:50"

	controller.turnoff()

	controller.daemon.get_device_monitor.return_value.disconnect_bluetooth.assert_called_once_with(controller.syspath)


def make_evdev_controller() -> DS4EvdevController:
	controller = object.__new__(DS4EvdevController)
	controller.device = Mock()
	controller.device.upload_effect.return_value = 7
	controller._feedback_effect_id = None
	return controller


def test_evdev_ds4_feedback_uploads_and_plays_rumble_effect() -> None:
	controller = make_evdev_controller()

	controller.feedback(HapticData(HapticPos.BOTH, amplitude=0x4000, period=1024, count=64))

	controller.device.upload_effect.assert_called_once()
	effect = controller.device.upload_effect.call_args.args[0]
	assert effect.type == controller.ECODES.FF_RUMBLE
	assert effect.u.ff_rumble_effect.strong_magnitude == 0x8000
	assert effect.u.ff_rumble_effect.weak_magnitude == 0x8000
	assert effect.ff_replay.length == 1000
	controller.device.write.assert_called_once_with(controller.ECODES.EV_FF, 7, 1)


def test_evdev_ds4_feedback_stop_stops_and_erases_effect() -> None:
	controller = make_evdev_controller()
	controller._feedback_effect_id = 7

	controller.feedback(HapticData(HapticPos.BOTH, amplitude=0, count=0))

	controller.device.write.assert_called_once_with(controller.ECODES.EV_FF, 7, 0)
	controller.device.erase_effect.assert_called_once_with(7)
	controller.device.upload_effect.assert_not_called()
	assert controller._feedback_effect_id is None
