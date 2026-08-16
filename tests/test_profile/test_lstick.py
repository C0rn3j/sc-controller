import json
from io import StringIO
from pathlib import Path

from scc.constants import LSTICK, SCButtons
from scc.profile import Profile

from . import parser


def test_legacy_left_stick_profile_names_are_migrated() -> None:
	data = json.loads(Path("default_profiles/XBox Controller.sccprofile").read_text())
	data["version"] = 1.5
	data["stick"] = data.pop("lstick")
	data["buttons"]["STICKPRESS"] = data["buttons"].pop("LSTICKPRESS")
	profile = Profile(parser).load_fileobj(StringIO(json.dumps(data)))

	assert profile.lstick
	assert profile.buttons[SCButtons.LSTICKPRESS]


def test_profile_saves_new_left_stick_names() -> None:
	profile = Profile(parser)
	output = StringIO()
	profile.save_fileobj(output)
	data = json.loads(output.getvalue())

	assert data["version"] == 1.6
	assert "lstick" in data
	assert "stick" not in data


def test_legacy_stick_action_constant_aliases_lstick() -> None:
	assert parser.CONSTS["STICK"] == LSTICK
