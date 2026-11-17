"""Identify ViGEm HID interfaces through Windows Configuration Manager ancestry."""

from __future__ import annotations

import ctypes
import functools
import logging
import sys
from uuid import UUID

log = logging.getLogger("WindowsDevices")

CR_SUCCESS = 0
CR_BUFFER_SMALL = 0x1A
CR_NO_SUCH_VALUE = 0x25
DEVPROP_TYPE_STRING = 0x12
DWORD = ctypes.c_uint32


class _DEVPROPKEY(ctypes.Structure):
	_fields_ = [("fmtid", ctypes.c_ubyte * 16), ("pid", DWORD)]

	def __init__(self, guid: str, pid: int) -> None:
		super().__init__((ctypes.c_ubyte * 16).from_buffer_copy(UUID(guid).bytes_le), pid)


# Property keys from the Windows SDK's devpkey.h.
_INSTANCE_ID = _DEVPROPKEY("78c34fc8-104a-4aca-9ea4-524d52996e57", 256)
_SERVICE = _DEVPROPKEY("a45c254e-df1c-4efd-8020-67d146a850e0", 6)


class _ConfigurationManager:
	def __init__(self, library) -> None:
		self.library = library
		property_args = [
			ctypes.POINTER(_DEVPROPKEY),
			ctypes.POINTER(DWORD),
			ctypes.c_void_p,
			ctypes.POINTER(DWORD),
			DWORD,
		]
		for name, args in (
			("CM_Get_Device_Interface_PropertyW", [ctypes.c_wchar_p, *property_args]),
			("CM_Get_DevNode_PropertyW", [DWORD, *property_args]),
			("CM_Locate_DevNodeW", [ctypes.POINTER(DWORD), ctypes.c_wchar_p, DWORD]),
			("CM_Get_Parent", [ctypes.POINTER(DWORD), DWORD, DWORD]),
		):
			function = getattr(library, name)
			function.argtypes = args
			function.restype = DWORD

	@staticmethod
	def _string_property(function, device, key) -> str | None:
		kind, size = DWORD(), DWORD()
		result = function(device, ctypes.byref(key), ctypes.byref(kind), None, ctypes.byref(size), 0)
		if result == CR_NO_SUCH_VALUE:
			return None
		if result not in (CR_SUCCESS, CR_BUFFER_SMALL):
			raise OSError(result, "Configuration Manager property lookup failed")
		# Properties can change while devices are connecting or disconnecting.
		for _ in range(3):
			buffer = ctypes.create_string_buffer(size.value)
			result = function(device, ctypes.byref(key), ctypes.byref(kind), buffer, ctypes.byref(size), 0)
			if result == CR_BUFFER_SMALL:
				continue
			if result != CR_SUCCESS:
				raise OSError(result, "Configuration Manager property read failed")
			if kind.value != DEVPROP_TYPE_STRING:
				raise ValueError("Expected a Windows string device property")
			return buffer.raw[: size.value].decode("utf-16-le").rstrip("\0")
		raise OSError("Windows device property kept changing size")

	def locate(self, instance_id: str | None) -> int:
		node = DWORD()
		result = self.library.CM_Locate_DevNodeW(ctypes.byref(node), instance_id, 0)
		if result != CR_SUCCESS:
			raise OSError(result, "Cannot locate Windows device node")
		return node.value

	def interface_node(self, path: str) -> int:
		instance_id = self._string_property(self.library.CM_Get_Device_Interface_PropertyW, path, _INSTANCE_ID)
		if not instance_id:
			raise ValueError("HID interface has no Windows device instance ID")
		return self.locate(instance_id)

	def service(self, node: int) -> str | None:
		return self._string_property(self.library.CM_Get_DevNode_PropertyW, node, _SERVICE)

	def parent(self, node: int) -> int:
		parent = DWORD()
		result = self.library.CM_Get_Parent(ctypes.byref(parent), node, 0)
		if result != CR_SUCCESS:
			raise OSError(result, "Cannot locate parent Windows device node")
		return parent.value


@functools.lru_cache(maxsize=1)
def _configuration_manager() -> _ConfigurationManager:
	return _ConfigurationManager(ctypes.WinDLL("cfgmgr32"))


def is_vigem_device(path: bytes | str) -> bool | None:
	"""Return whether a HID interface descends from ViGEmBus.

	None means the path could not be resolved (e.g. during unplug). Do not
	cache device results: paths and devnode handles may be reused on reconnect.
	This identifies all ViGEm controllers, not just targets owned by SCC.
	"""
	if sys.platform != "win32":
		return False
	try:
		if isinstance(path, bytes):
			path = path.decode("utf-8")
		manager = _configuration_manager()
		node, root = manager.interface_node(path), manager.locate(None)
		visited = set()
		while node not in visited:
			if node == root:
				return False
			visited.add(node)
			if (manager.service(node) or "").casefold() == "vigembus":
				log.debug("HID interface %r belongs to ViGEmBus", path)
				return True
			node = manager.parent(node)
	except (OSError, ValueError) as error:
		log.debug("Cannot resolve HID ancestry for %r: %s", path, error)
	return None
