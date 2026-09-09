import os

import pytest

from scc.drivers import evdevdrv


class FakeDevice:
	def __init__(self, path: str, name: str = "pad", fails: bool = False) -> None:
		self.path = path
		self.name = name
		self.grabbed = False
		self.ungrabbed = False
		self.closed = False
		self._fails = fails

	def grab(self) -> None:
		if self._fails:
			raise OSError(16, "Device or resource busy")
		self.grabbed = True

	def ungrab(self) -> None:
		if not self.grabbed:
			raise OSError(22, "Invalid argument")
		self.ungrabbed = True

	def close(self) -> None:
		self.closed = True


@pytest.fixture
def nodes(monkeypatch):
	found = [
		FakeDevice("/dev/input/event20", "Wireless Controller"),
		FakeDevice("/dev/input/event21", "Wireless Controller Touchpad"),
		FakeDevice("/dev/input/event22", "Wireless Controller Motion Sensors"),
	]
	by_path = {device.path: device for device in found}
	monkeypatch.setattr(evdevdrv, "HAVE_EVDEV", True)
	monkeypatch.setattr(evdevdrv, "evdev_nodes_from_hidraw", lambda path: list(by_path))
	monkeypatch.setattr(evdevdrv, "evdev", type("Evdev", (), {"InputDevice": staticmethod(by_path.get)}))
	return found


def test_every_node_is_grabbed(nodes) -> None:
	grabbed = evdevdrv.grab_evdev_nodes("/dev/hidraw22")

	assert grabbed == nodes
	assert all(device.grabbed for device in nodes)


def test_failed_node_does_not_prevent_other_grabs(nodes) -> None:
	nodes[1]._fails = True

	grabbed = evdevdrv.grab_evdev_nodes("/dev/hidraw22")

	assert grabbed == [nodes[0], nodes[2]]
	assert nodes[1].closed


def test_ungrab_releases_and_closes_every_node(nodes) -> None:
	grabbed = evdevdrv.grab_evdev_nodes("/dev/hidraw22")

	evdevdrv.ungrab_evdev_nodes(grabbed)

	assert all(device.ungrabbed and device.closed for device in nodes)


def test_ungrab_tolerates_disconnected_nodes(nodes) -> None:
	grabbed = evdevdrv.grab_evdev_nodes("/dev/hidraw22")
	nodes[0].grabbed = False

	evdevdrv.ungrab_evdev_nodes(grabbed)

	assert nodes[1].ungrabbed
	assert all(device.closed for device in nodes)


def test_grab_without_evdev_is_empty(monkeypatch) -> None:
	monkeypatch.setattr(evdevdrv, "HAVE_EVDEV", False)

	assert evdevdrv.grab_evdev_nodes("/dev/hidraw22") == []


def fake_sysfs(tmp_path, monkeypatch, inputs):
	hid = tmp_path / "devices" / "virtual" / "misc" / "uhid" / "0005:054C:09CC.034B"
	for input_dir, event_nodes in inputs.items():
		for event_node in event_nodes:
			(hid / "input" / input_dir / event_node).mkdir(parents=True)
	(hid / "hidraw" / "hidraw22").mkdir(parents=True)
	class_device = tmp_path / "class" / "hidraw" / "hidraw22"
	class_device.mkdir(parents=True)
	(class_device / "device").symlink_to(hid)
	monkeypatch.setattr(evdevdrv, "SYS_CLASS_HIDRAW", str(tmp_path / "class" / "hidraw"))
	return hid


def test_nodes_are_found_through_hidraw_sysfs_link(tmp_path, monkeypatch) -> None:
	hid = fake_sysfs(
		tmp_path,
		monkeypatch,
		{"input1045": ["event10"], "input1046": ["event13"], "input1047": ["event14"]},
	)
	(hid / "input" / "input1045" / "event_count").write_text("0")

	assert evdevdrv.evdev_nodes_from_hidraw("/dev/hidraw22") == [
		"/dev/input/event10",
		"/dev/input/event13",
		"/dev/input/event14",
	]


def test_device_without_input_nodes_is_empty(tmp_path, monkeypatch) -> None:
	fake_sysfs(tmp_path, monkeypatch, {})

	assert evdevdrv.evdev_nodes_from_hidraw("/dev/hidraw22") == []
