import json
from io import StringIO
from pathlib import Path

from scc.constants import RIGHT, SCButtons
from scc.profile import Profile

from . import parser


def test_legacy_right_pad_bindings_migrate_to_right_stick() -> None:
	data = json.loads(Path("default_profiles/XBox Controller.sccprofile").read_text())
	data.pop("rstick")
	data["buttons"].pop("RSTICKPRESS")
	profile = Profile(parser)
	profile.load_fileobj(StringIO(json.dumps(data)))

	assert profile.rstick.encode() == profile.pads[RIGHT].encode()
	assert profile.buttons[SCButtons.RSTICKPRESS].encode() == profile.buttons[SCButtons.RPAD].encode()
