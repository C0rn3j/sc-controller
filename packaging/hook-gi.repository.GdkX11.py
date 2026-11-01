"""Collect the GTK4 X11 backend typelib and its dependencies."""

from PyInstaller.utils.hooks.gi import GiModuleInfo

module_info = GiModuleInfo("GdkX11", "4.0")
if module_info.available:
	binaries, datas, hiddenimports = module_info.collect_typelib_data()
