"""Reproduce Windows GTK getter failures caused by ctypes import order."""

import os
import sys

if sys.platform == "win32":
	_dll_directory = os.add_dll_directory(r"C:\msys64\clang64\bin")

if "--gtk-first" not in sys.argv:
	import ctypes

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

adj = Gtk.Adjustment(value=50, lower=0, upper=100)
print("getter:", adj.get_value(), "property:", adj.props.value)

if "--gtk-first" in sys.argv:
	import ctypes

adj.props.value = 75
print("changed getter:", adj.get_value(), "property:", adj.props.value)
print("Python:", sys.version, sys.executable)
print("PyGObject:", gi.__version__, gi.__file__)
print("GTK:", Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())

# Diagnose which libffi the Windows loader selected, after testing the getters.
if sys.platform == "win32":
	from ctypes import wintypes

	kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
	get_module = kernel32.GetModuleHandleW
	get_module.argtypes = [wintypes.LPCWSTR]
	get_module.restype = wintypes.HMODULE
	get_filename = kernel32.GetModuleFileNameW
	get_filename.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
	get_filename.restype = wintypes.DWORD
	for name in ("libffi-8.dll", "libffi-7.dll", "libffi.dll"):
		handle = get_module(name)
		if handle:
			path = ctypes.create_unicode_buffer(32768)
			if get_filename(handle, path, len(path)):
				print("Loaded libffi:", path.value)
