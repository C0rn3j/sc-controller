"""Various constants.

If SC Controller is updated while daemon is running, DAEMON_VERSION sent by
daemon will differ from the one expected by the UI, and daemon will be forcefully restarted.
"""
# The MIT License (MIT)
#
# Copyright (c) 2015 Stany MARCEL <stanypub@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from enum import IntEnum, StrEnum
from importlib.metadata import packages_distributions, version

distribution_name: str = "N/A"
if __package__ is not None:
	distribution_name = packages_distributions()[__package__][0]

class SCLeftRight(StrEnum):
	"""Simply LEFT or RIGHT

	"LEFT" can mean LPAD or LT, depending on context
	"RIGHT" can mean RPAD or RT, depending on context
	"""

	LEFT = "LEFT"
	RIGHT = "RIGHT"

#class SCTriggers(StrEnum):
#	"""This implementation sure triggers."""  # noqa: D404
#
#	LEFT = "LEFT"
#	RIGHT = "RIGHT"


class SCPads(StrEnum):
	"""Touchpads and DPAD"""

	# TODO(Martin): Change this to LPAD and RPAD to maintain sanity
	LEFT = "LEFT"
	RIGHT = "RIGHT"
	CPAD = "CPAD"
	DPAD = "DPAD"

class SCSticks(StrEnum):
	"""Joysticks"""

	LSTICK = "LSTICK"
	RSTICK = "RSTICK"


class SCButtons(IntEnum):
	LSTICKTOUCH = 1 << 16 # capacitive left-stick touch - Steam Controller (2026) & Deck
	RSTICKTOUCH = 1 << 17 # capacitive right-stick touch - Steam Controller (2026) & Deck
	LGRIPTOUCH  = 1 << 18 # capacitive left handle grip - Steam Controller (2026)
	RGRIPTOUCH  = 1 << 19 # capacitive right handle grip - Steam Controller (2026)
	RPADTOUCH   = 0b000010000000000000000000000000000
	LPADTOUCH   = 0b000001000000000000000000000000000
	RPAD        = 0b000000100000000000000000000000000
	LPAD        = 0b000000010000000000000000000000000 # Same for stick but without LPadTouch
	RGRIP       = 0b000000001000000000000000000000000
	LGRIP       = 0b000000000100000000000000000000000
	START       = 0b000000000010000000000000000000000
	C           = 0b000000000001000000000000000000000
	BACK        = 0b000000000000100000000000000000000
	A           = 0b000000000000000001000000000000000
	X           = 0b000000000000000000100000000000000
	B           = 0b000000000000000000010000000000000
	Y           = 0b000000000000000000001000000000000
	LB          = 0b000000000000000000000100000000000
	RB          = 0b000000000000000000000010000000000
	LT          = 0b000000000000000000000001000000000
	RT          = 0b000000000000000000000000100000000
	CPADTOUCH   = 0b000000000000000000000000000000100 # Available on DS4 & DualSeanse & DualSense Edge
	CPADPRESS   = 0b000000000000000000000000000000010 # Available on DS4 & DualSeanse & DualSense Edge
	LSTICKPRESS = 0b001000000000000000000000000000000
	RSTICKPRESS = 0b010000000000000000000000000000000
	DOTS        = 0b000000000000000000000000000001000 # Steam Controller (2026) & Deck
	RGRIP2      = 0b000000000000000000000000000100000 # Steam Controller (2026) & Deck
	LGRIP2      = 0b000000000000000000000000000010000 # Steam Controller (2026) & Deck


class HapticPos(IntEnum):
	"""Specify which touchpad or trigger is used."""

	RIGHT = 0
	LEFT  = 1
	BOTH  = 2 # emulated


class HapticEffect(IntEnum):
	"""Which kind of haptic effect a HapticData describes.

	CLICK is the only one every controller can do, and the only one a v1
	understands at all; the rest need hardware with a synthesising actuator
	(currently just the Steam Controller 2, output reports 0x83-0x85). A
	driver that does not know an effect should fall back to CLICK rather than
	going silent.
	"""

	CLICK  = 0  # a single tick -- what feedback() has always meant
	TONE   = 1  # sine at a fixed frequency, optionally LFO-modulated
	SWEEP  = 2  # logarithmic frequency sweep between two frequencies
	SCRIPT = 3  # a preset effect stored in the controller firmware


class ControllerFlags(IntEnum):
	"""Used by mapper to workaround some physical differences between Steam Controller and other pads."""

	NONE           =      0 # No flags, default SC.
	HAS_RSTICK     = 1 << 0 # Controller has right stick instead of touchpad
	SEPARATE_LSTICK = 1 << 1 # Left stick and left pad are using separate axes
	EUREL_GYROS    = 1 << 2 # Gyro sensor values are provided as pitch, yaw
	                                    # and roll instead of quaterion. 'q4' is unused
	                                    # in such case.
	HAS_CPAD       = 1 << 3 # Controller has DS4-like touchpad in the center
	# TODO(Martin): Historically this assumed that it has dpad INSTEAD of touchpad - check if we have a problem with that
	HAS_DPAD       = 1 << 4 # Controller has d-pad
	NO_GRIPS       = 1 << 5 # Controller has no grips
	IS_DECK        = 1 << 6 # Very special case

DAEMON_VERSION = version(distribution_name)

HPERIOD  = 0.02
LPERIOD  = 0.5
DURATION = 1.0

# Constants used when forcing gamepad to read some type of event is needed
FE_STICK   = 1
FE_TRIGGER = 2
FE_PAD     = 3
FE_GYRO    = 4

# Trigger names, pads, etc. These constants are used in multiple places
LEFT   = "LEFT"  # DEPRECATED
RIGHT  = "RIGHT" # DEPRECATED
CPAD   = SCPads.CPAD   # DEPRECATED
DPAD   = SCPads.DPAD   # DEPRECATED
LSTICK = SCSticks.LSTICK # DEPRECATED
RSTICK = SCSticks.RSTICK # DEPRECATED
WHOLE  = "WHOLE"
GYRO   = "GYRO"
PITCH  = "PITCH"
YAW    = "YAW"
ROLL   = "ROLL"

# Special constants currently used only by menus
SAME    = "SAME"    # Menu is canceled by releasing same button that intiated it
DEFAULT = "DEFAULT" # Default confirm/cancel button. A/B for menus initiated by
                    # button, pad clicking / releasing for menus on pads

# Deadzone modes
CUT     = "CUT"
ROUND   = "ROUND"
LINEAR  = "LINEAR"
MINIMUM = "MINIMUM"

# Hipfire modes
HIPFIRE_NORMAL    = "NORMAL"
HIPFIRE_SENSIBLE  = "SENSIBLE"
HIPFIRE_EXCLUSIVE = "EXCLUSIVE"

PARSER_CONSTANTS = (
	LEFT, RIGHT, WHOLE, LSTICK, RSTICK, GYRO, PITCH,
	YAW, ROLL, DEFAULT, SAME, CUT, ROUND, LINEAR, MINIMUM,
	HIPFIRE_NORMAL, HIPFIRE_SENSIBLE, HIPFIRE_EXCLUSIVE,
)

# Steam Controller (2015) specific
# If lpad and lstick is used at once, this is sent as
# a button with every other packet to signalize that
# the values of lpad_x and lpad_y belong to lstick
LSTICKTILT = 0b10000000000000000000000000000000

STICK_PAD_MIN      = -32768
STICK_PAD_MAX      = 32767
STICK_PAD_MIN_HALF = STICK_PAD_MIN / 3
STICK_PAD_MAX_HALF = STICK_PAD_MAX / 3
STICK_PAD_RES      = STICK_PAD_MAX - (STICK_PAD_MIN)

# Take async 360 stick axes into account
OUTPUT_360_STICK_MAX = 32767
OUTPUT_360_STICK_MIN = -32768
OUTPUT_360_STICK_RES = OUTPUT_360_STICK_MAX - (OUTPUT_360_STICK_MIN)

CPAD_MIN   = 0
CPAD_X_MAX = 1916
CPAD_Y_MAX = 930

TRIGGER_MIN            = 0
TRIGGER_HALF           = 50
TRIGGER_CLICK          = 254 # Values under this are generated until trigger clicks
TRIGGER_MAX            = 255
BASE_STICK_MOUSE_SPEED = 1000 # Pixels per second
