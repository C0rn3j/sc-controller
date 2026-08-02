"""Runtime behaviour of the gyro actions.

Driven through a fake mapper: the real one needs a daemon, a controller and
uinput devices.
"""
import math

from scc.actions import GyroAbsAction, GyroAction
from scc.constants import STICK_PAD_MAX, TRIGGER_MAX, ControllerFlags
from scc.uinput import Axes

# driver-side euler encoding: 2**15 / PI fixed point, see ControllerFlags.EUREL_GYROS
EUREL = 32768.0 / math.pi


class FakeGamepad:
	def __init__(self):
		self.events = {}

	def axisEvent(self, axis, value):
		self.events.setdefault(axis, []).append(value)


class FakeController:
	flags = ControllerFlags.EUREL_GYROS


class FakeState:
	rtrig = 0


class FakeMapper:
	def __init__(self):
		self.gamepad = FakeGamepad()
		self.syn_list = set()
		self.mouse_moves = []
		self.state = FakeState()
		self._controller = FakeController()

	def get_controller(self):
		return self._controller

	def mouse_move(self, dx, dy):
		self.mouse_moves.append((dx, dy))

	def send_feedback(self, *a):
		pass


def sweep(action, mapper, to_degrees, steps=20):
	"""Rotates all three gyro axes from neutral to 'to_degrees'."""
	prev = None
	for n in range(steps + 1):
		a = math.radians(to_degrees * n / steps)
		rates = (0, 0, 0) if prev is None else tuple([(a - prev) * 3000.0] * 3)
		prev = a
		q = int(a * EUREL)
		action.gyro(mapper, rates[0], rates[1], rates[2], q, q, q, 0)


def peak(mapper, axis):
	vals = mapper.gamepad.events[axis]
	return max(vals, key=abs)


class TestGyroAxisRange:
	"""A gyro bound to a trigger must use the trigger's own 0..255 range.

	Feeding it a stick-range value and clamping (what it used to do) threw
	away the negative half and saturated within a fraction of a degree, so
	the trigger behaved like a button.
	"""

	def test_absolute_trigger_is_proportional(self):
		m = FakeMapper()
		sweep(GyroAbsAction(Axes.ABS_Z), m, 20)
		# 20 of the 90 deg that deflect a stick fully -> ~22% of trigger travel
		assert 0.15 * TRIGGER_MAX < peak(m, Axes.ABS_Z) < 0.30 * TRIGGER_MAX

	def test_absolute_trigger_reaches_full_pull(self):
		m = FakeMapper()
		sweep(GyroAbsAction(Axes.ABS_Z), m, 90)
		assert peak(m, Axes.ABS_Z) == TRIGGER_MAX

	def test_absolute_trigger_rests_released(self):
		"""A trigger has to sit at 0 when the controller is not rotated."""
		m = FakeMapper()
		sweep(GyroAbsAction(Axes.ABS_Z), m, 0)
		assert set(m.gamepad.events[Axes.ABS_Z]) == {0}

	def test_relative_trigger_is_not_digital(self):
		m = FakeMapper()
		sweep(GyroAction(Axes.ABS_Z), m, -20)
		assert 0 < peak(m, Axes.ABS_Z) < TRIGGER_MAX

	def test_stick_range_is_unchanged(self):
		"""The rescale must apply to triggers only."""
		m = FakeMapper()
		sweep(GyroAbsAction(Axes.ABS_X), m, 90)
		assert peak(m, Axes.ABS_X) == STICK_PAD_MAX
