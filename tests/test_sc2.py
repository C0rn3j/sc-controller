"""Unit tests for the new Steam Controller (v2) report-0x42 parser.

Frames are synthesized from docs/steam-controller-v2-protocol.md; no hardware
or captured data is required. These lock the reverse-engineered byte/bit layout.
"""
import struct

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, SCButtons
from scc.drivers.sc2 import parse_input


def _frame(bytes_=None, i16=None, u16=None):
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


def test_rejects_other_reports():
    assert parse_input(b"\x40" + b"\x00" * 53) is None  # mouse report
    assert parse_input(b"") is None
    assert parse_input(b"\x42\x00") is None              # too short


def test_face_buttons():
    assert parse_input(_frame({2: 0x01})).buttons & SCButtons.A
    assert parse_input(_frame({2: 0x02})).buttons & SCButtons.B
    assert parse_input(_frame({2: 0x04})).buttons & SCButtons.X
    assert parse_input(_frame({2: 0x08})).buttons & SCButtons.Y
    assert not parse_input(_frame({2: 0x01})).buttons & SCButtons.B


def test_bumpers():
    assert parse_input(_frame({4: 0x08})).buttons & SCButtons.LB  # L1
    assert parse_input(_frame({3: 0x02})).buttons & SCButtons.RB  # R1


def test_grips_and_paddles():
    assert parse_input(_frame({4: 0x02})).buttons & SCButtons.LGRIP    # L4
    assert parse_input(_frame({2: 0x80})).buttons & SCButtons.RGRIP    # R4
    assert parse_input(_frame({4: 0x04})).buttons & SCButtons.LGRIP2   # L5
    assert parse_input(_frame({3: 0x01})).buttons & SCButtons.RGRIP2   # R5


def test_system_buttons():
    assert parse_input(_frame({4: 0x01})).buttons & SCButtons.C        # Steam
    assert parse_input(_frame({2: 0x40})).buttons & SCButtons.START    # Menu (☰)
    assert parse_input(_frame({3: 0x40})).buttons & SCButtons.BACK     # View (⧉)
    assert parse_input(_frame({2: 0x10})).buttons & SCButtons.DOTS     # QuickAccess (…)


def test_stick_clicks():
    assert parse_input(_frame({3: 0x80})).buttons & SCButtons.STICKPRESS
    assert parse_input(_frame({2: 0x20})).buttons & SCButtons.RSTICKPRESS


def test_triggers():
    assert parse_input(_frame(u16={6: 0x7F80})).ltrig == 255          # analog -> 0..255
    assert parse_input(_frame(u16={8: 0x7000})).rtrig == (0x7000 >> 7)
    assert parse_input(_frame({5: 0x08})).buttons & SCButtons.LT       # digital full-pull
    assert parse_input(_frame({4: 0x80})).buttons & SCButtons.RT


def test_sticks_and_deadzone():
    assert parse_input(_frame(i16={10: 30000})).stick_x == 30000
    assert parse_input(_frame(i16={12: -30000})).stick_y == -30000
    assert parse_input(_frame(i16={14: 20000})).rstick_x == 20000
    assert parse_input(_frame(i16={16: -25000})).rstick_y == -25000
    assert parse_input(_frame(i16={10: 100})).stick_x == 0            # within deadzone


def test_pads():
    inp = parse_input(_frame(i16={18: 12345, 20: -6789}, u16={22: 400}))
    assert (inp.lpad_x, inp.lpad_y, inp.lpad_pressure) == (12345, -6789, 400)
    inp = parse_input(_frame(i16={24: -11111, 26: 22222}, u16={28: 650}))
    assert (inp.rpad_x, inp.rpad_y, inp.rpad_pressure) == (-11111, 22222, 650)


def test_dpad():
    assert parse_input(_frame({3: 0x20})).dpad_y == STICK_PAD_MAX   # up
    assert parse_input(_frame({3: 0x04})).dpad_y == STICK_PAD_MIN   # down
    assert parse_input(_frame({3: 0x08})).dpad_x == STICK_PAD_MAX   # right
    assert parse_input(_frame({3: 0x10})).dpad_x == STICK_PAD_MIN   # left


def test_imu():
    # IMU lands at offsets 34..53 (only nonzero when the gyro is enabled).
    assert parse_input(_frame(i16={48: 5000})).gpitch == 5000
    assert parse_input(_frame(i16={50: -6000})).groll == -6000
    assert parse_input(_frame(i16={52: 7000})).gyaw == 7000
    assert parse_input(_frame(i16={38: 16000})).accel_z == 16000
    assert parse_input(_frame(i16={46: 32000})).q4 == 32000
    # zero (gyro disabled) -> neutral IMU
    z = parse_input(_frame())
    assert (z.gpitch, z.groll, z.gyaw, z.accel_z, z.q4) == (0, 0, 0, 0, 0)


def test_rest_frame_is_neutral():
    inp = parse_input(_frame())
    assert inp.buttons == 0
    assert (inp.dpad_x, inp.dpad_y, inp.stick_x) == (0, 0, 0)
