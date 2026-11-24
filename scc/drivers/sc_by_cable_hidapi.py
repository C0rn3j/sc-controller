"""Steam Controller (2015) by_cable transport through HIDAPI."""

from scc.lib.sc_hidapi import HIDDriver, init_driver

_driver: HIDDriver | None = None


def init(daemon, config) -> bool:
	global _driver
	_driver = init_driver(daemon, config, "sc_by_cable", 0x1102, (2,), wired=True)
	return _driver is not None


def start(daemon) -> None:
	if _driver is not None:
		_driver.scan()
