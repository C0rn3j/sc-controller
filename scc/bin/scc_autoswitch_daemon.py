#!/usr/bin/env python3
"""SC-Controller - Autoswitch Daemon

Observes active window and commands scc-daemon to change profiles as needed.
"""

import logging
import os
import signal
import sys

from scc.x11.autoswitcher import AutoSwitcher

log = logging.getLogger("AS-Daemon")


def main() -> None:
	"""Run the X11 profile autoswitch daemon."""
	from scc.tools import init_logging, set_logging_level

	init_logging(suffix=" AS ")
	set_logging_level("debug" in sys.argv, "debug" in sys.argv)

	if "DISPLAY" not in os.environ:
		log.error("DISPLAY env variable not set.")
		sys.exit(1)

	d = AutoSwitcher()
	signal.signal(signal.SIGINT, d.sigint)
	d.run()
	sys.exit(d.exit_code)


if __name__ == "__main__":
	main()
