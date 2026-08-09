import json
from io import StringIO
from pathlib import Path

from scc.actions import NoAction
from scc.constants import SCButtons
from scc.profile import Profile

from . import parser


def test_legacy_right_pad_click_migrates_to_right_stick_click() -> None:
	data = json.loads(Path("default_profiles/XBox Controller.sccprofile").read_text())
	data["version"] = 1.4
	data.pop("rstick")
	data["buttons"].pop("RSTICKPRESS")
	profile = Profile(parser)
	profile.load_fileobj(StringIO(json.dumps(data)))

	assert isinstance(profile.rstick, NoAction)
	assert profile.buttons[SCButtons.RSTICKPRESS].encode() == profile.buttons[SCButtons.RPAD].encode()


def test_right_pad_click_does_not_migrate_in_1_5_profile() -> None:
	data = json.loads(Path("default_profiles/XBox Controller.sccprofile").read_text())
	data["version"] = 1.5
	data["buttons"].pop("RSTICKPRESS")
	profile = Profile(parser)
	profile.load_fileobj(StringIO(json.dumps(data)))

	assert isinstance(profile.buttons[SCButtons.RSTICKPRESS], NoAction)
	assert profile.buttons[SCButtons.RPAD]
