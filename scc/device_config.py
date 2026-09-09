"""Loading and migration of registered-controller configurations.

Pre-1.1:
  Evdev profiles predate the dedicated d-pad and right-stick axes and used the touchpads.
  Real touchpads should never be assigned to an evdev device, so we just rewrite the legacy values.
  Since we're never going to be loading a real LPAD/RPAD from these, automated migrations are safe.
"""

import json
import logging

log = logging.getLogger("DeviceConfig")

DEVICE_CONFIG_VERSION = 1.1

LEGACY_AXES = {
	"stick_x": "lstick_x",
	"stick_y": "lstick_y",
	"rpad_x": "rstick_x",
	"rpad_y": "rstick_y",
	"lpad_x": "dpad_x",
	"lpad_y": "dpad_y",
}

LEGACY_BUTTONS = {
	"STICK": "LSTICKPRESS",
	"STICKPRESS": "LSTICKPRESS",
	"RPAD": "RSTICKPRESS",
}


def migrate_device_config(config: dict) -> bool:
	"""Migrate a registered-controller configuration in place.

	Configurations written before versioning was added are treated as version
	0.0. Returns whether the configuration was changed.
	"""
	try:
		version = float(config.get("version", 0.0))
	except (TypeError, ValueError):
		log.warning("Invalid registered-controller config version; assuming version 0.0")
		version = 0.0

	if version >= DEVICE_CONFIG_VERSION:
		return False

	for section in ("axes", "dpads"):
		for axis in config.get(section, {}).values():
			if isinstance(axis, dict) and "axis" in axis:
				axis["axis"] = LEGACY_AXES.get(axis.get("axis"), axis.get("axis"))

	for code, button in config.get("buttons", {}).items():
		config["buttons"][code] = LEGACY_BUTTONS.get(button, button)

	config["version"] = DEVICE_CONFIG_VERSION
	return True


def load_device_config(filename: str) -> dict:
	"""Load a registered-controller configuration and persist migrations."""
	with open(filename) as file:
		config = json.load(file)

	if migrate_device_config(config):
		try:
			with open(filename, "w") as file:
				json.dump(config, file, sort_keys=True, indent=4, separators=(",", ": "))
		except OSError:
			# The migrated data is still usable for this process. Try persisting it
			# again the next time the configuration is loaded.
			log.exception("Failed to save migrated registered-controller config: %s", filename)

	return config
