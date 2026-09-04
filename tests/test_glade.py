import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


GLADE_LOADER = """
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

Gtk.init()
Gtk.Builder().add_from_file(sys.argv[1])
"""


def _get_files():
	"""Generates list of all glade files in glade/ directory."""
	# TODO: Caching, when there is more than one test using this
	rv = []

	def recursive(path):
		for f in os.listdir(path):
			filename = os.path.join(path, f)
			if os.path.isdir(filename):
				recursive(filename)
			elif filename.endswith(".glade"):
				rv.append(filename)

	recursive("glade/")
	return sorted(rv)


def _check_ids(el, filename, parent_id):
	"""Recursively walks through tree and check if every object has ID"""
	for child in el:
		if child.tag == "object":
			msg = "Widget has no ID in %s; class %s; Parent id: %s" % (filename, child.attrib["class"], parent_id)
			assert child.attrib.get("id"), msg
			for subel in child:
				if subel.tag == "child":
					_check_ids(subel, filename, child.attrib["id"])


class TestGlade:
	"""Tests every glade file in glade/ directory (and subdirectories) for known
	problems that may cause GUI to crash in some environments.

	(one case on one environment so far)
	"""

	def test_every_widget_has_id(self):
		"""Tests if every defined widget has ID.
		Dummy widgets without ID are OK, in theory, but Ubuntu version
		of libglade crashes witht them :(
		"""
		for filename in _get_files():
			root = ET.parse(filename).getroot()
			_check_ids(root, filename, "<root element>")

	@pytest.mark.parametrize("filename", _get_files(), ids=lambda filename: filename)
	def test_no_gtk_deprecations(self, filename):
		"""Load each Glade file with fatal GTK diagnostics enabled."""
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
			[sys.executable, "-c", GLADE_LOADER, filename],
			env=env,
			check=False,
		)
		assert result.returncode == 0, f"GTK diagnostics failed for {filename}"
