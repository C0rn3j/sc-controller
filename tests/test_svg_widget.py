from xml.etree import ElementTree as ET

import gi
import pytest

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")

from scc.gui.svg_widget import SVGEditor, SVGWidget


def test_area_bounds_apply_nonuniform_parent_scale() -> None:
	tree = ET.fromstring(
		'<svg><g transform="matrix(2,0,0,3,10,20)">'
		'<rect id="AREA_TEST" x="4" y="5" width="6" height="7" />'
		"</g></svg>",
	)
	areas = []

	SVGWidget.find_areas(tree, None, areas)

	assert (areas[0].x, areas[0].y, areas[0].w, areas[0].h) == (18, 35, 12, 21)


def test_area_bounds_enclose_rotated_rectangle() -> None:
	tree = ET.fromstring(
		'<svg><g transform="rotate(90)">'
		'<rect id="AREA_TEST" x="10" y="20" width="30" height="40" />'
		"</g></svg>",
	)
	areas = []

	SVGWidget.find_areas(tree, None, areas)

	assert (areas[0].x, areas[0].y, areas[0].w, areas[0].h) == pytest.approx((-60, 10, 40, 30))


def test_clone_element_deep_copies_children() -> None:
	editor = SVGEditor('<svg><g id="source"><rect id="child" /></g></svg>')

	clone = editor.clone_element("source")

	assert clone is not None
	assert clone is not SVGEditor.get_element(editor, "source")
	assert clone[0] is not SVGEditor.get_element(editor, "child")
	clone[0].attrib["id"] = "changed"
	assert SVGEditor.get_element(editor, "child").attrib["id"] == "child"


def test_remove_element_from_clone() -> None:
	editor = SVGEditor('<svg><g id="source"><rect id="child" /></g></svg>')
	clone = editor.clone_element("source")

	assert clone is not None
	child = SVGEditor.get_element(clone, "child")
	assert child is not None

	editor.remove_element(child)

	assert SVGEditor.get_element(clone, "child") is None


def test_recolor_group_preserves_text_fill() -> None:
	editor = SVGEditor(
		'<svg><g id="button">'
		'<circle id="background" style="fill:#666666;opacity:0" />'
		'<text id="label" style="fill:#000000;opacity:0"><tspan>L5</tspan></text>'
		"</g></svg>",
	)
	button = SVGEditor.get_element(editor, "button")
	background = SVGEditor.get_element(editor, "background")
	label = SVGEditor.get_element(editor, "label")

	assert button is not None
	assert background is not None
	assert label is not None
	assert SVGEditor.recolor(button, "#FF60A0FF")
	assert "fill:#60A0FF" in background.attrib["style"]
	assert "opacity:1.0" in background.attrib["style"]
	assert "fill:#000000" in label.attrib["style"]
	assert "opacity:1.0" in label.attrib["style"]
