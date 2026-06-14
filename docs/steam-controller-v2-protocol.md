# Steam Controller (2025, "v2") — USB/HID protocol notes

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
| 34–39 | i16×3 | **accelerometer** X/Y/Z (Z ≈ +16271 ≈ 1 g at rest) |
| 40–47 | i16×4 | **orientation quaternion** x/y/z/w (w ≈ +32767 at rest) |
| 48–53 | i16×3 | **gyro** pitch / roll / yaw (angular rate, ≈0 at rest) |

Offsets 30–53 are populated **only when the gyro is enabled** (constant
otherwise). Gyro axes verified by isolated rotations (pitch→`@48`, roll→`@50`,
yaw→`@52`); accel X/Y labels and IMU signs are provisional (see open questions).

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

Haptics: an **Output report `0x80`** on interrupt EP2, e.g.
`80 01 40 1f 00 00 fb …`.

**Implication:** the existing `sc_dongle.py` command builders port over; the
differences are the **transport** (SET_REPORT/feature to a per-slot interface
index, not v1's bulk endpoint) and the **CONFIGURE register layout**.

## Open questions / TODO

1. **IMU polarity (partly verified)**: gyro **yaw** and **pitch** signs checked
   live via a gyro→mouse test — pitch is inverted in the driver so up→up; yaw is
   natural. Still provisional: gyro **roll** sign (not exercised by that test),
   and the accel X/Y labels / signs and quaternion handedness.
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
