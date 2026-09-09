import json

from scc.device_config import DEVICE_CONFIG_VERSION, load_device_config, migrate_device_config


def legacy_config() -> dict:
	return {
		"buttons": {
			"304": "STICK",
			"305": "STICKPRESS",
			"306": "RPAD",
			"307": "A",
		},
		"axes": {
			"0": {"axis": "stick_x", "min": -1, "max": 1},
			"1": {"axis": "stick_y", "min": -1, "max": 1},
			"2": {"axis": "rpad_x", "min": -1, "max": 1},
			"3": {"axis": "rpad_y", "min": -1, "max": 1},
			"4": {"axis": "lpad_x", "min": -1, "max": 1},
			"5": {"axis": "lpad_y", "min": -1, "max": 1},
			"6": {"axis": "ltrig", "min": 0, "max": 255},
		},
		"dpads": {
			"16": {"axis": "lpad_x", "positive": True, "min": -1, "max": 1},
		},
	}


def test_missing_version_is_migrated_from_zero() -> None:
	config = legacy_config()

	assert migrate_device_config(config)
	assert config["version"] == DEVICE_CONFIG_VERSION
	assert [axis["axis"] for axis in config["axes"].values()] == [
		"lstick_x",
		"lstick_y",
		"rstick_x",
		"rstick_y",
		"dpad_x",
		"dpad_y",
		"ltrig",
	]
	assert config["dpads"]["16"]["axis"] == "dpad_x"
	assert config["buttons"] == {
		"304": "LSTICKPRESS",
		"305": "LSTICKPRESS",
		"306": "RSTICKPRESS",
		"307": "A",
	}


def test_current_config_is_not_changed() -> None:
	config = {"version": DEVICE_CONFIG_VERSION, "buttons": {"304": "STICK"}}

	assert not migrate_device_config(config)
	assert config["buttons"]["304"] == "STICK"


def test_loading_persists_migration(tmp_path) -> None:
	filename = tmp_path / "evdev-Test.json"
	filename.write_text(json.dumps(legacy_config()))

	config = load_device_config(str(filename))

	assert json.loads(filename.read_text()) == config
	assert config["version"] == DEVICE_CONFIG_VERSION
