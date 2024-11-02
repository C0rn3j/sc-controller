import inspect

from scc.actions import Action, AxisAction, ButtonAction, MouseAction
from scc.constants import STICK, HapticPos, SCButtons
from scc.modifiers import *
from scc.uinput import Axes, Keys, Rels

from . import _parses_as, parser


class TestModifiers:

	# TODO: Much more tests
	# TODO: test_tests

	def test_ball(self):
		"""Test if BallModifier can be converted from string"""
		# All options
		assert _parses_as(
			"ball(15, 40, 15, 0.1, 3265, 4, axis(ABS_X))",
			BallModifier(15, 40, 15, 0.1, 3265, 4, AxisAction(Axes.ABS_X))
		)
