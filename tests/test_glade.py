import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest


def _get_files():
	"""Generates list of all glade files in glade/ directory."""
	# TODO: Caching, when there is more than one test using this
	rv = []

	def recursive(path):
		for f in os.listdir(path):
			filename = os.path.join(path, f)
			if os.path.isdir(filename):
				recursive(filename)
			elif filename.endswith((".glade", ".ui")):
				rv.append(filename)

	recursive("glade/")
	return sorted(rv)


class TestGlade:
	"""Tests every glade file in glade/ directory (and subdirectories) for known problems that may cause GUI to crash in some environments.

	(one case on one environment so far)
	"""

	def test_every_toplevel_object_has_id(self) -> None:
		"""Ensure every top-level builder object can be addressed by ID.

		GTK4 supports anonymous nested widgets, controllers, layout objects,
		and other implementation details, so those do not require IDs.
		"""
		for filename in _get_files():
			root = ET.parse(filename).getroot()
			for obj in root.findall("object"):
				msg = f"Top-level object has no ID in {filename}; class {obj.attrib['class']}"
				assert obj.attrib.get("id"), msg

	@pytest.mark.parametrize("filename", _get_files(), ids=lambda filename: filename)
	def test_no_gtk_deprecations(self, filename):
		"""Validate each UI file with GTK's static deprecation checks."""
		validator = shutil.which("gtk4-builder-tool")
		assert validator is not None, "gtk4-builder-tool is required to validate UI files"
		env = os.environ.copy()
		env.update(
			{
				"G_ENABLE_DIAGNOSTIC": "1",
				"G_DEBUG": "fatal-warnings",
				"GTK_A11Y": "test",
			},
		)
		print(f"Validating GTK diagnostics: {filename}", flush=True)
		result = subprocess.run(
			[validator, "validate", "--deprecations", filename],
			env=env,
			check=False,
			capture_output=True,
			text=True,
		)
		diagnostics = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
		assert result.returncode == 0 and not diagnostics, (
			f"GTK diagnostics failed for {filename}\n{diagnostics}"
		)
