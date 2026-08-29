from scc.gui.creg.dialog import order_evdev_buttons_for_sdl, parse_sdl_dpad_axis


def test_order_evdev_buttons_for_sdl_puts_gamepad_buttons_before_extra_keys() -> None:
	# Xbox One S exposes its Share button as KEY_RECORD. Numeric evdev ordering
	# puts it before BTN_SOUTH, while SDL appends it after the gamepad buttons.
	buttons = [167, 304, 305, 307, 308, 310, 311, 314, 315, 316, 317, 318]

	assert order_evdev_buttons_for_sdl(buttons) == [304, 305, 307, 308, 310, 311, 314, 315, 316, 317, 318, 167]


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
