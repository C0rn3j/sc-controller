from unittest.mock import MagicMock, Mock

import usb1

from scc.drivers.usb import SCUSBDevice, USBDriver


def make_device() -> tuple[SCUSBDevice, Mock, Mock]:
	libusb_device = MagicMock()
	handle = Mock()
	device = SCUSBDevice(libusb_device, handle)
	return device, libusb_device, handle


def test_failed_transfer_requests_close_without_resubmitting() -> None:
	device, _, handle = make_device()
	transfer = Mock()
	transfer.getStatus.return_value = usb1.TRANSFER_ERROR
	handle.getTransfer.return_value = transfer

	device.set_input_interrupt(3, 64, Mock())
	callback = transfer.setInterrupt.call_args.kwargs["callback"]
	transfer.submit.reset_mock()

	callback(transfer)

	assert device._close_requested
	transfer.submit.assert_not_called()


def test_close_waits_for_cancelled_transfer_before_releasing() -> None:
	device, _, handle = make_device()
	driver = USBDriver()
	transfer = Mock()
	transfer.isSubmitted.side_effect = [True, False, False]
	device._transfer_list.append(transfer)
	device._usb_driver = driver
	device._claimed.append(2)
	device._detached.append(2)

	device.close()

	transfer.cancel.assert_called_once_with()
	handle.releaseInterface.assert_not_called()
	assert device in driver._closing_devices

	driver._finish_closing_devices()

	handle.releaseInterface.assert_called_once_with(2)
	handle.attachKernelDriver.assert_called_once_with(2)
	transfer.close.assert_called_once_with()
	handle.close.assert_called_once_with()
	assert device._closed
	assert device not in driver._closing_devices


def test_claim_by_only_detaches_matching_interfaces() -> None:
	device, libusb_device, handle = make_device()
	matching = Mock()
	matching.getNumber.return_value = 2
	matching.getClass.return_value = 3
	matching.getSubClass.return_value = 0
	matching.getProtocol.return_value = 0
	other = Mock()
	other.getNumber.return_value = 4
	other.getClass.return_value = 255
	other.getSubClass.return_value = 0
	other.getProtocol.return_value = 0
	libusb_device.__getitem__.return_value = [[matching, other]]
	handle.kernelDriverActive.return_value = True

	assert device.claim_by(klass=3, subclass=0, protocol=0) == 1

	handle.detachKernelDriver.assert_called_once_with(2)
	handle.claimInterface.assert_called_once_with(2)
	assert device._claimed == [2]
	assert device._detached == [2]
