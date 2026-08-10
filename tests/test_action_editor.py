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
		shown = [k for k, (trash, scl, trash2) in editor.feedback_effect_rows.items() if scl.get_visible()]
		assert shown == list(cls.PARAMS), (
			"%s shows rows %s but declares %s" % (cls.LABEL, shown, cls.PARAMS))
		assert editor.get_feedback_effect() == cls.EFFECT


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
			editor.feedback_effect_rows[key][1].set_value(100 + n * 37)
		editor.update_modifiers()
		before = editor.generate_modifiers(MouseAction()).to_string()
		editor.update_modifiers()          # a rebuild triggered by anything else
		after = editor.generate_modifiers(MouseAction()).to_string()
		assert before == after, "%s lost its settings on rebuild" % (cls.LABEL,)
		assert cls.COMMAND in after, "%s did not survive as %s" % (cls.LABEL, cls.COMMAND)


def test_loading_an_effect_restores_the_widgets(editor):
	from scc.actions import MouseAction
	from scc.constants import HapticEffect, HapticPos
	from scc.modifiers import FeedbackToneModifier

	editor._recursing = True
	editor.load_modifiers(FeedbackToneModifier(HapticPos.RIGHT, 512, 220, 300, 4, 128, MouseAction()))
	editor._recursing = False

	assert editor.get_feedback_effect() == HapticEffect.TONE
	assert editor.feedback_effect == HapticEffect.TONE
	assert editor.feedback_effect_rows["tone_frequency"][1].get_value() == 220
	assert editor.feedback_effect_rows["duration"][1].get_value() == 300
	assert editor.feedback_params["lfo_depth"] == 128
