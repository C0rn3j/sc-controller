import pytest

pytest.importorskip("gi", reason="PyGObject is required for trigger GUI tests")

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Rsvg", "2.0")

from scc.gui.svg_widget import SVGEditor


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
