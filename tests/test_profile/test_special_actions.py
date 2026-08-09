from scc.actions import ButtonAction
from scc.constants import HapticPos, RSTICK, SCButtons
from scc.special_actions import *

from . import parser

MENU_CLASSES = (MenuAction, HorizontalMenuAction, GridMenuAction, RadialMenuAction, QuickMenuAction)


class TestSpecialActions:
	def test_menu_can_be_opened_and_controlled_with_right_stick(self):
		calls = []

		class Handler:
			def on_sa_menu(self, mapper, action, *args):
				calls.append(args)

		class Mapper:
			def get_special_actions_handler(self):
				return Handler()

		action = MenuAction("some.menu")
		action.whole(Mapper(), MenuAction.MIN_STICK_DISTANCE + 1, 0, RSTICK)

		args = calls[0]
		assert args[args.index("--control-with") + 1] == RSTICK
		assert args[args.index("--confirm-with") + 1] == SCButtons.RSTICKPRESS.name
		assert args[args.index("--cancel-with") + 1] == RSTICK

	# def test_tests(self):
	# Tests if this class has test for each known SpecialAction defined.
	# Removed: profile is not parsed this way anymore, so newly added actions
	# don't have to support what's tested.

	def test_profile(self):
		"""Tests if ChangeProfileAction is parsed correctly from json."""
		a = parser.from_json_data({"action": "profile('xyz')"})
		assert isinstance(a, ChangeProfileAction)
		assert a.profile == "xyz"

	def test_shell(self):
		"""Tests if ShellCommandAction is parsed correctly from json."""
		a = parser.from_json_data({"action": "shell('ls -la')"})
		assert isinstance(a, ShellCommandAction)
		assert a.command == "ls -la"

	def test_turnoff(self):
		"""Tests if TurnOffAction is parsed correctly from json."""
		a = parser.from_json_data({"action": "turnoff"})
		assert isinstance(a, TurnOffAction)

	def test_restart(self):
		"""Tests if RestartDaemonAction is parsed correctly from json."""
		a = parser.from_json_data({"action": "restart"})
		assert isinstance(a, RestartDaemonAction)

	def test_led(self):
		"""Tests if LockedAction is parsed correctly from json."""
		a = parser.from_json_data({"action": "led(66)"})
		assert isinstance(a, LedAction)
		assert a.brightness == 66

	def test_osd(self):
		"""Tests if OSDAction is parsed correctly from json."""
		# With text
		a = parser.from_json_data({"action": "osd('something')"})
		assert isinstance(a, OSDAction)
		assert a.text == "something"
		# As modifier
		a = parser.from_json_data({"action": "button(KEY_X)", "osd": True})
		assert isinstance(a, OSDAction)
		assert isinstance(a.action, ButtonAction)

	def test_dialog(self):
		"""Tests if all Menu*Actions are parsed correctly from json."""
		# Simple
		a = parser.from_json_data({"action": "dialog('title', osd('something'))"})
		assert isinstance(a, DialogAction)
		assert a.text == "title"
		assert len(a.options) == 1
		assert isinstance(a.options[0], OSDAction)
		assert a.options[0].text == "something"

		# Complete
		a = parser.from_json_data(
			{"action": "dialog(X, Y, 'title', name('button', osd('something')), name('item', osd('something else')))"},
		)
		assert a.confirm_with == SCButtons.X
		assert a.cancel_with == SCButtons.Y
		assert isinstance(a, DialogAction)
		assert a.text == "title"
		assert len(a.options) == 2
		assert a.options[0].describe(Action.AC_MENU) == "button"
		assert a.options[0].strip().text == "something"

	def test_menus(self):
		"""Tests if all Menu*Actions are parsed correctly from json."""
		for cls in MENU_CLASSES:
			a_str = "%s('some.menu', LEFT, X, Y, True)" % (cls.COMMAND,)
			a = parser.from_json_data({"action": a_str})
			assert isinstance(a, cls)
			assert a.control_with == HapticPos.LEFT
			assert a.confirm_with == SCButtons.X
			assert a.cancel_with == SCButtons.Y
			assert a.show_with_release == True

	def test_position(self):
		"""Tests if PositionModifier is parsed correctly from json."""
		a = parser.from_json_data({"action": "menu('some.menu', LEFT, X, Y, True)", "position": [-10, 10]}).compress()

		assert isinstance(a, MenuAction)
		assert a.x == -10
		assert a.y == 10

	def test_keyboard(self):
		"""Tests if KeyboardAction is parsed correctly from json."""
		# With text
		a = parser.from_json_data({"action": "keyboard"})
		assert isinstance(a, KeyboardAction)

	def test_gestures(self):
		"""Tests if GesturesAction is parsed correctly from json."""
		# Simple
		a = parser.from_json_data({"gestures": {"UD": {"action": "turnoff"}, "LR": {"action": "keyboard"}}})
		assert isinstance(a, GesturesAction)
		assert isinstance(a.gestures["UD"], TurnOffAction)
		assert isinstance(a.gestures["LR"], KeyboardAction)
		# With OSD
		a = parser.from_json_data(
			{
				"gestures": {
					"UD": {"action": "turnoff"},
				},
				"osd": True,
			},
		)
		assert isinstance(a, OSDAction)
		assert isinstance(a.action, GesturesAction)
		assert isinstance(a.action.gestures["UD"], TurnOffAction)

	def test_cemuhook(self):
		"""Nothing to test here"""
