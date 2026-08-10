"""Unit tests for the new Steam Controller (2026) report-0x42 parser.

Frames are synthesized from docs/steam-controller-v2-protocol.md; no hardware
or captured data is required. These lock the reverse-engineered byte/bit layout.
"""

import struct

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, HapticPos, SCButtons
from scc.drivers.sc2 import PAD_CLICK_PRESS, PAD_CLICK_RELEASE, SC2Controller, TURNOFF_QUIET_PERIOD, SC2Controller, SC2Device, SCPacketType, parse_input


def _frame(
	bytes_: dict[int, int] | None = None, i16: dict[int, int] | None = None, u16: dict[int, int] | None = None
) -> bytes:
	"""Build a 54-byte report 0x42 with the given fields set."""
	f = bytearray(54)
	f[0] = 0x42
	for off, val in (bytes_ or {}).items():
		f[off] = val
	for off, val in (i16 or {}).items():
		struct.pack_into("<h", f, off, val)
	for off, val in (u16 or {}).items():
		struct.pack_into("<H", f, off, val)
	return bytes(f)


def test_rejects_other_reports() -> None:
	assert parse_input(b"\x40" + b"\x00" * 53) is None  # mouse report
	assert parse_input(b"") is None
	assert parse_input(b"\x42\x00") is None  # too short


def test_face_buttons() -> None:
	assert parse_input(_frame({2: 0x01})).buttons & SCButtons.A
	assert parse_input(_frame({2: 0x02})).buttons & SCButtons.B
	assert parse_input(_frame({2: 0x04})).buttons & SCButtons.X
	assert parse_input(_frame({2: 0x08})).buttons & SCButtons.Y
	assert not parse_input(_frame({2: 0x01})).buttons & SCButtons.B


def test_bumpers() -> None:
	assert parse_input(_frame({4: 0x08})).buttons & SCButtons.LB  # L1
	assert parse_input(_frame({3: 0x02})).buttons & SCButtons.RB  # R1


def test_grips_and_paddles() -> None:
	assert parse_input(_frame({4: 0x02})).buttons & SCButtons.LGRIP  # L4
	assert parse_input(_frame({2: 0x80})).buttons & SCButtons.RGRIP  # R4
	assert parse_input(_frame({4: 0x04})).buttons & SCButtons.LGRIP2  # L5
	assert parse_input(_frame({3: 0x01})).buttons & SCButtons.RGRIP2  # R5


def test_system_buttons() -> None:
	assert parse_input(_frame({4: 0x01})).buttons & SCButtons.C  # Steam
	assert parse_input(_frame({2: 0x40})).buttons & SCButtons.START  # Menu (☰)
	assert parse_input(_frame({3: 0x40})).buttons & SCButtons.BACK  # View (⧉)
	assert parse_input(_frame({2: 0x10})).buttons & SCButtons.DOTS  # QuickAccess (…)


def test_stick_clicks() -> None:
	assert parse_input(_frame({3: 0x80})).buttons & SCButtons.LSTICKPRESS
	assert parse_input(_frame({2: 0x20})).buttons & SCButtons.RSTICKPRESS


def test_stick_touch() -> None:
	assert parse_input(_frame({5: 0x01})).buttons & SCButtons.LSTICKTOUCH
	assert parse_input(_frame({4: 0x10})).buttons & SCButtons.RSTICKTOUCH


def test_grip_sensing() -> None:
	assert parse_input(_frame({5: 0x20})).buttons & SCButtons.LGRIPTOUCH
	assert parse_input(_frame({5: 0x10})).buttons & SCButtons.RGRIPTOUCH


def test_triggers() -> None:
	assert parse_input(_frame(u16={6: 0x7F80})).ltrig == 255  # analog -> 0..255
	assert parse_input(_frame(u16={8: 0x7000})).rtrig == (0x7000 >> 7)
	assert parse_input(_frame({5: 0x08})).buttons & SCButtons.LT  # digital full-pull
	assert parse_input(_frame({4: 0x80})).buttons & SCButtons.RT


def test_sticks_and_deadzone() -> None:
	assert parse_input(_frame(i16={10: 30000})).lstick_x == 30000
	assert parse_input(_frame(i16={12: -30000})).lstick_y == -30000
	assert parse_input(_frame(i16={14: 20000})).rstick_x == 20000
	assert parse_input(_frame(i16={16: -25000})).rstick_y == -25000
	assert parse_input(_frame(i16={10: 100})).lstick_x == 0  # within deadzone


def test_pads() -> None:
	inp = parse_input(_frame(i16={18: 12345, 20: -6789}, u16={22: 400}))
	assert (inp.lpad_x, inp.lpad_y, inp.lpad_pressure) == (12345, -6789, 400)
	inp = parse_input(_frame(i16={24: -11111, 26: 22222}, u16={28: 650}))
	assert (inp.rpad_x, inp.rpad_y, inp.rpad_pressure) == (-11111, 22222, 650)


def test_dpad() -> None:
	assert parse_input(_frame({3: 0x20})).dpad_y == STICK_PAD_MAX  # up
	assert parse_input(_frame({3: 0x04})).dpad_y == STICK_PAD_MIN  # down
	assert parse_input(_frame({3: 0x08})).dpad_x == STICK_PAD_MAX  # right
	assert parse_input(_frame({3: 0x10})).dpad_x == STICK_PAD_MIN  # left


def test_imu() -> None:
	# IMU lands at offsets 34..53 (only nonzero when the gyro is enabled).
	# Rates live at 40..45 (x/y/z); signs map to the DS4 conventions
	# (rate + at nose-up / yaw-left / roll-left; hw-verified).
	assert parse_input(_frame(i16={40: 5000})).gpitch == 5000
	assert parse_input(_frame(i16={42: -6000})).groll == 6000  # roll negated
	assert parse_input(_frame(i16={44: 7000})).gyaw == 7000
	assert parse_input(_frame(i16={38: 16000})).accel_z == 16000
	# The firmware quaternion (w@46 x@48 y@50 z@52, norm 32768) becomes euler
	# in q1-q3, EUREL fixed point (2**15/PI per radian), DS4 conventions
	# (pitch nose-down +, yaw yaw-left +, roll roll-right +). Ground truth: a
	# real held-pose capture, controller pitched nose-down past vertical.
	nose_down = parse_input(_frame(i16={46: 18232, 48: -26975, 50: -2361, 52: 2831}))
	assert 100.0 < nose_down.q1 * 180.0 / 32768.0 < 125.0  # ~ +111 deg nose-down
	assert abs(nose_down.q3 * 180.0 / 32768.0) < 15.0  # roll ~ level
	assert nose_down.q4 == 0  # unused in EUREL mode
	# a real roll-right capture -> positive q3, pitch near level
	roll_right = parse_input(_frame(i16={46: 23715, 48: -2921, 50: 21679, 52: 5719}))
	assert 70.0 < roll_right.q3 * 180.0 / 32768.0 < 95.0  # ~ +81 deg roll-right
	# a real yaw-left capture -> negative q2 (yaw angle is + at yaw-RIGHT)
	yaw_left = parse_input(_frame(i16={46: 20168, 48: -1919, 50: -1725, 52: 25695}))
	assert -115.0 < yaw_left.q2 * 180.0 / 32768.0 < -90.0  # ~ -104 deg
	# zero (gyro disabled) -> neutral IMU, identity-safe euler
	z = parse_input(_frame())
	assert (z.gpitch, z.groll, z.gyaw, z.accel_z, z.q1, z.q2, z.q3, z.q4) == (0, 0, 0, 0, 0, 0, 0, 0)


def test_rest_frame_is_neutral() -> None:
	inp = parse_input(_frame())
	assert inp.buttons == 0
	assert (inp.dpad_x, inp.dpad_y, inp.lstick_x) == (0, 0, 0)


class _FakeMapper:
	def __init__(self) -> None:
		self.sent: list[tuple[str, int]] = []

	def send_feedback(self, hd) -> None:
		self.sent.append((HapticPos(hd.data[0]).name, hd.data[1]))


class _FakeState:
	def __init__(self, buttons: int) -> None:
		self.buttons = buttons


def _click(old: int, new: int) -> list[tuple[str, int]]:
	"""Runs queue_pad_click over a button transition, without touching USB."""
	c = SC2Controller.__new__(SC2Controller)
	c.mapper = _FakeMapper()
	c._old_state = _FakeState(old)
	c.queue_pad_click(_FakeState(new))
	return c.mapper.sent


class TestSimulatedPadClick:
	"""The v2's pads have no dome switch, so the click is produced in software.
	It has to fire on the edges only -- a pulse per frame while held would be a
	continuous buzz.
	"""

	def test_press_pulses_that_side(self) -> None:
		assert _click(0, SCButtons.LPAD) == [("LEFT", PAD_CLICK_PRESS)]
		assert _click(0, SCButtons.RPAD) == [("RIGHT", PAD_CLICK_PRESS)]

	def test_release_pulses_more_softly(self) -> None:
		assert _click(SCButtons.LPAD, 0) == [("LEFT", PAD_CLICK_RELEASE)]
		assert PAD_CLICK_RELEASE < PAD_CLICK_PRESS

	def test_silent_while_held(self) -> None:
		assert _click(SCButtons.LPAD, SCButtons.LPAD) == []

	def test_sides_are_independent(self) -> None:
		assert _click(SCButtons.LPAD, SCButtons.RPAD) == [
			("LEFT", PAD_CLICK_RELEASE), ("RIGHT", PAD_CLICK_PRESS)]

	def test_other_buttons_do_not_click(self) -> None:
		assert _click(0, SCButtons.A) == []
		assert _click(0, SCButtons.RPADTOUCH) == []


class _Daemon:
	def __init__(self) -> None:
		self.removed = []

	def remove_controller(self, controller) -> None:
		self.removed.append(controller)


def _turnoff_device():
	device = SC2Device.__new__(SC2Device)
	device._cmsg = []
	device._suppressed_endpoints = {}
	device.daemon = _Daemon()

	controller = SC2Controller.__new__(SC2Controller)
	controller._driver = device
	controller._ccidx = 2
	device._controllers = {3: controller}
	return device, controller


def test_turnoff_removes_controller_and_ignores_residual_input() -> None:
	device, controller = _turnoff_device()
	added = []

	class ReconnectedController:
		mapper = None

	device._add_controller = lambda endpoint: added.append(endpoint) or ReconnectedController()

	controller.turnoff()

	assert device._cmsg[0][4][1] == SCPacketType.OFF
	assert device.daemon.removed == [controller]
	assert device._controllers == {}
	assert 3 in device._suppressed_endpoints

	device._on_input(3, _frame({1: 1}))
	assert added == []

	device._suppressed_endpoints[3] -= TURNOFF_QUIET_PERIOD
	device._on_input(3, _frame({1: 1}))

	assert added == [3]
	assert 3 not in device._suppressed_endpoints
