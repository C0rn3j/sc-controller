from types import SimpleNamespace

from scc.actions import AxisAction, XYAction
from scc.constants import FE_PAD, RSTICK
from scc.uinput import Axes


class Gamepad:
	def __init__(self) -> None:
		self.events = []

	def axisEvent(self, axis, value) -> None:
		self.events.append((axis, value))


def test_right_stick_does_not_force_right_pad_event() -> None:
	gamepad = Gamepad()
	mapper = SimpleNamespace(gamepad=gamepad, syn_list=set(), force_event=set())
	action = XYAction(AxisAction(Axes.ABS_RX), AxisAction(Axes.ABS_RY))

	action.whole(mapper, 12000, -8000, RSTICK)

	assert gamepad.events == [(Axes.ABS_RX, 12000), (Axes.ABS_RY, -8000)]
	assert FE_PAD not in mapper.force_event
