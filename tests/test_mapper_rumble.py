from unittest.mock import Mock

from scc.constants import HapticPos
from scc.mapper import Mapper


def make_mapper(*, level: int, duration: int, repetitions: int, controller_type: str) -> Mapper:
	mapper = object.__new__(Mapper)
	mapper.gamepad = Mock()
	mapper.gamepad.ff_read.return_value = Mock(level=level, duration=duration, repetitions=repetitions)
	mapper.controller = Mock()
	mapper.controller.get_type.return_value = controller_type
	mapper.feedbacks = [None, None]
	return mapper


def test_conventional_rumble_uses_normal_amplitude_and_duration() -> None:
	mapper = make_mapper(level=0x7FFF, duration=2000, repetitions=1, controller_type="ds4")

	mapper._rumble_ready(0, 0)

	mapper.controller.feedback.assert_called_once()
	position, amplitude, period, count = mapper.controller.feedback.call_args.args[0].data
	assert position == HapticPos.BOTH
	assert amplitude == 0x7FFF
	assert period * count / 0x10000 == 2.0
	assert mapper.feedbacks == [None, None]


def test_rumble_stop_event_has_zero_amplitude() -> None:
	mapper = make_mapper(level=0x7FFF, duration=1000, repetitions=0, controller_type="ds4")

	mapper._rumble_ready(0, 0)

	mapper.controller.feedback.assert_called_once()
	position, amplitude, period, count = mapper.controller.feedback.call_args.args[0].data
	assert position == HapticPos.BOTH
	assert amplitude == 0
	assert period == 1024
	assert count == 0
	assert mapper.feedbacks == [None, None]
