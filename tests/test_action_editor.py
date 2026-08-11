"""Action editor smoke tests.

These construct the real ActionEditor against a stub app. They exist because
the GUI is the one part of this codebase the rest of the suite cannot reach --
importing it loads Gtk, so it was left untested, and two bugs shipped that
opening the editor would have caught immediately: a missing class attribute
that made it fail to construct at all, and effect settings being dropped
whenever anything else rebuilt the editor from its state.

Skipped without a display. Run them under `xvfb-run -a python -m pytest` to
get the coverage on a headless machine.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
	not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"),
	reason="needs a display; try xvfb-run",
)


@pytest.fixture
def editor():
	import gi

	gi.require_version("Gtk", "3.0")
	gi.require_version("Gdk", "3.0")
	import scc.actions  # noqa: F401  (import order: the GUI needs it first)
	from scc.gui.action_editor import ActionEditor
	from scc.paths import get_share_path

	class FakeController:
		def get_type(self):
			return "sc2"

	class FakeSwitcher:
		def get_controller(self):
			return FakeController()

	class FakeApp:
		gladepath = os.path.join(os.getcwd(), "glade")
		imagepath = os.path.join(get_share_path(), "images")
		profile_switchers = (FakeSwitcher(),)

		def __getattr__(self, name):
			return lambda *a, **kw: None

	ae = ActionEditor(FakeApp(), lambda *a: None)
	ae._modifiers_enabled = True
	return ae


def test_constructs(editor):
	"""It used to raise AttributeError during setup_widgets."""
	assert editor.window is not None


def test_effect_rows_follow_the_chosen_effect(editor):
	from scc.modifiers import HAPTIC_EFFECT_MODIFIERS

	for i, cls in enumerate(HAPTIC_EFFECT_MODIFIERS):
		editor._cbFeedbackEffect.set_active(i)
		shown = [k for k, (trash, trash2, field, trash3)
			in editor.feedback_effect_rows.items() if field.get_visible()]
		assert shown == list(cls.PARAMS), (
			"%s shows rows %s but declares %s" % (cls.LABEL, shown, cls.PARAMS))
		assert editor.get_feedback_effect() == cls.EFFECT

		# the rows are hidden, not absent, so any show_all() further up the tree
		# would put every one of them back on screen
		editor.window.show_all()
		still_shown = [k for k, (trash, trash2, field, trash3)
			in editor.feedback_effect_rows.items() if field.get_visible()]
		assert still_shown == list(cls.PARAMS), (
			"%s revived rows %s after show_all" % (cls.LABEL, still_shown))


def test_effect_survives_a_rebuild(editor):
	"""update_modifiers() rebuilds the action from tracked state. Anything it
	does not track is silently lost the next time some other change fires it.
	"""
	from scc.actions import MouseAction
	from scc.constants import HapticEffect
	from scc.modifiers import HAPTIC_EFFECT_MODIFIERS

	editor.builder.get_object("cbFeedback").set_active(True)
	for i, cls in enumerate(HAPTIC_EFFECT_MODIFIERS):
		if cls.EFFECT == HapticEffect.CLICK:
			continue
		editor._cbFeedbackEffect.set_active(i)
		for n, key in enumerate(cls.PARAMS):
			# via the accessor: some rows are dropdowns, not scales
			editor._set_row_value(key, 100 + n * 37)
		editor.update_modifiers()
		before = editor.generate_modifiers(MouseAction()).to_string()
		editor.update_modifiers()          # a rebuild triggered by anything else
		after = editor.generate_modifiers(MouseAction()).to_string()
		assert before == after, "%s lost its settings on rebuild" % (cls.LABEL,)
		assert cls.COMMAND in after, "%s did not survive as %s" % (cls.LABEL, cls.COMMAND)


def test_opening_the_editor_keeps_the_feedback(editor):
	"""Open a saved binding the way the GUI does, and get back what was saved.

	set_input() is the real entry point, and it is the one that broke: writing
	the effect widgets while load_modifiers was still parsing fired their
	'changed' handlers, and update_modifiers rebuilt the action from an editor
	that had not applied the feedback yet -- so the dialog came up with no
	action at all and feedback switched off.
	"""
	from scc.actions import MouseAction
	from scc.constants import HapticPos
	from scc.modifiers import FeedbackToneModifier
	from scc.profile import Profile

	action = FeedbackToneModifier(HapticPos.RIGHT, 512, 220, 300, 4, 128, MouseAction())
	editor.set_input(Profile.RPAD, action)

	assert editor.builder.get_object("entAction").get_text() == action.to_string()
	assert editor.builder.get_object("cbFeedback").get_active()
	assert editor.feedback_position == HapticPos.RIGHT
	assert editor.generate_modifiers(editor._action).to_string() == action.to_string()


def test_loading_an_effect_restores_the_widgets(editor):
	from scc.actions import MouseAction
	from scc.constants import HapticEffect, HapticPos
	from scc.modifiers import FeedbackToneModifier
	from scc.profile import Profile

	editor.set_input(Profile.RPAD,
		FeedbackToneModifier(HapticPos.RIGHT, 512, 220, 300, 4, 128, MouseAction()))

	assert editor.get_feedback_effect() == HapticEffect.TONE
	assert editor.feedback_effect == HapticEffect.TONE
	assert editor._row_value("tone_frequency") == 220
	assert editor._row_value("duration") == 300
	assert editor.feedback_params["lfo_depth"] == 128


def test_preset_row_is_a_named_dropdown(editor):
	"""The firmware presets are an enumeration, not a magnitude, so they get
	names rather than a 0-255 slider.
	"""
	import gi

	gi.require_version("Gtk", "3.0")
	from gi.repository import Gtk

	from scc.modifiers import HAPTIC_SCRIPTS

	trash, widget, trash2, trash3 = editor.feedback_effect_rows["script_id"]
	assert isinstance(widget, Gtk.ComboBoxText)
	for value, name in HAPTIC_SCRIPTS:
		editor._set_row_value("script_id", value)
		assert editor._row_value("script_id") == value

	# an id the firmware may have that our list does not must survive, not be
	# silently rewritten to something else
	editor._set_row_value("script_id", 0x42)
	assert editor._row_value("script_id") == 0x42


def test_numeric_rows_pair_a_slider_with_a_spin_button(editor):
	"""A slider alone cannot hit 220 Hz on a 20-1000 range: that is ~5 Hz per
	pixel. The spin button is how you land on a value exactly, and it shares the
	slider's adjustment so the two can never disagree.
	"""
	import gi

	gi.require_version("Gtk", "3.0")
	from gi.repository import Gtk

	trash, scale, field, trash2 = editor.feedback_effect_rows["tone_frequency"]
	spins = [w for w in field.get_children() if isinstance(w, Gtk.SpinButton)]
	assert len(spins) == 1
	assert spins[0].get_adjustment() is scale.get_adjustment()

	spins[0].set_value(223)
	assert editor._row_value("tone_frequency") == 223
	editor._set_row_value("tone_frequency", 447)
	assert spins[0].get_value_as_int() == 447

	# arrow keys and the spin button step by one; only Page Up/Down jumps
	adj = scale.get_adjustment()
	assert adj.get_step_increment() == 1
	assert adj.get_page_increment() > 1
