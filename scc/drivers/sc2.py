"""SC Controller - Steam Controller (2025, "v2") Driver.

Implements the reverse-engineered protocol from
docs/steam-controller-v2-protocol.md. Validated end-to-end on real hardware
via the wireless Puck (0x1304): lizard-mode disable plus button / stick / pad
/ trigger / gyro input flow through scc-daemon to uinput.
Still TODO: haptics, the wired (0x1302) and Bluetooth (0x1303) transports,
real serial read-back, IMU axis-polarity tuning, and GUI assets (see inline).

Architecture mirrors the existing drivers:
  - the wireless "Controller Puck" (0x1304) is a multi-slot dongle, like
    sc_dongle.Dongle: 4 HID interfaces (2..5), one per controller slot, each
    with an interrupt-IN endpoint (3..6);
  - per-slot parsing/mapping mirrors steamdeck.py (separate left stick + left
    pad, right stick, real d-pad, plus grips);
  - commands are USB SET_REPORT, like sc_dongle, but addressed to feature
    report 0x01 of each slot's interface (v1/Deck used feature report 0x00).
"""

from __future__ import annotations

import logging
import struct
from collections import namedtuple
from enum import IntEnum

import usb1

from scc.constants import STICK_PAD_MAX, STICK_PAD_MIN, ControllerFlags, SCButtons
from scc.drivers.sc_dongle import SCController, SCPacketType
from scc.drivers.usb import USBDevice, register_hotplug_device

log = logging.getLogger("SC2")

VENDOR_ID = 0x28DE
PID_PUCK = 0x1304   # wireless Controller Puck (dongle) - the path implemented here
PID_WIRED = 0x1302  # controller over USB-C cable          - TODO
PID_BT = 0x1303     # controller over Bluetooth LE          - TODO

# The puck exposes 4 controller slots as HID interfaces 2..5, each with an
# interrupt-IN endpoint numbered one higher (3..6).
FIRST_INTERFACE = 2
FIRST_IN_ENDPOINT = 3
MAX_SLOTS = 4

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
# 40..47  quaternion x/y/z/w (i16)  } via configure(); zero/constant otherwise
# 48..53  gyro pitch/roll/yaw (i16) }
_INPUT_FORMAT = "<BBBBBBHHhhhhhhHhhH4xhhhhhhhhhh"
assert struct.calcsize(_INPUT_FORMAT) == INPUT_SIZE


class SC2Button(IntEnum):
    """Raw button bits as a 32-bit value: byte off2 = bits 0..7, off3 = 8..15,
    off4 = 16..23, off5 = 24..31.  Verified by per-control capture.
    """
    # off2
    A           = 1 << 0
    B           = 1 << 1
    X           = 1 << 2
    Y           = 1 << 3
    QUICKACCESS = 1 << 4          # the "..." button
    RSTICKPRESS = 1 << 5          # R3
    MENU        = 1 << 6          # hamburger
    R4          = 1 << 7
    # off3
    R5          = 1 << 8
    RB          = 1 << 9          # right bumper (R1)
    DPAD_DOWN   = 1 << 10
    DPAD_RIGHT  = 1 << 11
    DPAD_LEFT   = 1 << 12
    DPAD_UP     = 1 << 13
    UNKNOWN_3_6 = 1 << 14         # TODO: unmapped
    LSTICKPRESS = 1 << 15         # L3
    # off4
    STEAM       = 1 << 16
    L4          = 1 << 17
    L5          = 1 << 18
    LB          = 1 << 19         # left bumper (L1)
    RSTICKTOUCH = 1 << 20         # capacitive right-stick touch
    RPADTOUCH   = 1 << 21
    RPADPRESS   = 1 << 22
    RT_FULL     = 1 << 23         # right trigger digital full-pull
    # off5
    LSTICKTOUCH = 1 << 24         # capacitive left-stick touch
    LPADTOUCH   = 1 << 25
    LPADPRESS   = 1 << 26
    LT_FULL     = 1 << 27         # left trigger digital full-pull
    RGRIP_TOUCH = 1 << 28         # capacitive right handle (reads on against table)
    LGRIP_TOUCH = 1 << 29         # capacitive left handle
    UNKNOWN_5_6 = 1 << 30         # TODO: unmapped
    UNKNOWN_5_7 = 1 << 31         # TODO: unmapped


# raw SC2 bit -> SCButtons. Stick/handle capacitive-touch and the unknown bits
# are intentionally left out (no SCButtons equivalent yet).  L4/R4/L5/R5 follow
# the Deck convention: upper paddles -> (L/R)GRIP, lower -> (L/R)GRIP2.
_BUTTON_MAP = (
    (SC2Button.A,           SCButtons.A),
    (SC2Button.B,           SCButtons.B),
    (SC2Button.X,           SCButtons.X),
    (SC2Button.Y,           SCButtons.Y),
    (SC2Button.RB,          SCButtons.RB),
    (SC2Button.LB,          SCButtons.LB),
    (SC2Button.RT_FULL,     SCButtons.RT),
    (SC2Button.LT_FULL,     SCButtons.LT),
    (SC2Button.LSTICKPRESS, SCButtons.STICKPRESS),
    (SC2Button.RSTICKPRESS, SCButtons.RSTICKPRESS),
    (SC2Button.LPADTOUCH,   SCButtons.LPADTOUCH),
    (SC2Button.RPADTOUCH,   SCButtons.RPADTOUCH),
    (SC2Button.LPADPRESS,   SCButtons.LPAD),
    (SC2Button.RPADPRESS,   SCButtons.RPAD),
    (SC2Button.L4,          SCButtons.LGRIP),
    (SC2Button.R4,          SCButtons.RGRIP),
    (SC2Button.L5,          SCButtons.LGRIP2),
    (SC2Button.R5,          SCButtons.RGRIP2),
    (SC2Button.STEAM,       SCButtons.C),      # Steam/home button
    (SC2Button.MENU,        SCButtons.START),  # hamburger
    (SC2Button.QUICKACCESS, SCButtons.BACK),   # "..." (default; remappable)
)

# field set mirrors steamdeck.DeckInput so the mapper sees familiar attributes
SC2Input = namedtuple("SC2Input", (
    "buttons ltrig rtrig "
    "stick_x stick_y rstick_x rstick_y "
    "lpad_x lpad_y rpad_x rpad_y "
    "lpad_pressure rpad_pressure "
    "accel_x accel_y accel_z gpitch groll gyaw q1 q2 q3 q4 "
    "dpad_x dpad_y seq"
))
SC2_NULL = SC2Input(*([0] * len(SC2Input._fields)))


def _deadzone(v: int) -> int:
    return 0 if -STICK_DEADZONE < v < STICK_DEADZONE else v


def parse_input(data) -> SC2Input | None:
    """Parse a raw report 0x42 into an SC2Input. Returns None for other reports."""
    if not data or data[0] != INPUT_REPORT_ID or len(data) < INPUT_SIZE:
        return None
    (_rid, seq, b2, b3, b4, b5, ltrig, rtrig,
     lsx, lsy, rsx, rsy, lpx, lpy, lpz, rpx, rpy, rpz,
     ax, ay, az, q1, q2, q3, q4, gpitch, groll, gyaw) = struct.unpack(
        _INPUT_FORMAT, bytes(data[:INPUT_SIZE]))
    raw = b2 | (b3 << 8) | (b4 << 16) | (b5 << 24)

    buttons = 0
    for from_, to in _BUTTON_MAP:
        if raw & from_:
            buttons |= to

    dpad_x = STICK_PAD_MAX if raw & SC2Button.DPAD_RIGHT else STICK_PAD_MIN if raw & SC2Button.DPAD_LEFT else 0
    dpad_y = STICK_PAD_MAX if raw & SC2Button.DPAD_UP else STICK_PAD_MIN if raw & SC2Button.DPAD_DOWN else 0

    return SC2Input(
        buttons=buttons,
        # triggers are ~15-bit; scale to the 0..255 the mapper expects (cf. Deck >>7)
        ltrig=ltrig >> 7, rtrig=rtrig >> 7,
        stick_x=_deadzone(lsx), stick_y=_deadzone(lsy),
        rstick_x=_deadzone(rsx), rstick_y=_deadzone(rsy),
        lpad_x=lpx, lpad_y=lpy, rpad_x=rpx, rpad_y=rpy,
        lpad_pressure=lpz, rpad_pressure=rpz,
        # IMU: nonzero only when the gyro is enabled (configure() sends that).
        # gyro axes verified by motion: gpitch @48, groll @50, gyaw @52.
        accel_x=ax, accel_y=ay, accel_z=az, gpitch=gpitch, groll=groll, gyaw=gyaw,
        q1=q1, q2=q2, q3=q3, q4=q4,
        dpad_x=dpad_x, dpad_y=dpad_y, seq=seq,
    )
    # TODO: verify pad/stick Y polarity (may need inversion) once tested live.


class SC2Controller(SCController):
    flags = (
        ControllerFlags.SEPARATE_STICK
        | ControllerFlags.HAS_RSTICK
        | ControllerFlags.HAS_DPAD
    )

    def __init__(self, driver, ccidx: int, endpoint: int):
        super().__init__(driver, ccidx, endpoint)
        self._old_state = SC2_NULL

    def get_type(self) -> str:
        return "sc2"

    def __repr__(self) -> str:
        return f"<SC2 {self.get_id()}>"

    def get_gui_config_file(self) -> str | None:
        return None  # TODO: ship sc2.config.json + button images for the GUI

    def generate_serial(self) -> None:
        # real GET_SERIAL read-back over feature 0x01 is TODO; derive from topology
        self._serial = "%s:%s" % (self._driver.device.getBusNumber(), self._driver.device.getPortNumber())

    def disconnected(self) -> None:
        # override SCController.disconnected: the puck keeps no serial pool
        pass

    # --- v2 command channel -------------------------------------------------
    # All commands are CLEAR_MAPPINGS / CONFIGURE etc. (SCPacketType), but sent
    # to feature report 0x01 (handled by the puck's send_control override).

    def clear_mappings(self) -> None:
        # observed from Steam as "81 00" (after the 0x01 report-id prefix)
        self._driver.overwrite_control(self._ccidx, struct.pack(">BB", SCPacketType.CLEAR_MAPPINGS, 0x00))

    def configure(self, idle_timeout=None, enable_gyros=None, led_level=None) -> None:
        # Replay the config blocks captured from Steam. These put the controller
        # into gamepad mode; the exact gyro-enable register is still TODO.
        if led_level is not None:
            self._led_level = led_level
        # main config block: 87 0f 30 18 00 07 07 00 08 07 00 31 02 00 52 03
        self._driver.overwrite_control(self._ccidx, bytes(
            (SCPacketType.CONFIGURE, 0x0F, 0x30, 0x18, 0x00, 0x07, 0x07, 0x00,
             0x08, 0x07, 0x00, 0x31, 0x02, 0x00, 0x52, 0x03)))
        # LED level: 87 03 2d <level>
        self._driver.overwrite_control(self._ccidx, struct.pack(
            ">BBBB", SCPacketType.CONFIGURE, 0x03, 0x2D, int(self._led_level)))

    def set_gyro_enabled(self, enabled: bool) -> None:
        self._enable_gyros = enabled
        # TODO: which 0x87 CONFIGURE register enables the IMU?

    def get_gyro_enabled(self) -> bool:
        return self._enable_gyros

    def feedback(self, data) -> None:
        # TODO: haptics use Output report 0x80 on the interrupt-OUT endpoint,
        # e.g. "80 01 40 1f 00 00 fb ..." - format not yet decoded.
        pass


class SC2Puck(USBDevice):
    """The wireless Controller Puck: up to MAX_SLOTS controllers."""

    def __init__(self, device, handle, daemon):
        self.daemon = daemon
        USBDevice.__init__(self, device, handle)
        self.claim_by(klass=3, subclass=0, protocol=0)   # the HID interfaces
        self._controllers: dict[int, SC2Controller] = {}
        for i in range(MAX_SLOTS):
            self._listen(FIRST_IN_ENDPOINT + i)

    def _listen(self, endpoint: int) -> None:
        """Submit a lenient interrupt-IN transfer.

        Unlike USBDevice.set_input_interrupt, this resubmits regardless of the
        received length, because this endpoint multiplexes reports of several
        sizes (0x42=54B plus shorter 0x43/0x44/0x7b/... ). A strict length
        check would stop resubmitting on the first short report and freeze input.
        """
        def cb(transfer: usb1.USBTransfer) -> None:
            status = transfer.getStatus()
            if status == usb1.TRANSFER_COMPLETED:
                data = transfer.getBuffer()[:transfer.getActualLength()]
                try:
                    self._on_input(endpoint, data)
                except Exception:
                    log.exception("SC2 input handler failed")
            elif status in (usb1.TRANSFER_NO_DEVICE, usb1.TRANSFER_CANCELLED):
                return  # device gone / shutting down: do not resubmit
            try:
                transfer.submit()
            except Exception:
                pass

        transfer = self.handle.getTransfer()
        transfer.setInterrupt(usb1.ENDPOINT_IN | endpoint, INPUT_BUFFER, callback=cb)
        transfer.submit()
        self._transfer_list.append(transfer)

    # --- v2 transport: SET_REPORT to feature report 0x01 of the interface ---
    # The base class targets feature report 0x00 (wValue 0x0300); v2 numbered
    # reports require 0x0301 and a leading 0x01 byte in the payload.

    def send_control(self, index: int, data) -> None:
        # prefix the report-ID byte and pad/clamp to exactly 64 bytes (the
        # device stalls SET_REPORTs of any other length)
        payload = (bytes([0x01]) + bytes(data))[:64]
        payload = payload + b"\x00" * (64 - len(payload))
        self._cmsg.insert(0, (0x21, 0x09, 0x0301, index, payload, 0))

    def overwrite_control(self, index: int, data) -> None:
        for x in self._cmsg:
            x_index, x_data = x[3], x[4]
            # x_data[0] is our 0x01 prefix; the real packet starts at [1]
            if x_index == index and x_data[1:4] == (bytes([0x01]) + bytes(data))[1:4]:
                self._cmsg.remove(x)
                break
        self.send_control(index, data)

    def _slot_index(self, endpoint: int) -> int:
        return endpoint - FIRST_IN_ENDPOINT  # 0..MAX_SLOTS-1

    def _add_controller(self, endpoint: int) -> SC2Controller:
        interface = FIRST_INTERFACE + self._slot_index(endpoint)
        log.debug("New SC2 controller on slot %d (interface %d, endpoint %d)",
                  self._slot_index(endpoint), interface, endpoint)
        # ccidx == interface number so send_control() addresses the right slot
        c = SC2Controller(self, ccidx=interface, endpoint=endpoint)
        c.clear_mappings()
        c.configure()
        c.generate_serial()        # TODO: real GET_SERIAL read-back over 0x01
        self._controllers[endpoint] = c
        c.on_serial_got()          # registers the controller with the daemon
        return c

    def _on_input(self, endpoint: int, data) -> None:
        idata = parse_input(data)
        if idata is None:
            return                  # ignore non-0x42 reports for now
        c = self._controllers.get(endpoint) or self._add_controller(endpoint)
        if idata.seq % UNLIZARD_INTERVAL == 0:
            c.clear_mappings()      # keep lizard mode from creeping back
        if c.mapper:
            c.mapper.input(c, c._old_state, idata)
        c._old_state = idata

    def close(self) -> None:
        for c in self._controllers.values():
            self.daemon.remove_controller(c)
        self._controllers = {}
        USBDevice.close(self)


def init(daemon, config: dict) -> bool:
    """Register hotplug callbacks for the new Steam Controller."""

    def cb_puck(device, handle):
        return SC2Puck(device, handle, daemon)

    register_hotplug_device(cb_puck, VENDOR_ID, PID_PUCK)
    # TODO: wired (PID_WIRED) and Bluetooth (PID_BT) are single-interface
    # variants (cf. sc_by_cable / sc_by_bt) - register once implemented.
    return True
