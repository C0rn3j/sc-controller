"""Platform HIDAPI driver names and legacy configuration migration."""

from copy import deepcopy
from pathlib import Path
import pkgutil
from types import SimpleNamespace

import pytest

from scc import config, drivers


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize("enabled", [False, True])
def test_legacy_hidapi_driver_setting_is_renamed(monkeypatch, platform, enabled):
	monkeypatch.setattr(config, "sys", SimpleNamespace(platform=platform))
	# Match the defaults constructed when importing on the target platform.
	defaults = deepcopy(config.Config.DEFAULTS)
	defaults["drivers"].pop("hiddrv", None)
	defaults["drivers"]["hidapi"] = True
	monkeypatch.setattr(config.Config, "DEFAULTS", defaults)
	settings = object.__new__(config.Config)
	settings.values = {"drivers": {"hiddrv": enabled, "hidapi": False}}
	assert settings.check_values()
	assert settings.values["drivers"]["hidapi"] is enabled
	assert "hiddrv" not in settings.values["drivers"]
	assert not settings.check_values()


def test_linux_driver_settings_remain_separate(monkeypatch):
	monkeypatch.setattr(config, "sys", SimpleNamespace(platform="linux"))
	settings = object.__new__(config.Config)
	settings.values = {"drivers": {"hiddrv": True, "hidapi": False}}
	settings.check_values()
	assert settings.values["drivers"]["hiddrv"] is True
	assert settings.values["drivers"]["hidapi"] is False


@pytest.mark.parametrize("platform", ["linux", "windows", "macos"])
def test_shared_hidapi_is_discovered_once(platform):
	# Match the daemon's discovery of shared plus platform-specific modules.
	root = Path(drivers.__file__).parent
	modules = [
		module.name
		for path, prefix in ((root, "scc.drivers."), (root / platform, f"scc.drivers.{platform}."))
		for module in pkgutil.iter_modules([str(path)], prefix)
		if module.name.rsplit(".", 1)[-1] == "hidapi"
	]
	assert modules == ["scc.drivers.hidapi"]
	assert drivers.MOD_INIT_ORDER.count("scc.drivers.hidapi") == 1
