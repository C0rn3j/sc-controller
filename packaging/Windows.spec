import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata


def find_msys64_path() -> Path:
	"""Check common paths for MSYS2 installations."""
	potential_paths = [
		# This is the path the GitHub CI msys action uses
		Path("C:\\a\\_temp\\msys64"),
		# This is the path the GitHub CI msys used to use
		Path("D:\\a\\_temp\\msys64"),
		# This is default Windows path
		Path("C:\\msys64"),
	]
	for path in potential_paths:
		if path.exists():
			return path
	raise FileNotFoundError("MSYS2 base path not found in common locations")


SPEC_DIR = Path(globals().get("SPECPATH", Path.cwd() / "packaging")).resolve()
REPO_ROOT = SPEC_DIR.parents[0]

python_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
msys64_path = Path(find_msys64_path())
print(f"Found msys64 path: {msys64_path}")

a = Analysis(
	[REPO_ROOT / "scc/bin/sc_controller.py"],
	pathex=[],
	binaries=[(str(Path(sys.base_prefix) / "bin" / "libusb-1.0.dll"), ".")],
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
		"scc.drivers.windows",
		#"scc.drivers.macos",
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
#icon_themes = {
#	(Path(source).parent, Path(destination).parent)
#	for destination, source, kind in a.datas
#	if destination.startswith("share/icons/") and Path(destination).name == "index.theme"
#}
#for source_root, destination_root in icon_themes:
#	for directory, _, filenames in os.walk(source_root, followlinks=True):
#		for filename in filenames:
#			source = Path(directory) / filename
#			if source.is_file():
#				destination = destination_root / source.relative_to(source_root)
#				a.datas.append((str(destination), str(source.resolve()), "DATA"))

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
	console=False,
	disable_windowed_traceback=False,
	argv_emulation=False,
	target_arch=None,
	codesign_identity=None,
	entitlements_file=None,
	#icon=[str(REPO_ROOT / "src/icon.ico")],
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
