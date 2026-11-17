"""Steam Controller (2015) dongle transport through HIDAPI."""

from scc.lib.sc_hidapi import HIDDriver, init_driver

_driver: HIDDriver | None = None


def init(daemon, config) -> bool:
	global _driver
	_driver = init_driver(daemon, config, "sc_dongle", 0x1142, (1, 2, 3, 4))
	return _driver is not None


def start(daemon) -> None:
	if _driver is not None:
		_driver.scan()
