from io import BytesIO
from unittest.mock import Mock

from scc.constants import HapticPos
from scc.sccdaemon import SCCDaemon


def make_client():
	controller = Mock()
	client = Mock()
	client.mapper.get_controller.return_value = controller
	client.wfile = BytesIO()
	return client, controller


def test_feedback_command_sends_haptic_data() -> None:
	client, controller = make_client()

	SCCDaemon._handle_message(Mock(), client, b"Feedback: BOTH 32768")

	data = controller.feedback.call_args.args[0]
	assert data.data == (HapticPos.BOTH, 32768, 1024, 1)
	assert client.wfile.getvalue() == b"OK.\n"


def test_invalid_feedback_command_returns_failure() -> None:
	client, controller = make_client()

	SCCDaemon._handle_message(Mock(), client, b"Feedback: INVALID nope")

	controller.feedback.assert_not_called()
	assert client.wfile.getvalue().startswith(b"Fail: ")
