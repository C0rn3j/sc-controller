import sys
import tomllib
from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules, copy_metadata


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

with (REPO_ROOT / "pyproject.toml").open("rb") as project_file:
	project = tomllib.load(project_file)["project"]
entry_points = project["gui-scripts"] | project["scripts"]
scripts = {
	name: REPO_ROOT / (entry_point.split(":", 1)[0].replace(".", "/") + ".py")
	for name, entry_point in entry_points.items()
}

# These extensions are loaded through ctypes, so import analysis cannot discover them
native_binaries = []
for name in ("libhiddrv", "libsc_by_bt", "libremotepad", "libcemuhook"):
	module = find_spec(name)
	if module is None or module.origin is None:
		raise ModuleNotFoundError(f"{name} is missing; build and install sc-controller before packaging")
	native_binaries.append((module.origin, "."))


python_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
msys64_path = Path(find_msys64_path())
print(f"Found msys64 path: {msys64_path}")

a = Analysis(
	list(scripts.values()),
	pathex=[],
	binaries=native_binaries + collect_dynamic_libs("vgamepad") + [
		(str(Path(sys.base_prefix) / "bin" / "libusb-1.0.dll"), "."),
	],
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
		"scc.lib",
		"scc.x11",
		"scc.osd",
		"scc.foreign",
		"scc.gui",
		"scc.gui.app",
		"scc.gui.ae",
		"scc.gui.importexport",
		"scc.gui.creg",
	] + collect_submodules("scc.gui.ae") + collect_submodules(
		"scc.drivers",
		filter=lambda name: not name.startswith(("scc.drivers.linux", "scc.drivers.macos")),
	) + collect_submodules("scc.drivers.windows"),
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

# Each executable runs the common runtime hooks, then only its own entry point.
entry_point_paths = {path.resolve() for path in scripts.values()}
runtime_hooks = [script for script in a.scripts if Path(script[1]).resolve() not in entry_point_paths]
executables = []
for name, path in scripts.items():
	entry_script = next(script for script in a.scripts if Path(script[1]).resolve() == path.resolve())
	executables.append(EXE(
		pyz,
		[*runtime_hooks, entry_script],
		[],
		exclude_binaries=True,
		name=name,
		debug=False,
		bootloader_ignore_signals=False,
		strip=False,
		upx=True,
		console=name not in project["gui-scripts"],
		disable_windowed_traceback=False,
		argv_emulation=False,
		target_arch=None,
		codesign_identity=None,
		entitlements_file=None,
	))
coll = COLLECT(
	*executables,
	a.binaries,
	a.datas,
	strip=False,
	upx=True,
	upx_exclude=[],
	name="sc-controller",
)
