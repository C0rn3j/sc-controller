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
| 30–53 | 24 B | **Constant** in all captures → IMU is **disabled by default** (see below) |

### Button bits (offsets 2–5)

| Byte | bit `0x01` | `0x02` | `0x04` | `0x08` | `0x10` | `0x20` | `0x40` | `0x80` |
|---|---|---|---|---|---|---|---|---|
| **2** | A | B | X | Y | QuickAccess (…) | R3 (rstick click) | Menu (☰) | R4 |
| **3** | R5 | R1 (bumper) | Dpad Down | Dpad Right | Dpad Left | Dpad Up | *?* | L3 (lstick click) |
| **4** | Steam | L4 | L5 | L1 (bumper) | RStick touch | RPad touch | RPad click | RT full-pull (digital) |
| **5** | LStick touch | LPad touch | LPad click | LT full-pull (digital) | **R** grip touch | **L** grip touch | *?* | *?* |

Notes:
- **Capacitive touch** is reported for both thumbsticks (off4 `0x10`, off5
  `0x01`) and both trackpads (off4 `0x20`, off5 `0x02`).
- **Capacitive grip/handle sensors** (off5 `0x10`/`0x20`) are the feature this
  controller adds over a bare Steam Deck. They read **on whenever the handles
  are touched — including resting on a table** (byte 5 rests at `0x30`). With
  hands fully off the handles, byte 5 reads `0x00`.
- Triggers report both a 16-bit analog value (off 6–9) **and** a digital
  full-pull bit (off4 `0x80` / off5 `0x08`).
- Unknown bits remaining: off3 `0x40`, off5 `0x40`, off5 `0x80` (may be unused
  or rare buttons not present/triggered on the test unit).

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

## Open questions / TODO

1. **Command channel** (Feature reports `0x01`–`0x04` / Output `0x80`–`0x89`):
   - How to **disable lizard mode** (stop the mouse/keyboard emulation) —
     required for usable gamepad behavior.
   - How to **enable the gyro/accel** (cf. the Deck's
     `configure(enable_gyros=…)`).
   - Best obtained by **sniffing Steam's own USB traffic** (`usbmon`) while it
     configures the controller, rather than guessing report payloads.
2. **IMU stream**: once enabled, determine whether it fills offsets 30–53 of
   `0x42` or arrives via another report (`0x43`/`0x45`), and its scale/order.
3. **Trackpad pressure** scaling and the exact meaning of the pressure word.
4. The remaining unknown button bits.
5. The **CDC ACM** interface's purpose.

## How this was captured

See `tools/sc2-probe/` — a passive hidraw capture harness (read-only on the
device). Method: capture a still **baseline**, then capture each control while
actuating it, and diff per-byte ranges / changed bits against the baseline.
The two analog sticks were told apart from the IMU by checking which 16-bit
field saturates to ±32767 for which stick. Grip-touch bits were isolated with a
"hands off the handles" reference hold vs. a normal hold.
