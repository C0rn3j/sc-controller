"""Configuration Manager ancestry and physical/virtual HID filtering."""

import ctypes
from types import SimpleNamespace

import pytest

from scc.lib import hid_registration, windows_devices

PHYSICAL = r"\\?\hid#vid_045e&pid_028e#physical#{guid}"
VIRTUAL = r"\\?\hid#vid_045e&pid_028e#virtual#{guid}"


class Function:
	"""Callable DLL export that also accepts ctypes ABI declarations."""

	def __init__(self, callback):
		self.callback = callback

	def __call__(self, *args):
		return self.callback(*args)


class ConfigurationManagerDLL:
	"""Minimal Windows device tree with a physical and virtual Xbox 360."""

	def __init__(self):
		self.paths = {PHYSICAL: "physical", VIRTUAL: "virtual"}
		self.nodes = {"physical": 10, "virtual": 20}
		self.parents = {10: 11, 11: 1, 20: 21, 21: 22, 22: 1}
		self.services = {10: "HidUsb", 11: "xusb22", 20: "HidUsb", 21: "xusb22", 22: "ViGEmBus"}
		self.fail_parent = False
		self.CM_Get_Device_Interface_PropertyW = Function(self.interface_property)
		self.CM_Get_DevNode_PropertyW = Function(self.node_property)
		self.CM_Locate_DevNodeW = Function(self.locate)
		self.CM_Get_Parent = Function(self.parent)

	@staticmethod
	def string(value, kind, buffer, size):
		encoded = (value + "\0").encode("utf-16-le")
		kind._obj.value = windows_devices.DEVPROP_TYPE_STRING
		capacity = size._obj.value
		size._obj.value = len(encoded)
		if buffer is None or capacity < len(encoded):
			return windows_devices.CR_BUFFER_SMALL
		ctypes.memmove(buffer, encoded, len(encoded))
		return windows_devices.CR_SUCCESS

	def interface_property(self, path, key, kind, buffer, size, flags):
		assert flags == 0
		assert key._obj.pid == 256
		if path not in self.paths:
			return 0x0D
		return self.string(self.paths[path], kind, buffer, size)

	def node_property(self, node, key, kind, buffer, size, flags):
		assert flags == 0
		assert key._obj.pid == 6
		if node not in self.services:
			return windows_devices.CR_NO_SUCH_VALUE
		return self.string(self.services[node], kind, buffer, size)

	def locate(self, output, instance_id, flags):
		assert flags == 0
		if instance_id is None:
			output._obj.value = 1
		elif instance_id in self.nodes:
			output._obj.value = self.nodes[instance_id]
		else:
			return 0x0D
		return windows_devices.CR_SUCCESS

	def parent(self, output, node, flags):
		assert flags == 0
		if self.fail_parent or node not in self.parents:
			return 0x0D
		output._obj.value = self.parents[node]
		return windows_devices.CR_SUCCESS


@pytest.fixture
def windows_tree(monkeypatch):
	library = ConfigurationManagerDLL()
	manager = windows_devices._ConfigurationManager(library)
	monkeypatch.setattr(windows_devices, "sys", SimpleNamespace(platform="win32"))
	monkeypatch.setattr(windows_devices, "_configuration_manager", lambda: manager)
	monkeypatch.setattr(hid_registration, "sys", SimpleNamespace(platform="win32"))
	return library


def info(path):
	return {"path": path.encode(), "vendor_id": 0x045E, "product_id": 0x028E, "usage_page": 1, "usage": 5}


def test_same_vid_pid_physical_controller_is_allowed_and_vigem_is_excluded(windows_tree):
	assert windows_devices.is_vigem_device(PHYSICAL.encode()) is False
	assert windows_devices.is_vigem_device(VIRTUAL) is True
	assert not hid_registration.should_skip_hid_device(info(PHYSICAL))
	assert hid_registration.should_skip_hid_device(info(VIRTUAL))


def test_service_matching_is_case_insensitive_and_not_product_specific(windows_tree):
	windows_tree.services[22] = "vIgEmBuS"
	device = info(VIRTUAL)
	device.update(vendor_id=0x054C, product_id=0x05C4)
	assert hid_registration.should_skip_hid_device(device)


def test_missing_service_on_intermediate_nodes_does_not_stop_traversal(windows_tree):
	del windows_tree.services[21]
	assert windows_devices.is_vigem_device(VIRTUAL) is True


def test_disappearing_device_is_deferred_and_retried_without_stale_cache(windows_tree):
	windows_tree.fail_parent = True
	assert windows_devices.is_vigem_device(PHYSICAL) is None
	assert hid_registration.should_skip_hid_device(info(PHYSICAL))
	windows_tree.fail_parent = False
	assert not hid_registration.should_skip_hid_device(info(PHYSICAL))
	# The same interface path can be reused for a different ancestry.
	windows_tree.parents[11] = 22
	assert hid_registration.should_skip_hid_device(info(PHYSICAL))


def test_unknown_interface_and_parent_cycle_do_not_allow_feedback(windows_tree):
	assert windows_devices.is_vigem_device("missing") is None
	windows_tree.parents[21] = 20
	assert windows_devices.is_vigem_device(VIRTUAL) is None
	assert hid_registration.should_skip_hid_device(info(VIRTUAL))


def test_non_windows_does_not_load_configuration_manager(monkeypatch):
	monkeypatch.setattr(windows_devices, "sys", SimpleNamespace(platform="linux"))
	monkeypatch.setattr(windows_devices, "_configuration_manager", lambda: pytest.fail("Loaded Windows DLL on Linux"))
	assert windows_devices.is_vigem_device(PHYSICAL) is False


def test_daemon_discovery_filters_by_ancestry_even_with_saved_registration(windows_tree, monkeypatch, tmp_path):
	from scc.drivers import hidapi

	physical, virtual = info(PHYSICAL), info(VIRTUAL)
	monkeypatch.setattr(hidapi, "hid", SimpleNamespace(enumerate=lambda: [physical, virtual]))
	opened = []
	monkeypatch.setattr(
		hidapi, "HIDAPIController", lambda driver, device, *args: opened.append(device["path"]) or object()
	)
	driver = hidapi.HIDAPIDriver(SimpleNamespace())
	driver.configs[(0x045E, 0x028E)] = (str(tmp_path / "registered.json"), {"input_backend": "hidapi"})
	driver.scan()
	assert opened == [physical["path"]]
	assert set(driver.controllers) == {physical["path"]}
