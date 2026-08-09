"""SC-Controller - Controller Registration Constants

Just a huge chunk of constants put aside to make important code more readable
"""

from scc.constants import LEFT, RSTICK, STICK, SCButtons

X = 0
Y = 1

AXIS_ORDER = (
	("stick_x", X),
	("stick_y", Y),
	("rstick_x", X),
	("rstick_y", Y),
	("lpad_x", X),
	("lpad_y", Y),
	("ltrig", X),  # index 6
	("rtrig", X),
)

STICK_PAD_AREAS = {
	# Numbers here are indexes to AXIS_ORDER tuple
	"STICK": (STICK, (0, 1)),
	"RSTICK": (RSTICK, (2, 3)),
	"LPAD": (LEFT, (4, 5)),
}

TRIGGER_AREAS = {
	# Numbers here are indexes to AXIS_ORDER tuple
	"LT": 6,
	"RT": 7,
}

AXIS_TO_BUTTON = {
	# Maps stick and dpad axes to their respective "pressed" button
	"stick_x": SCButtons.STICKPRESS,
	"stick_y": SCButtons.STICKPRESS,
	"rstick_x": SCButtons.RSTICKPRESS,
	"rstick_y": SCButtons.RSTICKPRESS,
	"lpad_x": SCButtons.LPAD,
	"lpad_y": SCButtons.LPAD,
}

SDL_TO_SCC_NAMES = {
	"guide": "C",
	"leftstick": "STICKPRESS",
	"rightstick": "RSTICKPRESS",
	"leftshoulder": "LB",
	"rightshoulder": "RB",
}

SDL_AXES = (
	# This tuple has to use same order as AXIS_ORDER
	"leftx",
	"lefty",
	"rightx",
	"righty",
	"dpadx",
	"dpady",
	"lefttrigger",
	"righttrigger",
)


SDL_DPAD = {
	# Numbers here are indexes to AXIS_ORDER tuple
	# Booleans here are True for positive movements (down/right) and
	# False for negative (up/left)
	"dpdown": (5, True),
	"dpleft": (4, False),
	"dpright": (4, True),
	"dpup": (5, False),
}
