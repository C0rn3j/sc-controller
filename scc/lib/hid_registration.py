"""Raw HIDAPI input and saved mappings used by controller registration.

The wizard and driver share input numbering: buttons start at 288, axes
follow descriptor order, and each hat exposes two additional axes.
"""

from dataclasses import dataclass
from types import SimpleNamespace

from scc.constants import SCButtons, STICK_PAD_MAX, STICK_PAD_MIN
from scc.lib.hidparse import AXES, GenericDesktopPage, GlobalItem, ItemLength, ItemType, LocalItem, MainItem, UsagePage
from scc.lib.hidparse import parse_report_descriptor

FIRST_BUTTON = 288


def path_token(path: bytes | str) -> str:
	"""Encode a HIDAPI path for the device list and tester command line."""
	return (path if isinstance(path, bytes) else path.encode()).hex()


def registration_device(info: dict) -> SimpleNamespace:
	return SimpleNamespace(
		path=path_token(info["path"]),
		name=info.get("product_string") or f"{info['vendor_id']:04x}:{info['product_id']:04x}",
		info=SimpleNamespace(vendor=info["vendor_id"], product=info["product_id"]),
	)


def open_device(info: dict):
	import hid

	device = hid.device()
	try:
		device.open_path(info["path"])
		device.set_nonblocking(True)
		try:
			descriptor = device.get_report_descriptor()
		except TypeError:
			descriptor = device.get_report_descriptor(4096)
		return device, RawHIDInput(bytes(descriptor))
	except Exception:
		device.close()
		raise


@dataclass
class Field:
	report: int
	bit: int
	size: int
	minimum: int
	maximum: int
	kind: str
	code: int


class RawHIDInput:
	"""Read descriptor-defined values, preserving state across report IDs."""

	def __init__(self, descriptor: bytes) -> None:
		self.fields = []
		self.axes = {}
		self.buttons = {}
		self.report_sizes = {}
		self.numbered = False
		state = {"size": 0, "count": 0, "minimum": 0, "maximum": 0, "page": 0, "report": 0}
		stack = []
		usages = []
		usage_min = None
		positions = {}
		gamepad = False
		for item in parse_report_descriptor(descriptor, True):
			if isinstance(item, GlobalItem):
				item = (item,)
			tag = item[0]
			if isinstance(tag, GlobalItem):
				keys = {
					GlobalItem.ReportSize: "size",
					GlobalItem.ReportCount: "count",
					GlobalItem.LogicalMinimum: "minimum",
					GlobalItem.LogicalMaximum: "maximum",
					GlobalItem.UsagePage: "page",
					GlobalItem.ReportID: "report",
				}
				if tag in keys:
					state[keys[tag]] = int(item[1])
					if tag == GlobalItem.ReportID:
						self.numbered = True
				elif tag == GlobalItem.Push:
					stack.append(state.copy())
				elif tag == GlobalItem.Pop:
					state = stack.pop()
			elif tag == LocalItem.Usage:
				usages.append(int(item[1]))
				if state["page"] == UsagePage.GenericDesktopPage and item[1] in (
					GenericDesktopPage.Joystick,
					GenericDesktopPage.GamePad,
				):
					gamepad = True
			elif tag == LocalItem.UsageMinimum:
				usage_min = int(item[1])
			elif tag == LocalItem.UsageMaximum and usage_min is not None:
				usages.extend(range(usage_min, int(item[1]) + 1))
			elif isinstance(tag, MainItem):
				if tag == MainItem.Input:
					report, size = state["report"], state["size"]
					bit = positions.get(report, 0)
					for index in range(state["count"]):
						usage = usages[min(index, len(usages) - 1)] if usages else None
						kind = None
						if item[1] == ItemType.Data and item[2] == ItemLength.Variable and 0 < size <= 32:
							if state["page"] == UsagePage.ButtonPage:
								kind = "button"
							elif state["page"] == UsagePage.GenericDesktopPage:
								if usage in AXES:
									kind = "axis"
								elif usage == GenericDesktopPage.Hatswitch:
									kind = "hat"
						if kind:
							code = FIRST_BUTTON + len(self.buttons) if kind == "button" else len(self.axes)
							self.fields.append(Field(report, bit, size, state["minimum"], state["maximum"], kind, code))
							if kind == "button":
								self.buttons[code] = False
							else:
								self.axes[code] = 0
								if kind == "hat":
									self.axes[code + 1] = 0
						bit += size
					positions[report] = bit
				usages = []
				usage_min = None
		if not gamepad or not self.fields:
			raise ValueError("HID interface has no supported joystick/gamepad inputs")
		self.report_sizes = {report: (bits + 7) // 8 + int(self.numbered) for report, bits in positions.items()}

	def read(self, data: bytes) -> bool:
		if not data:
			return False
		report = data[0] if self.numbered else 0
		if report not in self.report_sizes or len(data) < self.report_sizes[report]:
			return False
		bits = int.from_bytes(data[int(self.numbered) :], "little")
		for field in self.fields:
			if field.report != report:
				continue
			value = (bits >> field.bit) & ((1 << field.size) - 1)
			if field.minimum < 0 and value & (1 << (field.size - 1)):
				value -= 1 << field.size
			if field.kind == "button":
				self.buttons[field.code] = bool(value)
			elif field.kind == "hat":
				directions = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
				index = value - field.minimum
				x, y = directions[index] if 0 <= index < 8 else (0, 0)
				self.axes[field.code], self.axes[field.code + 1] = x, y
			else:
				self.axes[field.code] = value
		return True


def map_inputs(raw: RawHIDInput, config: dict) -> dict:
	"""Apply the wizard's axis calibration, buttons, and button-driven axes."""
	result = {"buttons": 0}
	for code, name in config.get("buttons", {}).items():
		if raw.buttons.get(int(code)):
			if name in ("LT", "RT"):
				result["ltrig" if name == "LT" else "rtrig"] = 255
			result["buttons"] |= int(getattr(SCButtons, name))
	for code, axis in config.get("axes", {}).items():
		if int(code) not in raw.axes:
			continue
		name = axis["axis"]
		lo, hi = axis["min"], axis["max"]
		if lo == hi:
			continue
		value = raw.axes[int(code)]
		trigger = name in ("ltrig", "rtrig")
		normal = (value - lo) / (hi - lo)
		if trigger:
			result[name] = round(max(0, min(1, normal)) * 255)
		else:
			normal = normal * 2 - 1
			deadzone = abs(axis.get("deadzone", 0) * 2 / (hi - lo))
			result[name] = 0 if abs(normal) <= deadzone else round(max(-1, min(1, normal)) * STICK_PAD_MAX)
	for code, axis in config.get("dpads", {}).items():
		name = axis["axis"]
		result.setdefault(name, 0)
		if raw.buttons.get(int(code)):
			if name in ("ltrig", "rtrig"):
				result[name] = 255
			else:
				result[name] = STICK_PAD_MAX if axis["positive"] else STICK_PAD_MIN
			if axis.get("button"):
				result["buttons"] |= int(getattr(SCButtons, axis["button"]))
	return result


def hiddrv_test(argv: list[str]) -> int:
	"""Stream raw inputs using the existing registration tester protocol."""
	import hid

	if len(argv) != 1:
		return 1
	info = next((info for info in hid.enumerate() if path_token(info["path"]) == argv[0]), None)
	if info is None:
		return 2
	try:
		device, raw = open_device(info)
	except (OSError, ValueError, AttributeError):
		return 2
	try:
		device.set_nonblocking(False)
		print("Axes:", *raw.axes)
		print("Buttons:", *raw.buttons)
		print("Ready", flush=True)
		while True:
			old_axes, old_buttons = raw.axes.copy(), raw.buttons.copy()
			# Blocking reads with a timeout keep the tester idle between inputs.
			data = device.read(max(raw.report_sizes.values()), 100)
			if not raw.read(bytes(data)):
				continue
			for code, value in raw.axes.items():
				if old_axes[code] != value:
					print("Axis", code, value, flush=True)
			for code, value in raw.buttons.items():
				if old_buttons[code] != value:
					print("ButtonPress" if value else "ButtonRelease", code, flush=True)
	except KeyboardInterrupt:
		return 0
	finally:
		device.close()
