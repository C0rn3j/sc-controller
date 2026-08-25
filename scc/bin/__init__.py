"""SC-Controller executables."""

import logging
import os
import sys

# https://docs.python.org/3/library/warnings.html
logging.captureWarnings(capture=True)
if not sys.warnoptions:
	import warnings

	warnings.simplefilter("default")
	os.environ["PYTHONWARNINGS"] = "default"  # Also affect subprocesses
