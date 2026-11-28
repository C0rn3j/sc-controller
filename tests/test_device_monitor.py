from unittest.mock import Mock, patch

from scc.device_monitor import DeviceMonitor, _is_same_or_child


def make_monitor() -> DeviceMonitor:
	monitor = object.__new__(DeviceMonitor)
	monitor._monitor = None
	monitor.daemon = Mock()
	monitor.dev_added_cbs = {}
	monitor.dev_removed_cbs = {}
	monitor.known_devs = {}
	monitor._pending_bt = {}
	monitor.bt_addresses = {}
	monitor._get_hci_addresses = Mock()
	return monitor


@patch("scc.device_monitor.os.path.exists", return_value=True)
def test_bluetooth_discovery_retries_until_vendor_is_available(_exists: Mock) -> None:
	monitor = make_monitor()
	callback = Mock(return_value=object())
	monitor.dev_added_cbs[("bluetooth", 0x054C, 0x05C4)] = callback
	monitor.get_vendor_product = Mock(side_effect=[OSError(), (0x054C, 0x05C4)])
	scheduled = []
	monitor.daemon.get_scheduler.return_value.schedule.side_effect = lambda delay, fn: (
		scheduled.append((delay, fn)) or Mock()
	)

	monitor._on_new_syspath("bluetooth", "/sys/devices/hci0:1")

	assert callback.call_count == 0
	assert scheduled[0][0] == monitor.BT_DISCOVERY_RETRY_DELAY
	scheduled[0][1]()
	monitor._get_hci_addresses.assert_called_once_with()
	callback.assert_called_once_with("/sys/devices/hci0:1", 0x054C, 0x05C4)
	assert "/sys/devices/hci0:1" in monitor.known_devs
	assert "/sys/devices/hci0:1" not in monitor._pending_bt


@patch("scc.device_monitor.os.path.exists", return_value=True)
def test_bluetooth_discovery_retries_until_added_callback_is_ready(_exists: Mock) -> None:
	monitor = make_monitor()
	callback = Mock(side_effect=[None, object()])
	monitor.dev_added_cbs[("bluetooth", 0x054C, 0x05C4)] = callback
	monitor.get_vendor_product = Mock(return_value=(0x054C, 0x05C4))
	scheduled = []
	monitor.daemon.get_scheduler.return_value.schedule.side_effect = lambda delay, fn: (
		scheduled.append((delay, fn)) or Mock()
	)

	monitor._on_new_syspath("bluetooth", "/sys/devices/hci0:1")

	assert callback.call_count == 1
	assert "/sys/devices/hci0:1" not in monitor.known_devs
	assert monitor._pending_bt["/sys/devices/hci0:1"][0] == 1
	scheduled[0][1]()
	assert callback.call_count == 2
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


def test_flatpak_rescan_repeats_after_failure() -> None:
	monitor = make_monitor()
	monitor.rescan = Mock(side_effect=OSError("udev unavailable"))

	monitor._flatpak_rescan()

	monitor.daemon.get_scheduler.return_value.schedule.assert_called_once_with(
		monitor.FLATPAK_RESCAN_INTERVAL, monitor._flatpak_rescan,
	)


def test_rescan_removes_devices_missing_from_enumeration() -> None:
	monitor = make_monitor()
	removed = Mock()
	monitor.known_devs["/sys/devices/old"] = (0x054C, 0x0CE6, removed)
	monitor._eudev = Mock()
	monitor._eudev.enumerate.return_value.__iter__ = Mock(return_value=iter(()))

	monitor.rescan()

	removed.assert_called_once_with("/sys/devices/old", 0x054C, 0x0CE6)
	assert "/sys/devices/old" not in monitor.known_devs


@patch("scc.device_monitor._disconnect_bluez")
def test_disconnect_bluetooth_uses_bluez_device_path(disconnect_bluez: Mock) -> None:
	monitor = make_monitor()
	monitor.bt_addresses = {"hci0:50": "A0:5A:5D:87:82:17"}

	monitor.disconnect_bluetooth("/sys/devices/bluetooth/hci0/hci0:50")

	disconnect_bluez.assert_called_once_with("/org/bluez/hci0/dev_A0_5A_5D_87_82_17")


@patch("scc.device_monitor._disconnect_bluez")
def test_disconnect_bluetooth_gets_address_from_hid_sysfs(disconnect_bluez: Mock) -> None:
	monitor = make_monitor()
	monitor._dev_for_hci = Mock(return_value="/sys/bus/hid/devices/controller")
	monitor._find_bt_address = Mock(return_value="a0:5a:5d:87:82:17")

	monitor.disconnect_bluetooth("/sys/devices/bluetooth/hci1/hci1:256")

	disconnect_bluez.assert_called_once_with("/org/bluez/hci1/dev_A0_5A_5D_87_82_17")
	assert monitor.bt_addresses["hci1:256"] == "A0:5A:5D:87:82:17"
	monitor._get_hci_addresses.assert_not_called()


def test_get_bluetooth_syspath_matches_address_case_insensitively() -> None:
	monitor = make_monitor()
	monitor.bt_addresses = {"hci0:50": "A0:5A:5D:87:82:17"}

	assert monitor.get_bluetooth_syspath("a0:5a:5d:87:82:17") == "hci0:50"
	monitor._get_hci_addresses.assert_called_once_with()


def test_sysfs_child_detection_does_not_need_bluetooth_address() -> None:
	connection = "/sys/devices/bluetooth/hci1/hci1:256"
	hid_node = connection + "/0005:054C:0CE6.0001"

	assert _is_same_or_child(connection, hid_node)
	assert not _is_same_or_child(connection, "/sys/devices/bluetooth/hci0/hci0:42/device")
