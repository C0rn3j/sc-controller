#!/usr/bin/env python
"""Run through all the *.py files and import them

This lets us see surface-level deprecations that we should probably take care of such as:
  scc.gui.ae.dpad: /home/user/Projects/sc-controller/scc/gui/icon_chooser.py:182: PyGIDeprecationWarning: GObject.property is deprecated; use GObject.Property instead
"""
import subprocess
import sys
from pathlib import Path

root = Path("scc")

modules = []
for path in root.rglob("*.py"):
	parts = path.with_suffix("").parts

	# Files containing "-" cannot be easily imported as Python modules.
	if any("-" in part for part in parts):
		print(f"{path} has a dash in it - rename it!")
		continue

	if parts[-1] == "__init__":
		parts = parts[:-1]

	modules.append(".".join(parts))

for module in sorted(set(modules)):
	command = [
		sys.executable,
		"-W", "always::DeprecationWarning",
		"-W", "always::PendingDeprecationWarning",
		"-c", f"import {module}",
	]

	try:
		result = subprocess.run(
			command,
			text=True,
			capture_output=True,
			timeout=10,
		)
	except subprocess.TimeoutExpired:
		print(f"{module}: IMPORT TIMED OUT")
		continue

	warnings = [
		line
		for line in result.stderr.splitlines()
		if "DeprecationWarning" in line
	]

	for warning in warnings:
		print(f"{module}: {warning}")

	if result.returncode and not warnings:
		last_line = result.stderr.splitlines()[-1:] or ["unknown error"]
		print(f"{module}: IMPORT FAILED: {last_line[0]}")
