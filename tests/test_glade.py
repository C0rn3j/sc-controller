import os
import xml.etree.ElementTree as ET


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
	return rv


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


def _adjustment(filename, id_):
	"""Returns a GtkAdjustment's properties as floats."""
	root = ET.parse(filename).getroot()
	for obj in root.iter("object"):
		if obj.get("class") == "GtkAdjustment" and obj.get("id") == id_:
			return {p.get("name"): float(p.text) for p in obj.iter("property")}
	raise AssertionError("no adjustment %s in %s" % (id_, filename))


def test_haptic_strength_slider_reaches_the_amplitude_the_driver_accepts():
	"""A GtkAdjustment's usable maximum is upper - page_size, and page_size means
	nothing for a slider. Left at 128 it stopped the haptic Strength slider at
	32639, which reads to a user as an off-by-something rather than as a limit.

	Some adjustments do use page-size deliberately (global_settings sets
	upper 10.01 / page-size 0.01 to land on a round 10.00), so this pins the one
	value that has to agree with the driver rather than banning the property.
	"""
	from scc.drivers.sc2 import HAPTIC_AMPLITUDE_MAX, HAPTIC_AMPLITUDE_MIN

	adj = _adjustment("glade/action_editor.glade", "adjFAmplitude")
	assert adj["lower"] == HAPTIC_AMPLITUDE_MIN
	assert adj["upper"] - adj.get("page-size", 0) == HAPTIC_AMPLITUDE_MAX
