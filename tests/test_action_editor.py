from unittest.mock import Mock

import pytest

gi = pytest.importorskip("gi", reason="PyGObject is required for action editor tests")
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

from scc.actions import ButtonAction
from scc.constants import HapticPos
from scc.gui.action_editor import ActionEditor
from scc.modifiers import FeedbackModifier
from scc.uinput import Keys


def test_custom_feedback_count_is_preserved() -> None:
	editor = ActionEditor.__new__(ActionEditor)
	editor._modifiers_enabled = True
	editor.feedback_position = HapticPos.BOTH
	editor.feedback = [32767, 4, 1024]
	editor.feedback_count = 64
	editor.feedback_widgets = [(None, None, None, default) for default in (512, 4, 1024)]
	editor.osd = False

	feedback_side = Mock()
	feedback_side.get_active.return_value = 2
	editor.builder = Mock()
	editor.builder.get_object.side_effect = {
		"cbFeedbackSide": feedback_side,
		"cbFeedback": Mock(),
		"grFeedback": Mock(),
	}.get

	action = editor.generate_modifiers(ButtonAction(Keys.BTN_SOUTH), from_custom=True)

	assert isinstance(action, FeedbackModifier)
	assert action.haptic.data == (HapticPos.BOTH, 32767, 1024, 64)
