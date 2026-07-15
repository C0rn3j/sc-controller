from unittest.mock import Mock, patch

from scc.device_monitor import DeviceMonitor


def make_monitor() -> DeviceMonitor:
	monitor = object.__new__(DeviceMonitor)
	monitor._monitor = None
	monitor.daemon = Mock()
	monitor.dev_added_cbs = {}
	monitor.dev_removed_cbs = {}
	monitor.known_devs = {}
	monitor._pending_bt = {}
	monitor._get_hci_addresses = Mock()
	return monitor


@patch("scc.device_monitor.os.path.exists", return_value=True)
def test_bluetooth_discovery_retries_until_vendor_is_available(_exists: Mock) -> None:
	monitor = make_monitor()
	callback = Mock(return_value=object())
	monitor.dev_added_cbs[("bluetooth", 0x054C, 0x05C4)] = callback
	monitor.get_vendor_product = Mock(side_effect=[OSError(), (0x054C, 0x05C4)])
	scheduled = []
	monitor.daemon.get_scheduler.return_value.schedule.side_effect = (
		lambda delay, fn: scheduled.append((delay, fn)) or Mock()
	)

	monitor._on_new_syspath("bluetooth", "/sys/devices/hci0:1")

	assert callback.call_count == 0
	assert scheduled[0][0] == monitor.BT_DISCOVERY_RETRY_DELAY
	scheduled[0][1]()
	monitor._get_hci_addresses.assert_called_once_with()
	callback.assert_called_once_with("/sys/devices/hci0:1", 0x054C, 0x05C4)
	assert "/sys/devices/hci0:1" in monitor.known_devs
	assert "/sys/devices/hci0:1" not in monitor._pending_bt


def test_bluetooth_discovery_retry_is_cancelled_on_remove() -> None:
	monitor = make_monitor()
	task = Mock()
	monitor._pending_bt["/sys/devices/hci0:1"] = (1, task)

	monitor._cancel_bt_retry("/sys/devices/hci0:1")

	task.cancel.assert_called_once_with()
	assert "/sys/devices/hci0:1" not in monitor._pending_bt


def test_bluetooth_adapter_is_not_retried_as_device() -> None:
	monitor = make_monitor()
	monitor.get_vendor_product = Mock()

	monitor._on_new_syspath("bluetooth", "/sys/devices/bluetooth/hci0")

	monitor.get_vendor_product.assert_not_called()
	monitor.daemon.get_scheduler.return_value.schedule.assert_not_called()


@patch("scc.device_monitor._disconnect_bluez")
def test_disconnect_bluetooth_uses_bluez_device_path(disconnect_bluez: Mock) -> None:
	monitor = make_monitor()
	monitor.bt_addresses = {"hci0:50": "A0:5A:5D:87:82:17"}

	monitor.disconnect_bluetooth("/sys/devices/bluetooth/hci0/hci0:50")

	disconnect_bluez.assert_called_once_with("/org/bluez/hci0/dev_A0_5A_5D_87_82_17")
