#!/usr/bin/env python3
"""Installation script for everything that could not be migrated to pyproject.toml so far."""

import glob
from pathlib import Path

from setuptools import Extension, setup

data_files = [
	("share/scc/ui", glob.glob("ui/*.ui")),
	("share/scc/ui/ae", glob.glob("ui/ae/*.ui")),
	("share/scc/images", glob.glob("images/*.svg")),
	("share/scc/images", glob.glob("images/*.json")),
	("share/scc/images/button-images", glob.glob("images/button-images/*.svg")),
	("share/scc/images/button-images", glob.glob("images/button-images/*.json")),
	("share/scc/images/controller-icons", glob.glob("images/controller-icons/*.svg")),
	("share/scc/images/controller-images", glob.glob("images/controller-images/*.svg")),
	("share/icons/hicolor/24x24/status", glob.glob("images/24x24/status/*.png")),
	("share/icons/hicolor/256x256/status", glob.glob("images/256x256/status/*.png")),
	("share/icons/hicolor/scalable/apps", ["packaging/io.github.c0rn3j.sc-controller.svg"]),
	("share/scc/default_profiles", glob.glob("default_profiles/*.sccprofile")),
	("share/scc/default_profiles", glob.glob("default_profiles/.*.sccprofile")),
	("share/scc/default_menus", glob.glob("default_menus/*.menu")),
	("share/scc/default_menus", glob.glob("default_menus/.*.menu")),
	("share/scc/osd-styles", glob.glob("osd-styles/*.json")),
	("share/scc/osd-styles", glob.glob("osd-styles/*.css")),
	("share/scc/", ["gamecontrollerdb.txt"]),
	("share/metainfo", ["packaging/io.github.c0rn3j.sc-controller.metainfo.xml"]),
	("share/mime/packages", ["packaging/io.github.c0rn3j.sc-controller.mimetypes.xml"]),
	("share/applications", ["packaging/io.github.c0rn3j.sc-controller.desktop"]),
	("lib/udev/rules.d", glob.glob("packaging/*.rules")),
] + [  # menu icons subfolders
	("share/scc/images/menu-icons/" + x.split("/")[-1], [x + "/LICENSES"] + glob.glob(x + "/*.png"))
	for x in glob.glob("images/menu-icons/*")
] + [
	(f"share/locale/{path.parent.parent.name}/LC_MESSAGES", [str(path)])
	for path in Path("scc/locale").glob("*/LC_MESSAGES/*.mo")
]

extensions = [
	Extension("libuinput", sources=["scc/uinput.c"]),
	Extension("libcemuhook", sources=["scc/cemuhook_server.c"], libraries=["z"], define_macros=[("PYTHON", "1")]),
	Extension("libhiddrv", sources=["scc/drivers/hiddrv.c"]),
	Extension("libsc_by_bt", sources=["scc/drivers/sc_by_bt.c"]),
	Extension("libremotepad", sources=["scc/drivers/remotepad_controller.c"]),
]

setup(
	ext_modules=extensions,
	data_files=data_files,
)
