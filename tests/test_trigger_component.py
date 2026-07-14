import pytest

pytest.importorskip("gi", reason="PyGObject is required for trigger GUI tests")

from scc.actions import Action, ButtonAction, MultiAction, TriggerAction
from scc.constants import TRIGGER_CLICK, TRIGGER_HALF, TRIGGER_MAX
from scc.gui.ae.trigger import TriggerComponent
from scc.uinput import Keys


def split(action: TriggerAction | MultiAction) -> tuple[Action, Action]:
	success, partial, full, analog = TriggerComponent._split(action)
	assert success
	assert not analog
	return partial, full


def test_split_partial_only_trigger() -> None:
	action = ButtonAction(Keys.BTN_LEFT)
	partial, full = split(TriggerAction(TRIGGER_HALF, TRIGGER_MAX, action))

	assert partial.action is action
	assert not full


def test_split_full_only_trigger() -> None:
	action = ButtonAction(Keys.BTN_RIGHT)
	partial, full = split(TriggerAction(TRIGGER_CLICK, action))

	assert not partial
	assert full.action is action


def test_split_legacy_full_only_trigger() -> None:
	action = ButtonAction(Keys.BTN_RIGHT)
	partial, full = split(TriggerAction(TRIGGER_CLICK, TRIGGER_MAX, action))

	assert not partial
	assert full.action is action


def test_split_partial_and_full_triggers() -> None:
	partial_action = ButtonAction(Keys.BTN_LEFT)
	full_action = ButtonAction(Keys.BTN_RIGHT)
	action = MultiAction(
		TriggerAction(TRIGGER_HALF, TRIGGER_MAX, partial_action),
		TriggerAction(TRIGGER_CLICK, full_action),
	)
	partial, full = split(action)

	assert partial.action is partial_action
	assert full.action is full_action
