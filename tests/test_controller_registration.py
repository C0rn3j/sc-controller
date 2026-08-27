from scc.gui.creg.dialog import parse_sdl_dpad_axis


def test_parse_sdl_dpad_half_axes() -> None:
	axes = [16, 17]

	assert parse_sdl_dpad_axis("dpup", "-a1", axes) == (17, 5, True)
	assert parse_sdl_dpad_axis("dpdown", "+a1", axes) == (17, 5, True)
	assert parse_sdl_dpad_axis("dpleft", "-a0", axes) == (16, 4, False)
	assert parse_sdl_dpad_axis("dpright", "+a0", axes) == (16, 4, False)


def test_parse_sdl_dpad_half_axis_honors_reversed_axis() -> None:
	assert parse_sdl_dpad_axis("dpup", "+a1", [16, 17]) == (17, 5, False)
	assert parse_sdl_dpad_axis("dpleft", "+a0", [16, 17]) == (16, 4, True)


def test_parse_sdl_dpad_half_axis_rejects_missing_axis() -> None:
	assert parse_sdl_dpad_axis("dpup", "-a2", [16, 17]) is None
