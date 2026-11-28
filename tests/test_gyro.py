"""Runtime behaviour of the gyro actions and of the analog modeshift gate.

Both are driven through a fake mapper: the real one needs a daemon, a
controller and uinput devices.
"""
import math

from scc.actions import GyroAbsAction, GyroAction, RangeOP
from scc.constants import STICK_PAD_MAX, TRIGGER_MAX, ControllerFlags, SCButtons
from scc.parser import ActionParser
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


class TestGyroSensitivity:
	"""Per-axis sensitivity used to be read from index 2 for every axis and
	then applied a second time per-axis, squaring it.
	"""

	def test_applied_once(self):
		plain, scaled = FakeMapper(), FakeMapper()
		a = GyroAbsAction(Axes.ABS_X)
		sweep(a, plain, 10)
		b = GyroAbsAction(Axes.ABS_X)
		b.set_speed(2.0, 2.0, 2.0)
		sweep(b, scaled, 10)
		assert peak(scaled, Axes.ABS_X) == 2 * peak(plain, Axes.ABS_X)

	def test_is_per_axis(self):
		"""Sensitivity of gyro axis 0 must not be taken from axis 2."""
		m = FakeMapper()
		a = GyroAbsAction(Axes.ABS_X, Axes.ABS_Y, Axes.ABS_RX)
		a.set_speed(1.0, 1.0, 3.0)
		sweep(a, m, 10)
		assert peak(m, Axes.ABS_RX) == 3 * peak(m, Axes.ABS_X)

	def test_moves_the_full_deflection_point(self):
		"""Sensitivity has to change the rotation needed to peg the axis, not
		just scale a value that already saturated at 90 deg.
		"""
		m = FakeMapper()
		a = GyroAbsAction(Axes.ABS_X)
		a.set_speed(3.0, 3.0, 3.0)
		sweep(a, m, 35)  # 3x35 deg is past the 90 deg full-deflection point
		assert peak(m, Axes.ABS_X) == STICK_PAD_MAX


class TestRangeOPHysteresis:
	"""`mode(RT >= 0.7, ...)` must not flip while the trigger is parked near
	the threshold: every flip runs ModeModifier's switch path, which recenters
	gyro references and releases held buttons.
	"""

	def test_holds_through_jitter(self):
		m = FakeMapper()
		op = RangeOP(SCButtons.RT, ">=", 0.7)
		m.state.rtrig = int(0.9 * TRIGGER_MAX)
		assert op(m)
		# dip just under the raw threshold, still inside the hysteresis band
		m.state.rtrig = int((0.7 - RangeOP.HYSTERESIS / 2) * TRIGGER_MAX)
		assert op(m)

	def test_still_releases(self):
		m = FakeMapper()
		op = RangeOP(SCButtons.RT, ">=", 0.7)
		m.state.rtrig = int(0.9 * TRIGGER_MAX)
		assert op(m)
		m.state.rtrig = int((0.7 - 2 * RangeOP.HYSTERESIS) * TRIGGER_MAX)
		assert not op(m)

	def test_needs_the_full_threshold_to_engage(self):
		"""Approaching from below, the band tightens rather than loosens."""
		m = FakeMapper()
		op = RangeOP(SCButtons.RT, ">=", 0.7)
		m.state.rtrig = int((0.7 + RangeOP.HYSTERESIS / 2) * TRIGGER_MAX)
		assert not op(m)
		m.state.rtrig = int((0.7 + 2 * RangeOP.HYSTERESIS) * TRIGGER_MAX)
		assert op(m)

	def test_less_than_direction(self):
		m = FakeMapper()
		op = RangeOP(SCButtons.RT, "<", 0.3)
		m.state.rtrig = 0
		assert op(m)
		m.state.rtrig = int((0.3 + RangeOP.HYSTERESIS / 2) * TRIGGER_MAX)
		assert op(m)
		m.state.rtrig = int((0.3 + 2 * RangeOP.HYSTERESIS) * TRIGGER_MAX)
		assert not op(m)

	def test_gated_absolute_gyro_survives_jitter(self):
		"""End to end: the reported symptom was an absolute gyro producing
		nothing at all when gated behind a trigger held at 70%.
		"""
		action = ActionParser().restart("mode(RT >= 0.7, gyroabs(Axes.ABS_X), None)").parse().compress()
		m = FakeMapper()
		prev = None
		for n in range(21):
			m.state.rtrig = TRIGGER_MAX if n % 3 else int(0.69 * TRIGGER_MAX)
			a = math.radians(20.0 * n / 20)
			rate = 0 if prev is None else (a - prev) * 3000.0
			prev = a
			q = int(a * EUREL)
			action.gyro(m, rate, rate, rate, q, q, q, 0)
		assert peak(m, Axes.ABS_X) > 0.15 * STICK_PAD_MAX


class TestFeedbackEffects:
	"""The action editor drives its effect chooser entirely off these classes.
	A missing attribute on any one of them crashes the editor on construction,
	as FeedbackModifier lacking PARAMS did -- so check every entry, not just
	the ones that were interesting to write.
	"""

	def test_every_effect_is_complete(self):
		import scc.actions  # noqa: F401  (import order: modifiers needs it first)
		from scc.modifiers import HAPTIC_EFFECT_MODIFIERS

		assert HAPTIC_EFFECT_MODIFIERS
		seen = set()
		for cls in HAPTIC_EFFECT_MODIFIERS:
			for attr in ("EFFECT", "PARAMS", "LABEL", "COMMAND"):
				assert hasattr(cls, attr), "%s has no %s" % (cls.__name__, attr)
			assert cls.EFFECT not in seen, "duplicate effect on %s" % (cls.__name__,)
			seen.add(cls.EFFECT)

	def test_params_are_real_haptic_fields(self):
		import scc.actions  # noqa: F401
		from scc.constants import HapticPos
		from scc.controller import HapticData
		from scc.modifiers import HAPTIC_EFFECT_MODIFIERS

		h = HapticData(HapticPos.LEFT)
		for cls in HAPTIC_EFFECT_MODIFIERS:
			for name in cls.PARAMS:
				assert hasattr(h, name), (
					"%s.PARAMS names %r, which HapticData does not carry"
					% (cls.__name__, name))


class TestFeedbackEffectSignatures:
	"""The action editor builds each effect modifier positionally from its
	PARAMS. If PARAMS and the signature drift apart the GUI silently writes
	values into the wrong parameter -- which it did once, feeding amplitude
	into script_id.
	"""

	def test_params_match_signatures(self):
		import inspect

		from scc.modifiers import (
			FeedbackScriptModifier,
			FeedbackSweepModifier,
			FeedbackToneModifier,
		)

		for cls in (FeedbackToneModifier, FeedbackSweepModifier, FeedbackScriptModifier):
			args = inspect.getfullargspec(cls._mod_init).args
			assert args == ["self", "position", "amplitude", *cls.PARAMS], (
				"%s signature %s does not match PARAMS %s"
				% (cls.__name__, args, cls.PARAMS))
