from unittest.mock import Mock, patch

import pytest

from scc.actions import BASE_STICK_MOUSE_SPEED, MouseAction
from scc.constants import FE_STICK, RSTICK, STICK_PAD_MAX
from scc.mapper import Mapper


def make_resampling_mapper() -> Mapper:
	mapper = object.__new__(Mapper)
	mapper.controller = Mock()
	mapper.controller.is_bluetooth.return_value = True
	mapper.mouse = Mock()
	mapper.schedule = Mock(return_value=Mock())
	mapper._bt_stick_mouse_velocities = {}
	mapper._bt_stick_mouse_task = None
	mapper._bt_stick_mouse_last_tick = 0.0
	mapper._bt_stick_mouse_logged = True
	return mapper


def test_bluetooth_stick_mouse_uses_velocity_resampler() -> None:
	mapper = Mock()
	mapper.force_event = set()
	mapper.set_bt_stick_mouse_velocity.return_value = True
	action = MouseAction()

	action.whole(mapper, STICK_PAD_MAX, 0, RSTICK)

	mapper.set_bt_stick_mouse_velocity.assert_called_once_with(
		action,
		RSTICK,
		BASE_STICK_MOUSE_SPEED,
		0.0,
	)
	mapper.mouse_move_stick.assert_not_called()
	assert FE_STICK in mapper.force_event


def test_bluetooth_stick_mouse_tick_integrates_velocity_at_fixed_rate() -> None:
	mapper = make_resampling_mapper()
	source = MouseAction()

	with patch("scc.mapper.time.monotonic", return_value=10.0):
		assert mapper.set_bt_stick_mouse_velocity(source, RSTICK, 100.0, 50.0)
	mapper._bt_stick_mouse_last_tick = 10.0
	with patch("scc.mapper.time.monotonic", return_value=10.008):
		mapper._tick_bt_stick_mouse(mapper)

	dx, dy, dt = mapper.mouse.moveStickEvent.call_args.args
	assert dx == pytest.approx(0.8)
	assert dy == pytest.approx(-0.4)
	assert dt == pytest.approx(0.008)
	assert mapper.schedule.call_count == 2


def test_bluetooth_stick_mouse_stops_when_centered() -> None:
	mapper = make_resampling_mapper()
	source = MouseAction()
	mapper.set_bt_stick_mouse_velocity(source, RSTICK, 100.0, 0.0)
	task = mapper._bt_stick_mouse_task

	mapper.set_bt_stick_mouse_velocity(source, RSTICK, 0.0, 0.0)

	task.cancel.assert_called_once_with()
	assert mapper._bt_stick_mouse_task is None
	assert not mapper._bt_stick_mouse_velocities
