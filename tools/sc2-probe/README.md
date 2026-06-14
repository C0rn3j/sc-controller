# sc2-probe — Steam Controller v2 HID capture harness

Read-only reverse-engineering tool used to map the new Steam Controller's
(2025) main gamepad HID report. Results are written up in
[`docs/steam-controller-v2-protocol.md`](../../docs/steam-controller-v2-protocol.md).

It passively reads report `0x42` from the puck's HID slots
(`/dev/hidraw5`–`8` on the test machine; auto-detected). It never writes to the
device. Captures are saved to `/tmp/sc2_<label>.bin` (raw 54-byte frames).

Requires read access to the `hidraw` nodes (e.g. membership in the `input`
group, or the udev rule in `scripts/69-sc-controller.rules`). No root needed.

## Usage

```sh
# 1. Baseline — controller perfectly still:
python3 sc2.py rec rest 7

# 2. Guided auto-walk of all controls (flat on table, then held):
python3 sc2.py guided

# 3. Focused grip/paddle re-test (held in the air):
python3 sc2.py grips

# 4. Consolidated analysis across every capture:
python3 sc2.py report
```

Individual commands:

- `rec <label> [dur]` — capture `0x42` frames to `/tmp/sc2_<label>.bin` and
  print which byte offsets moved.
- `diff <baseline> <label>` — show offsets that moved beyond rest noise,
  masking sensor/always-moving bytes.
- `guided` / `grips` — auto-walking guided capture sessions (no typing during
  the run; countdowns tell you when to actuate).
- `report` — load all captures listed in `/tmp/sc2_manifest.txt` and print a
  consolidated control → (offset, bit) map.

## Method

Capture a still baseline, then capture each control while actuating it, and
diff per-byte ranges / changed bits against the baseline. Analog sticks are
told apart from the (disabled) IMU by which 16-bit field saturates to ±32767.
Capacitive grip bits are isolated with a "hands off the handles" reference hold
versus a normal hold.
