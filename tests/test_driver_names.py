"""Platform HIDAPI driver names and legacy configuration migration."""

from copy import deepcopy
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


def test_platform_hidapi_modules_are_importable_and_ordered():
	from scc.drivers.macos import hidapi as macos_hidapi
	from scc.drivers.windows import hidapi as windows_hidapi

	assert macos_hidapi.init is windows_hidapi.init
	assert macos_hidapi.start is windows_hidapi.start
	assert "scc.drivers.windows.hidapi" in drivers.MOD_INIT_ORDER
	assert "scc.drivers.macos.hidapi" in drivers.MOD_INIT_ORDER
	assert "scc.drivers.windows.hiddrv" not in drivers.MOD_INIT_ORDER
	assert "scc.drivers.macos.hiddrv" not in drivers.MOD_INIT_ORDER
