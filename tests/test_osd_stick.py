"""OSD-wrapped stick buttons display once for each activation."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scc.actions import ButtonAction
from scc.constants import LSTICK, RSTICK
from scc.parser import ActionParser
from scc.special_actions import OSDAction
from scc.uinput import Keys


@pytest.mark.parametrize("stick", [LSTICK, RSTICK])
@pytest.mark.parametrize("position", [(100, 0), (0, -100), (20000, 20000)])
def test_osd_stick_button_displays_once_until_released(monkeypatch, stick, position):
	action = ActionParser().restart("osd(button(Keys.BTN_GAMEPAD))").parse().compress()
	assert isinstance(action, OSDAction)
	press, release = Mock(), Mock()
	monkeypatch.setattr(ButtonAction, "_button_press", press)
	monkeypatch.setattr(ButtonAction, "_button_release", release)
	handler = Mock()
	mapper = SimpleNamespace(get_special_actions_handler=lambda: handler)

	action.whole(mapper, 0, 0, stick)
	action.whole(mapper, 99, -99, stick)
	press.assert_not_called()
	handler.on_sa_osd.assert_not_called()

	action.whole(mapper, *position, stick)
	press.assert_called_once_with(mapper, Keys.BTN_GAMEPAD, haptic=None)
	handler.on_sa_osd.assert_called_once_with(mapper, action)
	action.whole(mapper, -20000, 10000, stick)
	assert press.call_count == 1
	assert handler.on_sa_osd.call_count == 1

	action.whole(mapper, 0, 0, stick)
	release.assert_called_once_with(mapper, Keys.BTN_GAMEPAD)
	assert handler.on_sa_osd.call_count == 1
	action.whole(mapper, *position, stick)
	assert press.call_count == 2
	assert handler.on_sa_osd.call_count == 2


def test_osd_physical_button_behavior_is_unchanged(monkeypatch):
	press = Mock()
	monkeypatch.setattr(ButtonAction, "_button_press", press)
	action = OSDAction(ButtonAction(Keys.BTN_GAMEPAD))
	handler = Mock()
	mapper = SimpleNamespace(get_special_actions_handler=lambda: handler)
	action.button_press(mapper)
	handler.on_sa_osd.assert_called_once_with(mapper, action)
	press.assert_called_once()
