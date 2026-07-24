"""SC-Controller - Custom module loader

Loads ~/.config/scc/custom.py, if present. This allows injecting custom action
classes by user and breaking everything in very creative ways.

load_custom_module function needs to be called by daemon and GUI, so it exists
in separate module.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from scc.paths import get_config_path

if TYPE_CHECKING:
	from logging import Logger

def load_custom_module(log: Logger, who_calls: str = "daemon") -> bool:
	"""Loads and imports ~/.config/scc/custom.py, if it is present and displays big, fat warning in such case.

	Returns True if file exists.
	"""
	filename = os.path.join(get_config_path(), "custom.py")
	if os.path.exists(filename):
		log.warning("=" * 60)
		log.warning("Loading %s" % (filename,))
		log.warning(
			"If you don't know what this means or you haven't created it, stop daemon right now and remove this file.",
		)
		log.warning("")
		log.warning("Also try removing it if %s crashes shortly after this message." % (who_calls,))

		import imp

		imp.load_source("custom", filename)
		log.warning("=" * 60)
		return True
	return False
