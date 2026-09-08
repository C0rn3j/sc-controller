"""SC-Controller executables."""

import logging
import os
import sys

# https://docs.python.org/3/library/warnings.html
logging.captureWarnings(capture=True)
if not sys.warnoptions:
	import warnings

	warnings.simplefilter("default")
	# 3.14 deprecated this and it is to be removed in 3.16
	# Shut it up meanwhile since it's not our problem to solve
	warnings.filterwarnings(
		"ignore",
		message=r"'asyncio\.AbstractEventLoopPolicy' is deprecated.*",
		category=DeprecationWarning,
		module=r"gi\.events",
	)
	warnings.filterwarnings(
		"ignore",
		message=r"'asyncio\.get_event_loop_policy' is deprecated.*",
		category=DeprecationWarning,
		module=r"gi\.events",
	)

	# Apply the same for subprocesses
	os.environ["PYTHONWARNINGS"] = (
		"default,ignore:'asyncio.AbstractEventLoopPolicy' is deprecated:DeprecationWarning:gi.events,ignore:'asyncio.get_event_loop_policy' is deprecated:DeprecationWarning:gi.events"
	)
