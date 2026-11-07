"""Optional, manually registered HIDAPI controllers on Linux."""

import logging

from scc.drivers.windows import hiddrv

_driver = None


def init(daemon, config):
	global _driver
	if hiddrv.hid is None:
		logging.getLogger("HIDAPI").error("Install sccontroller[hidapi] to enable the HIDAPI backend")
		return False
	_driver = hiddrv.WindowsHIDDriver(daemon, autodetect=False)
	daemon.add_mainloop(_driver.mainloop)
	daemon.add_on_exit(_driver.close)
	daemon.add_on_rescan(_driver.rescan)
	return True


def start(daemon):
	if _driver is not None:
		_driver.start()
