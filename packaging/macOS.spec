import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

SPEC_DIR = Path(globals().get("SPECPATH", Path.cwd() / "packaging")).resolve()
REPO_ROOT = SPEC_DIR.parents[0]

a = Analysis(
	[REPO_ROOT / "scc/bin/sc_controller.py"],
	pathex=[],
	binaries=[],
	datas=[
		(REPO_ROOT / "scc/locale/", "share/locale/"),
		(REPO_ROOT / "ui/", "ui/"),
		(REPO_ROOT / "images/", "images/"),
		(REPO_ROOT / "default_profiles/", "default_profiles/"),
		(REPO_ROOT / "default_menus/", "default_menus/"),
		(REPO_ROOT / "osd-styles/", "osd-styles/"),
		(REPO_ROOT / "gamecontrollerdb.txt", "."),
	] + copy_metadata("sccontroller"), # For About dialogue to work correctly
	hiddenimports=[
		"scc",
		"scc.bin",
		"scc.drivers",
		#"scc.drivers.linux",
		#"scc.drivers.windows",
		"scc.drivers.macos",
		"scc.lib",
		"scc.x11",
		"scc.osd",
		"scc.foreign",
		"scc.gui",
		"scc.gui.app",
		"scc.gui.ae",
		"scc.gui.importexport",
		"scc.gui.creg",
	] + collect_submodules("scc.gui.ae"),
	hookspath=[],
	hooksconfig={
		"gi": {
			"module-versions": {
				"Gtk": "4.0",
				"Gdk": "4.0",
			},
		},
	},
	runtime_hooks=[],
	excludes=[],
	noarchive=False,
	optimize=0,
)

# pyinstaller skips symlink dirs
# GTK's icon caches reference aliases inside symlink dirs (like 16@2x)
icon_themes = {
	(Path(source).parent, Path(destination).parent)
	for destination, source, kind in a.datas
	if destination.startswith("share/icons/") and Path(destination).name == "index.theme"
}
for source_root, destination_root in icon_themes:
	for directory, _, filenames in os.walk(source_root, followlinks=True):
		for filename in filenames:
			source = Path(directory) / filename
			if source.is_file():
				destination = destination_root / source.relative_to(source_root)
				a.datas.append((str(destination), str(source.resolve()), "DATA"))

pyz = PYZ(a.pure)

exe = EXE(
	pyz,
	a.scripts,
	[],
	exclude_binaries=True,
	name="sc-controller",
	debug=False,
	bootloader_ignore_signals=False,
	strip=False,
	upx=True,
	console=True,
	disable_windowed_traceback=False,
	argv_emulation=False,
	target_arch=None,
	codesign_identity=None,
	entitlements_file=None,
)
coll = COLLECT(
	exe,
	a.binaries,
	a.datas,
	strip=False,
	upx=True,
	upx_exclude=[],
	name="sc-controller",
)
app = BUNDLE(
	coll,
	name="sc-controller.app",
	icon=None, # str(REPO_ROOT / "icons/scc-mac.icns"),
	bundle_identifier=None,
	info_plist={
		"CFBundleName": "SC Controller",
		"CFBundleDisplayName": "SC Controller",
		#"CFBundleIconName": "scc",
		"LSEnvironment": {
			"LANG": "en_US.UTF-8",
			"LC_CTYPE": "en_US.UTF-8",
			}
	}
)
