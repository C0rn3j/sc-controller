"""Steam Controller (2026) protocol helpers for the HIDAPI backend.

Copied from the original Linux driver, which is deliberately kept unchanged as a huge PR is filed against it.
This module avoids Linux transport imports on Windows and macOS.
"""

from __future__ import annotations

import logging
import math
import os
import struct
import time
from enum import IntEnum
from typing import NamedTuple

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, SCButtons

log = logging.getLogger("SC2")
_CALIB = bool(os.environ.get("SCC_GYRO_CALIB"))
if _CALIB:
	# The daemon leaves the root logger at WARNING; opt this logger into INFO so
	# the IMU-calibration dump (_log_imu_calib) is actually visible.
	log.setLevel(logging.INFO)


_calib_last_t = 0.0


def _log_imu_calib(idata) -> None:
	"""Throttled IMU dump for SC2 gyro calibration (gate: env SCC_GYRO_CALIB=1).
	Logs the parsed IMU state: accel gravity vector, the (sign-mapped) angular
	rates, and the euler angles derived from the firmware quaternion -- held
	orientations verify the axis/sign mapping end to end."""

	global _calib_last_t
	now = time.time()
	if now - _calib_last_t < 0.25:
		return
	_calib_last_t = now
	ax, ay, az = idata.accel_x, idata.accel_y, idata.accel_z
	mag = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
	k = 180.0 / 32768.0  # EUREL fixed point -> degrees
	log.info(
		"IMU-CALIB  accel unit=(% .2f % .2f % .2f) |a|=%6.0f  |  rates=(% 6d % 6d % 6d)  |  euler deg  pitch=% 6.1f yaw=% 6.1f roll=% 6.1f",
		ax / mag,
		ay / mag,
		az / mag,
		mag,
		idata.gpitch,
		idata.groll,
		idata.gyaw,
		idata.q1 * k,
		idata.q2 * k,
		idata.q3 * k,
	)


VENDOR_ID = 0x28DE
PID_PUCK = 0x1304  # wireless Controller Puck (dongle)
PID_WIRED = 0x1302  # controller over USB-C cable
PID_BT = 0x1303  # controller over Bluetooth LE          - TODO

# The puck exposes 4 controller slots as HID interfaces 2..5, each with an
# interrupt-IN endpoint numbered one higher (3..6).
FIRST_INTERFACE = 2
FIRST_IN_ENDPOINT = 3
MAX_SLOTS = 4

# wired controller (0x1302): a single HID interface 0, interrupt IN ep 0x81 /
# OUT ep 0x01. Same 0x42 report as the puck, so all parsing/commands reuse.
WIRED_INTERFACE = 0
WIRED_IN_ENDPOINT = 1
WIRED_OUT_ENDPOINT = 1

# report 0x42 is 54 bytes including the report-ID byte; the endpoint also
# carries shorter reports (0x43/0x44/0x7b/...), so we request the full max
# packet (64) and accept any length, filtering by report ID in parse_input.
INPUT_REPORT_ID = 0x42
INPUT_SIZE = 54
INPUT_BUFFER = 64

# sticks sit off-center and jitter at rest (same reason the Deck uses a
# deadzone); value is a placeholder pending in-headset/desktop tuning.  TODO
STICK_DEADZONE = 3000

# resend CLEAR_MAPPINGS every N frames so the controller never falls back to
# lizard (mouse/keyboard) mode, exactly as steamdeck.py does.
UNLIZARD_INTERVAL = 100

# Simulated pad click. The v2's touchpads have no dome switch under them -- the
# click is purely haptic, the way Steam does it -- so pressing one feels like
# nothing at all unless the driver produces the pulse itself. Every other haptic
# in sc-controller comes from a feedback() modifier the user attaches to an
# action, and there is no binding for "the pad was pressed" (nor any GUI control
# for one), so this cannot be expressed as a profile and has to be built in.
# Emitted on press and, more softly, on release, because that is what a real
# dome switch does: it clicks going down and again springing back.
PAD_CLICK_PRESS = 0x6000
PAD_CLICK_RELEASE = 0x3000

TURNOFF_QUIET_PERIOD = 0.5


# --- report 0x42 layout (see docs/steam-controller-v2-protocol.md) ----------
#  0      report id (0x42)
#  1      packet counter
#  2..5   four button bytes (bitfield below)
#  6..7   left trigger  (u16, ~0..32767)
#  8..9   right trigger (u16)
# 10..17  left stick X/Y, right stick X/Y (i16 each)
# 18..23  left pad  X(i16) Y(i16) pressure(u16)
# 24..29  right pad X(i16) Y(i16) pressure(u16)
# 30..33  IMU timestamp/counter (skipped)
# 34..39  accel X/Y/Z (i16)         } only populated when the gyro is enabled
# 40..45  gyro angular rates x/y/z  } via configure(); zero/constant otherwise
# 46..53  orientation quaternion, w@46 x@48 y@50 z@52 (norm 32768)
#
# The quaternion/rates split was pinned down from held-pose captures: the four
# i16 at 46/48/50/52 have norm exactly 32768 in every orientation (a unit
# quaternion), while 40..45 read ~0 whenever the controller is still (rates).
# IMU axes (right-handed, Z up): x = pitch (nose-up +), y = roll (roll-right
# +), z = yaw (yaw-left +); accel reads +Z flat, -Y nose-down, -X roll-right.
_INPUT_FORMAT = "<BBBBBBHHhhhhhhHhhH4xhhhhhhhhhh"
assert struct.calcsize(_INPUT_FORMAT) == INPUT_SIZE

_EUREL_SCALE = 32768.0 / math.pi  # radians -> the 2**15/PI fixed point EUREL_GYROS wants


class SC2Button(IntEnum):
	"""Raw button bits as a 32-bit value: byte off2 = bits 0..7, off3 = 8..15,
	off4 = 16..23, off5 = 24..31.  Verified by per-control capture.
	"""

	# off2
	A = 1 << 0
	B = 1 << 1
	X = 1 << 2
	Y = 1 << 3
	QUICKACCESS = 1 << 4  # the "..." button
	RSTICKPRESS = 1 << 5  # R3
	MENU = 1 << 6  # hamburger
	R4 = 1 << 7
	# off3
	R5 = 1 << 8
	RB = 1 << 9  # right bumper (R1)
	DPAD_DOWN = 1 << 10
	DPAD_RIGHT = 1 << 11
	DPAD_LEFT = 1 << 12
	DPAD_UP = 1 << 13
	VIEW = 1 << 14  # View button (overlapping rectangles, top-left)
	LSTICKPRESS = 1 << 15  # L3
	# off4
	STEAM = 1 << 16
	L4 = 1 << 17
	L5 = 1 << 18
	LB = 1 << 19  # left bumper (L1)
	RSTICKTOUCH = 1 << 20  # capacitive right-stick touch
	RPADTOUCH = 1 << 21
	RPADPRESS = 1 << 22
	RT_FULL = 1 << 23  # right trigger digital full-pull
	# off5
	LSTICKTOUCH = 1 << 24  # capacitive left-stick touch
	LPADTOUCH = 1 << 25
	LPADPRESS = 1 << 26
	LT_FULL = 1 << 27  # left trigger digital full-pull
	RGRIP_TOUCH = 1 << 28  # capacitive right handle (reads on against table)
	LGRIP_TOUCH = 1 << 29  # capacitive left handle
	UNKNOWN_5_6 = 1 << 30  # TODO: unmapped
	UNKNOWN_5_7 = 1 << 31  # TODO: unmapped


# raw SC2 bit -> SCButtons. Capacitive stick touch -> (L/R)STICKTOUCH and the
# capacitive handle grips -> (L/R)GRIPTOUCH (the latter are Steam-Controller-only
# and read "on" while the handles are held); only the unknown bits are unmapped.
# L4/R4/L5/R5 follow the Deck convention: upper paddles -> (L/R)GRIP, lower ->
# (L/R)GRIP2.
_BUTTON_MAP = (
	(SC2Button.A, SCButtons.A),
	(SC2Button.B, SCButtons.B),
	(SC2Button.X, SCButtons.X),
	(SC2Button.Y, SCButtons.Y),
	(SC2Button.RB, SCButtons.RB),
	(SC2Button.LB, SCButtons.LB),
	(SC2Button.RT_FULL, SCButtons.RT),
	(SC2Button.LT_FULL, SCButtons.LT),
	(SC2Button.LSTICKPRESS, SCButtons.LSTICKPRESS),
	(SC2Button.RSTICKPRESS, SCButtons.RSTICKPRESS),
	(SC2Button.LPADTOUCH, SCButtons.LPADTOUCH),
	(SC2Button.RPADTOUCH, SCButtons.RPADTOUCH),
	(SC2Button.LSTICKTOUCH, SCButtons.LSTICKTOUCH),
	(SC2Button.RSTICKTOUCH, SCButtons.RSTICKTOUCH),
	(SC2Button.LGRIP_TOUCH, SCButtons.LGRIPTOUCH),
	(SC2Button.RGRIP_TOUCH, SCButtons.RGRIPTOUCH),
	(SC2Button.LPADPRESS, SCButtons.LPAD),
	(SC2Button.RPADPRESS, SCButtons.RPAD),
	(SC2Button.L4, SCButtons.LGRIP),
	(SC2Button.R4, SCButtons.RGRIP),
	(SC2Button.L5, SCButtons.LGRIP2),
	(SC2Button.R5, SCButtons.RGRIP2),
	(SC2Button.STEAM, SCButtons.C),  # Steam / home button
	(SC2Button.MENU, SCButtons.START),  # hamburger (☰), top-right
	(SC2Button.VIEW, SCButtons.BACK),  # view / select (⧉), top-left
	(SC2Button.QUICKACCESS, SCButtons.DOTS),  # "..." quick access, bottom-center
)

# field set mirrors steamdeck.DeckInput so the mapper sees familiar attributes
class SC2Input(NamedTuple):
	"""TODO(Martin): types weren't verified but guessed, fix later"""

	buttons: int
	ltrig: float
	rtrig: float
	lstick_x: int
	lstick_y: int
	rstick_x: int
	rstick_y: int
	lpad_x: float
	lpad_y: float
	rpad_x: float
	rpad_y: float
	lpad_pressure: float
	rpad_pressure: float
	accel_x: float
	accel_y: float
	accel_z: float
	gpitch: float
	groll: float
	gyaw: float
	q1: float
	q2: float
	q3: float
	q4: float
	dpad_x: int
	dpad_y: int
	seq: int

SC2_NULL = SC2Input(*([0] * len(SC2Input._fields)))


def _deadzone(v: int) -> int:
	return 0 if -STICK_DEADZONE < v < STICK_DEADZONE else v


def parse_input(data: bytes | bytearray) -> SC2Input | None:
	"""Parse a raw report 0x42 into an SC2Input. Returns None for other reports."""
	if not data or data[0] != INPUT_REPORT_ID or len(data) < INPUT_SIZE:
		return None
	(
		_rid,
		seq,
		b2,
		b3,
		b4,
		b5,
		ltrig,
		rtrig,
		lsx,
		lsy,
		rsx,
		rsy,
		lpx,
		lpy,
		lpz,
		rpx,
		rpy,
		rpz,
		ax,
		ay,
		az,
		rx,
		ry,
		rz,
		qw,
		qx,
		qy,
		qz,
	) = struct.unpack(_INPUT_FORMAT, bytes(data[:INPUT_SIZE]))
	raw = b2 | (b3 << 8) | (b4 << 16) | (b5 << 24)

	buttons = 0
	for from_, to in _BUTTON_MAP:
		if raw & from_:
			buttons |= to

	dpad_x = STICK_PAD_MAX if raw & SC2Button.DPAD_RIGHT else STICK_PAD_MIN if raw & SC2Button.DPAD_LEFT else 0
	dpad_y = STICK_PAD_MAX if raw & SC2Button.DPAD_UP else STICK_PAD_MIN if raw & SC2Button.DPAD_DOWN else 0

	# quaternion (w@46, x@48, y@50, z@52) -> euler about the IMU's own axes:
	# about-x = physical pitch (nose-up +), about-y = roll (roll-right +),
	# about-z = yaw (yaw-left +). Identity (all zero, gyro disabled) gives 0s.
	w, x, y, z = qw / 32768.0, qx / 32768.0, qy / 32768.0, qz / 32768.0
	_qe_pitch = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
	_qe_roll = math.asin(min(1.0, max(-1.0, 2.0 * (w * y - z * x))))
	_qe_yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

	return SC2Input(
		buttons=buttons,
		# triggers are ~15-bit; scale to the 0..255 the mapper expects (cf. Deck >>7)
		ltrig=ltrig >> 7,
		rtrig=rtrig >> 7,
		lstick_x=_deadzone(lsx),
		lstick_y=_deadzone(lsy),
		rstick_x=_deadzone(rsx),
		rstick_y=_deadzone(rsy),
		lpad_x=lpx,
		lpad_y=lpy,
		rpad_x=rpx,
		rpad_y=rpy,
		lpad_pressure=lpz,
		rpad_pressure=rpz,
		# IMU: nonzero only when the gyro is enabled (configure() sends that).
		# The firmware-fused quaternion is converted to euler HOST-side and the
		# mapper gets DS4-convention EUREL angles in q1-q3 (SC2Controller sets
		# EUREL_GYROS): ANGLES are + at nose-down / yaw-right / roll-right, and
		# RATES are + in the opposite direction of each angle (nose-up /
		# yaw-left / roll-left) -- that per-axis opposition is inherited from
		# the DS4, whose relative path negates raw rates while its fused angles
		# follow the calibrated directions. All hw-verified on both pads. This
		# makes every gyro path (absolute, tilt, lean-to-turn, laser mouse)
		# behave identically to the DS4.
		accel_x=ax,
		accel_y=ay,
		accel_z=az,
		gpitch=rx,
		groll=-ry,
		gyaw=rz,
		q1=int(-_qe_pitch * _EUREL_SCALE),
		q2=int(-_qe_yaw * _EUREL_SCALE),
		q3=int(_qe_roll * _EUREL_SCALE),
		q4=0,
		dpad_x=dpad_x,
		dpad_y=dpad_y,
		seq=seq,
	)
	# TODO: verify pad/stick Y polarity (may need inversion) once tested live.
