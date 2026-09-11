# Steam Controller (2026, "v2") — USB/HID protocol notes

Reverse-engineering notes for adding support for the **new Steam Controller**
(released May 2026), distinct from the original Steam Controller (here "v1",
`28de:1102` wired / `28de:1142` dongle) and the Steam Deck (`28de:1205`).

Status: **input report (`0x42`) mapped**; command channel (lizard-mode
disable, gyro enable) and the IMU stream are **not yet reverse-engineered**.
Captured live from real hardware on Linux (`hid-generic`, no Steam running).

## Device topology

The controller ships with a wireless **"Controller Puck"** (dongle / charging
dock). USB IDs (all vendor `0x28de`, Valve):

| Product ID | Device |
|---|---|
| `0x1302` | the controller itself (USB-C cable) |
| `0x1303` | the controller over Bluetooth LE |
| `0x1304` | the **Controller Puck** (wireless dongle) |

The puck enumerates as a composite device with **6 interfaces**:

- IF 0+1: **CDC ACM** serial (`/dev/ttyACMx`) — purpose TBD (debug/config?).
- IF 2–5: **4 identical HID interfaces** — one per controller slot (like the
  v1 dongle's multi-slot design), each a `/dev/hidrawN`. With one controller
  paired, slot 1 (the first HID interface) carries its data.

When the controller is instead **wired over USB-C** (`0x1302`) it enumerates as
a **single HID interface 0** (interrupt IN `0x81`, OUT `0x01`, no CDC) with the
**same report descriptor and `0x42` report**, so all parsing and commands are
identical — only the interface index (0) and the endpoint numbers differ.
(Verified end-to-end: input, gyro, and haptics all work over the cable.)

Each HID interface's report descriptor declares (vendor usage page `0xFF00`):

- Input reports: `0x40` (mouse), `0x41` (keyboard) — **lizard mode** (the
  controller emulates mouse+keyboard by default), plus the gamepad reports
  `0x42` (53 B), `0x43` (14 B), `0x45` (45 B), `0x44` (5 B), `0x7b` (12 B),
  `0x79` (1 B).
- Output reports: `0x80`–`0x89` (3–63 B).
- Feature reports: `0x01`–`0x04` (63 B each) — the likely **command channel**.

By default the controller streams **`0x42` (the main gamepad state) at
~260 Hz even while lizard mode is active** — so raw gamepad data can be read
passively from hidraw with no handshake. The mouse/keyboard emulation runs in
parallel and must eventually be disabled (see Open questions).

## Report `0x42` — main gamepad state (54 bytes incl. report ID)

All multi-byte values are **little-endian**. Offsets are into the hidraw read
(offset 0 = the report-ID byte).

| Offset | Type | Field |
|---|---|---|
| 0 | u8 | Report ID = `0x42` |
| 1 | u8 | Packet counter (increments, wraps 0–255) |
| 2 | u8 | Button byte 0 (see bit table) |
| 3 | u8 | Button byte 1 |
| 4 | u8 | Button byte 2 |
| 5 | u8 | Button byte 3 (rest = `0x30`: grip-touch bits set when held/on table) |
| 6–7 | u16 | Left trigger, analog (0 … ~32767) |
| 8–9 | u16 | Right trigger, analog |
| 10–11 | i16 | Left stick X (±32767; off-center & noisy at rest → needs deadzone) |
| 12–13 | i16 | Left stick Y |
| 14–15 | i16 | Right stick X |
| 16–17 | i16 | Right stick Y |
| 18–19 | i16 | Left pad X |
| 20–21 | i16 | Left pad Y |
| 22–23 | u16 | Left pad pressure (0 … ~650 seen) |
| 24–25 | i16 | Right pad X |
| 26–27 | i16 | Right pad Y |
| 28–29 | u16 | Right pad pressure |
| 30–33 | u32 | IMU timestamp/counter |
| 34–39 | i16×3 | **accelerometer** X/Y/Z (Z ≈ +16271 ≈ 1 g flat at rest) |
| 40–45 | i16×3 | **gyro angular rates** about x/y/z (≈0 whenever still) |
| 46–53 | i16×4 | **orientation quaternion**, laid out **w`@46` x`@48` y`@50` z`@52`** |

Offsets 30–53 are populated **only when the gyro is enabled** (constant
otherwise).

The rates/quaternion split was pinned down from held-pose captures: the four
i16 at 46/48/50/52 have **norm exactly 32768 in every orientation** (a unit
quaternion), while 40–45 read ≈0 whenever the controller is still (rates).
An earlier revision of this document had the boundary wrong (quaternion at
40–47, rates at 48–53) — that misread the orientation components as rates,
which is why they "followed the angle".

**IMU axes** (right-handed, Z up), verified from seven held poses:
x = pitch (nose-up +), y = roll (roll-right +), z = yaw (yaw-left +).
Accelerometer: gravity reads **+Z** flat, **−Y** nose-down, **−X** roll-right.
The quaternion is firmware-fused: pitch/roll are gravity-referenced (drift
free); yaw is referenced to the enable-time orientation and drifts slowly.
The driver converts the quaternion to euler angles host-side and reports
EUREL (2¹⁵/π fixed-point) angles in DS4 conventions.

### Button bits (offsets 2–5)

| Byte | bit `0x01` | `0x02` | `0x04` | `0x08` | `0x10` | `0x20` | `0x40` | `0x80` |
|---|---|---|---|---|---|---|---|---|
| **2** | A | B | X | Y | QuickAccess (…) | R3 (rstick click) | Menu (☰) | R4 |
| **3** | R5 | R1 (bumper) | Dpad Down | Dpad Right | Dpad Left | Dpad Up | View (⧉) | L3 (lstick click) |
| **4** | Steam | L4 | L5 | L1 (bumper) | RStick touch | RPad touch | RPad click | RT full-pull (digital) |
| **5** | LStick touch | LPad touch | LPad click | LT full-pull (digital) | **R** grip touch | **L** grip touch | *?* | *?* |

Notes:
- **Capacitive touch** is reported for both thumbsticks (off4 `0x10`, off5
  `0x01`) and both trackpads (off4 `0x20`, off5 `0x02`).
- **Capacitive grip/handle sensors** (off5 `0x10`/`0x20`) are the feature this
  controller adds over a bare Steam Deck. They read **on whenever the handles
  are touched — including resting on a table** (byte 5 rests at `0x30`). With
  hands fully off the handles, byte 5 reads `0x00`.
- Four **system buttons**: Steam (off4 `0x01`), Menu ☰ (off2 `0x40`), View ⧉
  (off3 `0x40`), QuickAccess … (off2 `0x10`). The driver maps them to
  `C` / `START` / `BACK` / `DOTS` respectively.
- Triggers report both a 16-bit analog value (off 6–9) **and** a digital
  full-pull bit (off4 `0x80` / off5 `0x08`).
- Unknown bits remaining: off5 `0x40`, off5 `0x80` (may be unused or rare
  inputs not present/triggered on the test unit).

## Comparison to the Steam Deck (`scc/drivers/steamdeck.py`)

Same *field set* as `DeckInput`, but a **different, more compact byte layout**:

- Buttons packed into **4 bytes**, not the Deck's `u64`.
- Sticks come right after the triggers; trackpads carry an **extra pressure**
  word the Deck struct doesn't have.
- The IMU (accel/gyro/quaternion) is **not in the default stream**, whereas the
  Deck always sends it.

So `DeckInput` can't be reused verbatim, but the Deck **driver skeleton** is the
right model: claim the HID interface, parse the packet into an input struct,
map to `SCButtons`, and **periodically re-disable lizard mode** (the Deck calls
`clear_mappings()` every `UNLIZARD_INTERVAL` frames — see
`steamdeck.py::_on_input`).

## Command channel (host → device)

Captured by sniffing Steam's USB traffic (`usbmon`) as it grabbed the
controller. Commands are USB control transfers — **`SET_REPORT`**
(`bmRequestType=0x21`, `bRequest=0x09`):

- `wValue` = `0x03<reportID>` for a **Feature** report (e.g. `0x0301` = feature
  report `0x01`, the command channel) or `0x02<reportID>` for an **Output** report;
- `wIndex` = the **interface number (2–5)** — i.e. which of the four puck slots;
- `wLength` = `0x0040` (64-byte payload).

Payload layout: `[reportID, packetType, length, params… , 0-pad to 64]` — the
same shape as the v1/Deck command packets. The `packetType` opcodes match
`SCPacketType` in `scc/drivers/sc_dongle.py`:

| Opcode | Name | Observed | Meaning |
|---|---|---|---|
| `0x81` | CLEAR_MAPPINGS | `01 81 00…` (resent ~periodically) | **disable lizard mode** / clear mappings (heartbeat) |
| `0x8E` | LIZARD_MODE | `01 8e 00…` | lizard-mode control |
| `0x87` | CONFIGURE / LED | see below | settings & LED |
| `0xAE` | GET_SERIAL | `01 ae 15 01…` | request serial (read back via GET_REPORT) |
| `0xC1` | SET_AUDIO_INDICES | `01 c1 10 …` | audio indices |
| `0xB4` | *(v2, not in v1)* | `b4 00…` via feature report `0x00`, polled continuously | wireless poll / keepalive? |
| `0xED`/`0xAD`/`0xDC`/`0xE2` | *(v2)* | `01 ed … "user/wireless_transport"`, `"esb/bond"` | v2 key/value pairing & transport config |

`CONFIGURE` (`0x87`) = `87 <len> <configType> <value…>`:
- `87 03 2d <level>` — **LED brightness** (`configType 0x2D`; `0x64` = 100%).
- `87 0f 30 <gyro> 00 07 07 00 08 07 00 31 02 00 52 03` — main config block
  (`configType 0x30`, len `0x0f`). The byte after `30` is the **gyro/accel
  enable**: `0x18` turns the IMU on, `0x00` off (confirmed live; cf. the Deck's
  `0x1C`). Once enabled, IMU data streams in report `0x42` at offsets ~31–53.
- `87 06 34 ffff 35 ffff`, `87 03 22 64`, `87 03 23 50` — `(register, u16)` writes.

Haptics: **Output report `0x82`** on the **interrupt-OUT** endpoint (its number
equals the interface, e.g. EP `0x02` for slot 1) — the device **stalls it over
SET_REPORT control**, so it must go to the interrupt endpoint. Layout
`82 <side> <command> <gain>`: `side` 0=left / 1=right / 2=both; `command`
`0x01`=click, `0x02`=strong click; `gain` a **signed i8 in decibels**, clamped
by the firmware to -23…+24. Note the last byte is NOT a 0..255 amplitude -- we
sent it as one until v0.6.0.7, which made the strength control non-monotonic.

The full haptic report family is documented by Valve themselves: they upstreamed
this controller ("Triton") to SDL3, so `src/joystick/hidapi/SDL_hidapi_steam_triton.c`
is a reference implementation. Corroborated independently by iczero's RE, collected
at <https://github.com/CouchTurtle/sc2-research> (`docs/HAPTICS.md`):

| report | name | payload |
| --- | --- | --- |
| `0x80` | `HAPTIC_RUMBLE` | `type u8, intensity u16, left{speed u16, gain i8}, right{speed u16, gain i8}` — **verified live** |
| `0x81` | `HAPTIC_PULSE` | `side u8, on_us u16, off_us u16, repeat u16` |
| `0x82` | `HAPTIC_COMMAND` | `side u8, command u8 (0=stop all, 1=click, 2=strong click), gain i8 dB` |
| `0x83` | `HAPTIC_LFO_TONE` | `side u8, gain i8, frequency u16 Hz, duration u16, lfo_freq u16 Hz, lfo_depth u8` — **verified live** |
| `0x84` | `HAPTIC_LOG_SWEEP` | `side u8, gain i8, duration u16, start_freq u16, end_freq u16` — **verified live** |
| `0x85` | `HAPTIC_SCRIPT` | `side u8, script_id u8, gain i8` — **verified live**, ids below |

Firmware preset ids for `0x85`, names from the same RE (the list may be partial;
nothing says `0x10` is the last). Played on hardware: the ids are real and the
names broadly describe what you feel. CONTROLLER_VERY_ON, CONTROLLER_OFF and
PHONE_RINGING_1 are strong and unmistakable; several others are subtle.
WILHELM_SCREAM is barely perceptible even at maximum gain -- it is a long
sample, so this is most likely the preset itself rather than anything we send:

| id | name | id | name |
| --- | --- | --- | --- |
| `0x01` | CONTROLLER_ON | `0x09` | DOWN_SIX |
| `0x02` | CONTROLLER_VERY_ON | `0x0a` | WHOOP_UP_3 |
| `0x03` | TRILL_UP | `0x0b` | WHOOP_DOWN |
| `0x04` | TRILL_DOWN | `0x0c` | PHONE_RINGING_1 |
| `0x05` | CONTROLLER_OFF | `0x0d` | RINGBACK_TONE |
| `0x06` | UP_FIVE | `0x0e` | PHONE_RINGING_2 |
| `0x07` | DOWN_FIVE | `0x0f` | PHONE_RINGING_3 |
| `0x08` | UP_SIX | `0x10` | WILHELM_SCREAM |
| `0x86`–`0x89` | audio stream | actuator PCM / u-law streaming |

`0x83` and `0x84` are hardware-verified too. A sweep is clearly distinguishable
from a flat tone, so `start_freq`/`end_freq` do what they say. The LFO fields
work but are weak: at `lfo_freq` 4 / `lfo_depth` 128 the modulation is barely
there, and only at 10 / 255 is it obvious. Depth may not be a percentage.

`0x80` is hardware-verified: `type`, `intensity` and both `gain` fields at 0,
the two `speed` fields driving their own actuator independently. Confirmed with
`fftest` on the emulated pad, whose "strong rumble (heavy motor)" and "weak
rumble (light motor)" arrive as the two Linux FF_RUMBLE magnitudes and come out
on the left and right actuators respectively:

    strong=32768 weak=0      -> 80 00 00 00 00 80 00 00 00 00   (left only)
    strong=0     weak=49152  -> 80 00 00 00 00 00 00 00 c0 00   (right only)

**Open question:** the field is named `speed`, not amplitude, and `gain` is a
separate i8 in dB. The second case above carries the LARGER number yet is
clearly weaker in the hand, so `speed` is probably not linear amplitude -- more
likely a motor speed, where higher means a lighter, higher-frequency buzz. Both
gains are 0 dB here because that is what Valve's driver sends; exposing gain
per side, and the `intensity` field, is untried and may be the better volume
control.

So **continuous variable rumble is `0x80`**, and the earlier note here that it was
"not yet captured" was wrong -- the connect-time `0x80` traffic is that report,
sent with zero speeds, which is why nothing was felt. SDL sends the two SDL rumble
magnitudes straight through as `left.speed` / `right.speed` (u16) with `gain` 0.
Layouts for `0x83`-`0x89` are from RE and not verified here.

**Implication:** the existing `sc_dongle.py` command builders port over; the
differences are the **transport** (SET_REPORT/feature to a per-slot interface
index, not v1's bulk endpoint) and the **CONFIGURE register layout**.

## Open questions / TODO

1. **IMU rate scale**: the angular-rate unit (LSB per deg/s) at offsets 40–45
   is not measured yet — relative-mode sensitivity may need tuning vs the DS4.
   (Layout, axes and signs of rates/quaternion/accel are now verified; see the
   report-0x42 section.)
2. **Trackpad pressure** scaling and the exact meaning of the pressure word.
3. The remaining unknown button bits.
4. The **CDC ACM** interface's purpose.

## How this was captured

See `tools/sc2-probe/` — a passive hidraw capture harness (read-only on the
device). Method: capture a still **baseline**, then capture each control while
actuating it, and diff per-byte ranges / changed bits against the baseline.
The two analog sticks were told apart from the IMU by checking which 16-bit
field saturates to ±32767 for which stick. Grip-touch bits were isolated with a
"hands off the handles" reference hold vs. a normal hold.
