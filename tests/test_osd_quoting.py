"""Exercise OSD quoting at each boundary without starting a daemon."""

import argparse
import json
import runpy
from contextlib import nullcontext
from io import BytesIO, StringIO
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

import scc.actions  # noqa: F401
from scc.constants import SCButtons
from scc.modifiers import NameModifier
from scc.osd.dialog import Dialog
from scc.osd.menu import Menu
from scc.osd.message import Message
from scc.parser import ActionParser, ParseError, TalkingActionParser
from scc.profile import Profile
from scc.sccdaemon import SCCDaemon
from scc.special_actions import (
	ChangeProfileAction,
	DialogAction,
	GesturesAction,
	MenuAction,
	OSDAction,
	ShellCommandAction,
)
from scc.tools import shjoin, shsplit

TEXTS = [
	"Hello world", 'say "hello"', "don't", 'Don\'t lose "these" quotes',
	"", "#tag", "a\tb", r"C:\games\test", "Žluťoučký kůň",
	"ends with a backslash\\", "two single quotes: ''", "line1\nline2",
]


@pytest.fixture(scope="module")
def osd_daemon_class():
	path = Path(__file__).resolve().parents[1] / "scc/x11/scc-osd-daemon.py"
	return runpy.run_path(str(path))["OSDDaemon"]


@pytest.mark.parametrize("text", TEXTS)
def test_helper_roundtrip(text):
	args = ["message", "-t", "5", "-s", "3", text]
	wire = shjoin(args)
	assert isinstance(wire, bytes)
	assert shsplit(wire.decode("utf-8")) == args


@pytest.mark.parametrize("text", TEXTS)
def test_action_roundtrip(text):
	action = ActionParser(OSDAction(text).to_string()).parse()
	assert isinstance(action, OSDAction)
	assert action.text == text


@pytest.mark.parametrize("text", TEXTS)
def test_profile_roundtrip(text):
	profile = Profile(ActionParser())
	profile.buttons[SCButtons.A] = OSDAction(text)
	file = StringIO()
	profile.save_fileobj(file)
	file.seek(0)
	loaded = Profile(ActionParser()).load_fileobj(file)
	assert isinstance(loaded.buttons[SCButtons.A], OSDAction)
	assert loaded.buttons[SCButtons.A].text == text


@pytest.mark.parametrize("text", [text for text in TEXTS if "\n" not in text])
def test_daemon_message_framing(text, osd_daemon_class):
	output = BytesIO()
	daemon = SimpleNamespace(osd_daemon=SimpleNamespace(wfile=output))
	assert SCCDaemon._osd(daemon, "message", text)
	wire = output.getvalue()
	# DaemonManager consumes exactly one physical line per message.
	lines = wire.split(b"\n")
	assert len(lines) == 2 and lines[-1] == b""
	assert shsplit(lines[0].decode())[1:] == ["message", text]
	# Exercise the actual OSD receiver, including its argument decoding.
	message = Mock()
	message_factory = Mock(return_value=message)
	message.parse_arguments.return_value = True
	method = osd_daemon_class.on_unknown_message
	with pytest.MonkeyPatch.context() as patch:
		patch.setitem(method.__globals__, "Message", message_factory)
		receiver = SimpleNamespace(_visible_messages={}, on_message_closed=Mock())
		method(receiver, None, lines[0].decode())
	message.parse_arguments.assert_called_once_with(["message", text])
	message.show.assert_called_once()


@pytest.mark.xfail(strict=True, reason="The line-based OSD protocol cannot carry literal newlines")
def test_multiline_daemon_message_framing(osd_daemon_class):
	test_daemon_message_framing("line1\nline2", osd_daemon_class)


@pytest.mark.parametrize("text", [text for text in TEXTS if "\n" not in text])
def test_menu_selection_roundtrip(text, osd_daemon_class):
	menu = Mock()
	menu.get_exit_code.return_value = 0
	menu.get_menuid.return_value = text
	menu.get_selected_item_id.return_value = text
	osd = SimpleNamespace(daemon=Mock())
	osd_daemon_class.on_menu_closed(osd, menu)
	request = osd.daemon.request.call_args.args[0]
	assert "\n" not in request
	client = Mock()
	client.wfile = BytesIO()
	action = Mock()
	menu_data = Mock()
	menu_data.get_by_id.return_value.action = action
	client.mapper.profile.menus = {text: menu_data}
	SCCDaemon._handle_message(SimpleNamespace(lock=nullcontext()), client, request.encode())
	assert client.wfile.getvalue() == b"OK.\n"
	menu_data.get_by_id.assert_called_once_with(text)
	client.mapper.schedule.assert_called_once()


def test_menu_file_selection_roundtrip(tmp_path, osd_daemon_class):
	path = tmp_path / "Don't lose these menus.menu"
	item_id = 'Don\'t lose "this" item'
	path.write_text(json.dumps([{"id": item_id, "name": "item", "action": "keyboard()"}]))
	menu = Mock()
	menu.get_exit_code.return_value = 0
	menu.get_menuid.return_value = str(path)
	menu.get_selected_item_id.return_value = item_id
	osd = SimpleNamespace(daemon=Mock())
	osd_daemon_class.on_menu_closed(osd, menu)
	request = osd.daemon.request.call_args.args[0]
	client = Mock()
	client.wfile = BytesIO()
	SCCDaemon._handle_message(SimpleNamespace(lock=nullcontext()), client, request.encode())
	assert client.wfile.getvalue() == b"OK.\n"
	client.mapper.schedule.assert_called_once()


@pytest.mark.parametrize("payload", ["", "one", "one two three", "'unclosed"])
def test_invalid_menu_selection_is_rejected(payload):
	client = Mock()
	client.wfile = BytesIO()
	SCCDaemon._handle_message(SimpleNamespace(lock=nullcontext()), client, ("Selected: " + payload).encode())
	assert client.wfile.getvalue().startswith(b"Fail:")
	client.mapper.schedule.assert_not_called()


@pytest.mark.parametrize("literal, expected", [
	(r"'don\'t'", "don't"),
	(r'''"Don't lose \"these\" quotes"''', 'Don\'t lose "these" quotes'),
	(r"'C:\\new\\test\\'", "C:\\new\\test\\"),
	(r"'line1\nline2\tend'", "line1\nline2\tend"),
	(r"'\u017dlu\u0165ou\u010dk\u00fd'", "Žluťoučký"),
	(r"r'C:\new\test'", r"C:\new\test"),
	("'''both ' and \" quotes'''", "both ' and \" quotes"),
])
def test_string_literals_decode_escapes(literal, expected):
	assert ActionParser(f"osd({literal})").parse().text == expected


@pytest.mark.parametrize("literal", [r"'\xZZ'", "b'bytes'", "f'interpolated'"])
def test_invalid_text_literals_raise_parse_error(literal):
	with pytest.raises(ParseError):
		ActionParser(f"osd({literal})").parse()


@pytest.mark.parametrize("text", TEXTS)
def test_other_string_actions_roundtrip(text):
	for action, attribute in (
		(ChangeProfileAction(text), "profile"), (ShellCommandAction(text), "command"),
		(MenuAction(text), "menu_id"), (MenuAction(text, 2), "menu_id"),
		(DialogAction(text, OSDAction("option")), "text"),
		(NameModifier(text, OSDAction("message")), "name"),
	):
		encoded = action.to_string()
		parsed = ActionParser(encoded).parse()
		assert parsed.to_string() == encoded
		assert getattr(parsed, attribute) == text


def test_talking_parser_accepts_apostrophes_without_warning(capsys):
	action = TalkingActionParser(OSDAction("don't").to_string()).parse()
	assert action.text == "don't"
	assert not capsys.readouterr().err


@pytest.mark.parametrize("text", TEXTS)
def test_serialization_is_stable(text):
	action = OSDAction(2.5, 1, text)
	for _ in range(3):
		action = ActionParser(action.to_string()).parse()
		assert action.text == text
		assert action.timeout == 2.5
		assert action.size == 1


@pytest.mark.parametrize("text", ["--help", "-s3", "--", "-x100", "", 'Don\'t lose "these" quotes'])
@pytest.mark.parametrize("source", ["action", "client"])
def test_message_text_is_not_parsed_as_options(text, source):
	output = BytesIO()
	daemon = SimpleNamespace(lock=nullcontext(), osd_daemon=SimpleNamespace(wfile=output))
	daemon._osd = MethodType(SCCDaemon._osd, daemon)
	if source == "action":
		SCCDaemon.on_sa_osd(daemon, None, OSDAction(text))
	else:
		client = SimpleNamespace(wfile=BytesIO())
		SCCDaemon._handle_message(daemon, client, ("OSD: " + text).encode())
		assert client.wfile.getvalue() == b"OK.\n"
	args = shsplit(output.getvalue().decode())[1:]
	message = SimpleNamespace(argparser=argparse.ArgumentParser())
	Message._add_arguments(message)
	assert Message.parse_arguments(message, args)
	assert message.text == text
	assert message.size == OSDAction.DEFAULT_SIZE


@pytest.mark.parametrize("text", ["--help", "-s3", "--", "-x100", "", 'Don\'t lose "these" quotes'])
def test_dialog_title_and_button_label_are_not_parsed_as_options(text):
	option = NameModifier(text, OSDAction("option"))
	action = DialogAction(text, option)
	mapper = Mock()
	output = BytesIO()
	daemon = SimpleNamespace(lock=nullcontext(), osd_daemon=SimpleNamespace(wfile=output))
	daemon._osd = MethodType(SCCDaemon._osd, daemon)
	daemon.on_sa_dialog = MethodType(SCCDaemon.on_sa_dialog, daemon)
	mapper.get_special_actions_handler.return_value = daemon
	action.button_release(mapper)
	args = shsplit(output.getvalue().decode())[2:]
	dialog = SimpleNamespace(argparser=argparse.ArgumentParser())
	Dialog._add_arguments(dialog)
	parsed = dialog.argparser.parse_args(args)
	assert parsed.text == text
	assert parsed.items == [str(hash(option)), option.describe(scc.actions.Action.AC_MENU)]
	assert parsed.x == action.x
	assert parsed.y == action.y


@pytest.mark.parametrize("menu_id", ["--help", "--", "-menu", 'Don\'t lose "this" menu'])
def test_menu_id_is_not_parsed_as_options(menu_id):
	action = MenuAction(menu_id)
	mapper = Mock()
	mapper.get_controller.return_value = None
	mapper.profile.get_filename.return_value = "/tmp/profile.sccprofile"
	output = BytesIO()
	daemon = SimpleNamespace(lock=nullcontext(), osd_daemon=SimpleNamespace(wfile=output))
	daemon._osd = MethodType(SCCDaemon._osd, daemon)
	SCCDaemon.on_sa_menu(daemon, mapper, action, "--size", "2", "-x", "10")
	args = shsplit(output.getvalue().decode())[2:]
	menu = SimpleNamespace(argparser=argparse.ArgumentParser())
	Menu._add_arguments(menu)
	parsed = menu.argparser.parse_args(args)
	assert parsed.items == [menu_id]
	assert parsed.from_profile == "/tmp/profile.sccprofile"
	assert parsed.size == 2
	assert parsed.x == 10


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("multiline", [False, True])
def test_gesture_strings_roundtrip(text, multiline):
	action = GesturesAction(text, OSDAction("gesture"))
	parsed = ActionParser(action.to_string(multiline)).parse()
	assert list(parsed.gestures) == [text]
	assert parsed.gestures[text].text == "gesture"
