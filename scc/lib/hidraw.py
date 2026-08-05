from __future__ import annotations

import ctypes
import fcntl
from typing import TYPE_CHECKING, NamedTuple

import ioctl_opt

if TYPE_CHECKING:
	import sys
	if sys.version_info >= (3, 12):
		from collections.abc import Buffer
	else:
		from typing_extensions import Buffer

	from typing import BinaryIO

# input.h
BUS_USB = 0x03
BUS_HIL = 0x04
BUS_BLUETOOTH = 0x05
BUS_VIRTUAL = 0x06

# hid.h
_HID_MAX_DESCRIPTOR_SIZE = 4096


# hidraw.h
class _hidraw_report_descriptor(ctypes.Structure):
	_fields_ = [
		("size", ctypes.c_uint),
		("value", ctypes.c_ubyte * _HID_MAX_DESCRIPTOR_SIZE),
	]


class _hidraw_devinfo(ctypes.Structure):
	_fields_ = [
		("bustype", ctypes.c_uint),
		("vendor", ctypes.c_short),
		("product", ctypes.c_short),
	]


_HIDIOCGRDESCSIZE = ioctl_opt.IOR(ord("H"), 0x01, ctypes.c_int)
_HIDIOCGRDESC = ioctl_opt.IOR(ord("H"), 0x02, _hidraw_report_descriptor)
_HIDIOCGRAWINFO = ioctl_opt.IOR(ord("H"), 0x03, _hidraw_devinfo)
_HIDIOCGRAWNAME = lambda length: ioctl_opt.IOC(ioctl_opt.IOC_READ, ord("H"), 0x04, length)
_HIDIOCGRAWPHYS = lambda length: ioctl_opt.IOC(ioctl_opt.IOC_READ, ord("H"), 0x05, length)
_HIDIOCSFEATURE = lambda length: ioctl_opt.IOC(ioctl_opt.IOC_WRITE | ioctl_opt.IOC_READ, ord("H"), 0x06, length)
_HIDIOCGFEATURE = lambda length: ioctl_opt.IOC(ioctl_opt.IOC_WRITE | ioctl_opt.IOC_READ, ord("H"), 0x07, length)

HIDRAW_FIRST_MINOR = 0
HIDRAW_MAX_DEVICES = 64
HIDRAW_BUFFER_SIZE = 64


class DevInfo(NamedTuple):
	"""Device Info.

	- bustype: one of BUS_USB, BUS_HIL, BUS_BLUETOOTH or BUS_VIRTUAL
	- vendor: device's vendor number
	- product: device's product number
	"""

	bustype: int
	vendor: int
	product: int


class HIDRaw:
	"""Provide methods to access hidraw device's ioctls."""

	def __init__(self, device: BinaryIO | int) -> None:
		"""Device (file, fileno).

		A file object or a fileno of an open hidraw device node.
		"""
		self._device: BinaryIO | int = device

	def _ioctl(self, func: int, arg: int | Buffer, mutate_flag: bool = False) -> None:
		result = fcntl.ioctl(self._device, func, arg, mutate_flag)
		if result < 0:
			raise OSError(result)

	def getRawReportDescriptor(self) -> str:
		"""Return a binary string containing the raw HID report descriptor."""
		descriptor = _hidraw_report_descriptor()
		size = ctypes.c_uint()
		self._ioctl(_HIDIOCGRDESCSIZE, size, True)
		descriptor.size = size
		self._ioctl(_HIDIOCGRDESC, descriptor, True)
		return "".join(chr(x) for x in descriptor.value[: size.value])

	# TODO: decode descriptor into a python object
	# def getReportDescriptor(self):

	def getInfo(self) -> DevInfo:
		"""Return a DevInfo instance."""
		devinfo = _hidraw_devinfo()
		self._ioctl(_HIDIOCGRAWINFO, devinfo, True)
		return DevInfo(devinfo.bustype, devinfo.vendor, devinfo.product)

	def getName(self, length: int = 512) -> str:
		"""Return device name as an Unicode string."""
		name = ctypes.create_string_buffer(length)
		self._ioctl(_HIDIOCGRAWNAME(length), name, True)
		return name.value.decode("UTF-8")

	def getPhysicalAddress(self, length: int = 512) -> bytes:
		"""Return device's physical address as bytes.

		See hidraw documentation for value signification, as it depends on device's bus type.
		"""
		name = ctypes.create_string_buffer(length)
		self._ioctl(_HIDIOCGRAWPHYS(length), name, True)
		return name.value

	def sendFeatureReport(self, report: bytes, report_num: int = 0) -> None:
		"""Send a feature report."""
		length = len(report) + 1
		buf = bytearray(length)
		buf[0] = report_num
		buf[1:] = report
		self._ioctl(
			_HIDIOCSFEATURE(length),
			(ctypes.c_char * length).from_buffer(buf),
			True,
		)

	def getFeatureReport(self, report_num: int = 0, length: int = 63) -> bytearray:
		"""Receive a feature report.

		Blocks, unless you configured provided file (descriptor) to be non-blocking.
		"""
		length += 1
		buf = bytearray(length)
		buf[0] = report_num
		self._ioctl(
			_HIDIOCGFEATURE(length),
			(ctypes.c_char * length).from_buffer(buf),
			True,
		)
		return buf
