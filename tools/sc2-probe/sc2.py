#!/usr/bin/env python3
"""
sc2.py - reverse-engineering capture harness for the new Steam Controller (v2)
puck (28de:1304), report 0x42 (main gamepad state).  Read-only on the device.

Usage:
  sc2.py rec <label> [dur=5]     capture 0x42 frames -> /tmp/sc2_<label>.bin,
                                 print per-byte min/max/range summary
  sc2.py diff <baseline> <label> compare a control capture against baseline,
                                 flag byte offsets that moved beyond rest noise
"""
import os, select, sys, time, glob

REPORT_ID = 0x42
FRAME_LEN = 54           # 1 id + 53 payload

def find_slots() -> list[tuple[int, str]]:
    slots = []
    for p in sorted(glob.glob("/dev/hidraw*")):
        try:
            fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        slots.append((fd, p))
    return slots

def rec(label: str, dur: float, quiet: bool = False) -> None:
    slots = find_slots()
    fds = [fd for fd, _ in slots]
    name = {fd: p for fd, p in slots}
    frames = []          # list of bytes (the 0x42 frames, from the active slot)
    active = None
    end = time.monotonic() + dur
    while time.monotonic() < end:
        r, _, _ = select.select(fds, [], [], 0.2)
        for fd in r:
            try:
                data = os.read(fd, 128)
            except OSError:
                continue
            if not data or data[0] != REPORT_ID:
                continue
            if active is None:
                active = name[fd]
            if name[fd] == active:
                frames.append(bytes(data))
    for fd in fds:
        os.close(fd)
    if not frames:
        print("** no 0x42 frames captured (controller idle/off?) **")
        return
    path = f"/tmp/sc2_{label}.bin"
    with open(path, "wb") as f:
        for fr in frames:
            f.write(fr.ljust(FRAME_LEN, b"\x00")[:FRAME_LEN])
    n = len(frames)
    L = min(len(fr) for fr in frames)
    mins = [255] * L
    maxs = [0] * L
    for fr in frames:
        for i in range(L):
            b = fr[i]
            if b < mins[i]: mins[i] = b
            if b > maxs[i]: maxs[i] = b
    print(f"[{active}] captured {n} frames of 0x42 -> {path}")
    if not quiet:
        print("offset  rest   min  max  range   (only bytes that moved)")
        for i in range(L):
            rng = maxs[i] - mins[i]
            if rng > 0:
                print(f"  {i:2d}    0x{frames[0][i]:02x}   {mins[i]:3d}  {maxs[i]:3d}   {rng:4d}")

def load(label: str) -> list[bytes]:
    path = f"/tmp/sc2_{label}.bin"
    raw = open(path, "rb").read()
    return [raw[i:i+FRAME_LEN] for i in range(0, len(raw), FRAME_LEN)]

def noisy(frames: list[bytes], L: int, thresh: int) -> set[int]:
    s = set()
    for i in range(L):
        if (max(f[i] for f in frames) - min(f[i] for f in frames)) > thresh:
            s.add(i)
    return s

def diff(base_label: str, label: str, margin: int = 4) -> None:
    base = load(base_label)
    ctrl = load(label)
    L = min(min(len(f) for f in base), min(len(f) for f in ctrl))
    bmin = [min(f[i] for f in base) for i in range(L)]
    bmax = [max(f[i] for f in base) for i in range(L)]
    cmin = [min(f[i] for f in ctrl) for i in range(L)]
    cmax = [max(f[i] for f in ctrl) for i in range(L)]
    # sensor offsets = noisy at rest OR noisy in the dedicated IMU sweep capture
    sensor = noisy(base, L, 2 * margin)
    sensor.add(1)  # packet counter
    imu_path = "/tmp/sc2_imu.bin"
    if os.path.exists(imu_path):
        imu = [open(imu_path, "rb").read()[j:j+FRAME_LEN]
               for j in range(0, os.path.getsize(imu_path), FRAME_LEN)]
        sensor |= noisy(imu, L, 2 * margin)
    print(f"diff: baseline={base_label} ({len(base)} fr) vs {label} ({len(ctrl)} fr)"
          f"   [masking sensor offsets {sorted(sensor)}]")
    print("offset  base[min..max]   ctrl[min..max]   note")
    moved = []
    for i in range(L):
        if i in sensor:
            continue
        lo = bmin[i] - margin
        hi = bmax[i] + margin
        if cmin[i] < lo or cmax[i] > hi:
            moved.append(i)
            print(f"  {i:2d}    {bmin[i]:3d}..{bmax[i]:<3d}        {cmin[i]:3d}..{cmax[i]:<3d}        <== MOVED")
    if not moved:
        print("  (no clear movement beyond rest noise)")
    else:
        print(f"\nmoved offsets: {moved}")

PHASE1 = [  # flat on the table
    ("a",            "press / release button A about 5 times"),
    ("b",            "press / release button B about 5 times"),
    ("x",            "press / release button X about 5 times"),
    ("y",            "press / release button Y about 5 times"),
    ("dpad_up",      "press the D-pad UP a few times (skip if no d-pad)"),
    ("dpad_down",    "press the D-pad DOWN a few times (skip if none)"),
    ("dpad_left",    "press the D-pad LEFT a few times (skip if none)"),
    ("dpad_right",   "press the D-pad RIGHT a few times (skip if none)"),
    ("lstick",       "move the LEFT stick in full circles + push to all extremes"),
    ("lstick_click", "press the LEFT stick straight DOWN about 5 times"),
    ("rstick",       "move the RIGHT stick in full circles + all extremes"),
    ("rstick_click", "press the RIGHT stick straight DOWN about 5 times"),
    ("lpad_touch",   "REST a fingertip on the LEFT pad, lift off, repeat (no press)"),
    ("lpad_move",    "slide a finger ALL OVER the LEFT pad surface"),
    ("lpad_click",   "PRESS the LEFT pad down (click) about 5 times"),
    ("rpad_touch",   "REST a fingertip on the RIGHT pad, lift off, repeat (no press)"),
    ("rpad_move",    "slide a finger ALL OVER the RIGHT pad surface"),
    ("rpad_click",   "PRESS the RIGHT pad down (click) about 5 times"),
    ("l1",           "press / release the LEFT bumper (L1) about 5 times"),
    ("r1",           "press / release the RIGHT bumper (R1) about 5 times"),
    ("ltrig",        "pull the LEFT trigger fully in and release, about 5 times"),
    ("rtrig",        "pull the RIGHT trigger fully in and release, about 5 times"),
    ("steam",        "press the STEAM button about 5 times"),
    ("menu",         "press the MENU / hamburger button about 5 times"),
    ("quickaccess",  "press the QUICK-ACCESS (...) button about 5 times (skip if none)"),
]
PHASE2 = [  # held in your hands
    ("l4",     "press / release the LEFT rear grip BUTTON (L4) about 5 times"),
    ("r4",     "press / release the RIGHT rear grip BUTTON (R4) about 5 times"),
    ("l5",     "press / release a 2nd LEFT grip button (L5) if present, else skip"),
    ("r5",     "press / release a 2nd RIGHT grip button (R5) if present, else skip"),
    ("grip_l", "SQUEEZE the LEFT handle (capacitive grip), release, repeat"),
    ("grip_r", "SQUEEZE the RIGHT handle (capacitive grip), release, repeat"),
]

def _walk(items: list[tuple[str, str]], manifest: list[str]) -> None:
    for name, how in items:
        print(f"\n>>> NEXT: {name.upper()}  —  {how}")
        for s in (5, 4, 3, 2, 1):
            sys.stdout.write(f"    starting in {s}...   \r"); sys.stdout.flush(); time.sleep(1)
        print("    GO!  (actuate now for 5 seconds)        ")
        rec(name, 5, quiet=True)
        try:
            diff("rest", name)
        except Exception as e:
            print("  (diff skipped:", e, ")")
        manifest.append(name)
        time.sleep(0.6)

GRIPWALK = [
    ("notouch_base", "Hold the controller ONLY by the TOP edge / trackpads with your\n"
                     "      fingertips — palms and fingers OFF both handles. Hold still."),
    ("hold_base",    "Now hold NORMALLY in both hands (palms wrapped around the handles),\n"
                     "      but do NOT press any rear paddle/grip buttons. Hold still."),
    ("g_l4",         "Keep holding normally. Press/release the UPPER-LEFT rear button (L4) ~5x"),
    ("g_r4",         "Press/release the UPPER-RIGHT rear button (R4) ~5x"),
    ("g_l5",         "Press/release a LOWER-LEFT rear button (L5) ~5x — or do nothing if none"),
    ("g_r5",         "Press/release a LOWER-RIGHT rear button (R5) ~5x — or nothing if none"),
    ("g_grip_l",     "From a light hold, firmly SQUEEZE the LEFT handle, release, repeat"),
    ("g_grip_r",     "Firmly SQUEEZE the RIGHT handle, release, repeat"),
]

def grips() -> None:
    print("\n=== GRIP / PADDLE RE-TEST (held in the air, no table contact) ===")
    print("No motion noise to worry about (IMU isn't in this report). The point is to")
    print("capture clean reference holds, then isolate each rear button / grip touch.\n")
    manifest = []
    input("Press Enter to begin (hold the controller as each step says)...")
    _walk(GRIPWALK, manifest)
    print("\ndone:", manifest, " (bins at /tmp/sc2_<name>.bin)")

def guided() -> None:
    if not os.path.exists("/tmp/sc2_rest.bin"):
        print("No baseline yet. Set the controller STILL and FLAT, then:")
        input("  press Enter to capture a 6s baseline...")
        rec("rest", 6, quiet=True)
    print("\n=== GUIDED CONTROL MAPPING (auto-walk, no typing during the run) ===")
    print("Each step names a control, counts down 3..2..1, then captures 5s.")
    print("Just actuate the named control when it says GO. If your controller")
    print("doesn't have that control, do nothing for those 5s (it'll show empty).")
    manifest = []
    input("\nPHASE 1 — keep the controller FLAT ON THE TABLE. Press Enter to begin...")
    _walk(PHASE1, manifest)
    input("\nPHASE 2 — now PICK UP the controller and hold it normally. Press Enter...")
    _walk(PHASE2, manifest)
    with open("/tmp/sc2_manifest.txt", "w") as f:
        f.write("\n".join(manifest) + "\n")
    print("\ndone. captured controls:", manifest)
    print("bins: /tmp/sc2_<name>.bin   manifest: /tmp/sc2_manifest.txt")

def _stats(frames: list[bytes], L: int) -> tuple[list[int], list[int], list[int]]:
    mn = [255] * L; mx = [0] * L; mode = [0] * L
    for i in range(L):
        cnt = {}
        for f in frames:
            b = f[i]
            if b < mn[i]: mn[i] = b
            if b > mx[i]: mx[i] = b
            cnt[b] = cnt.get(b, 0) + 1
        mode[i] = max(cnt, key=cnt.get)
    return mn, mx, mode

def report() -> None:
    rest = load("rest")
    L = min(len(f) for f in rest)
    rmn, rmx, rmode = _stats(rest, L)
    sensor = {1} | {i for i in range(L) if rmx[i] - rmn[i] > 8}
    if os.path.exists("/tmp/sc2_imu.bin"):
        imu = load("imu")
        imn, imx, _ = _stats(imu, L)
        sensor |= {i for i in range(L) if imx[i] - imn[i] > 8}
    print(f"payload len={L}  sensor/motion offsets (masked): {sorted(sensor)}\n")
    labels = [l.strip() for l in open("/tmp/sc2_manifest.txt") if l.strip()]
    digital_map = {}   # (offset,bit) -> label
    for lab in labels:
        path = f"/tmp/sc2_{lab}.bin"
        if not os.path.exists(path):
            continue
        fr = load(lab)
        ctrl, motion = [], []
        for i in range(L):
            cmin = min(f[i] for f in fr); cmax = max(f[i] for f in fr)
            chbits = 0
            for f in fr:
                chbits |= (f[i] ^ rmode[i])
            if chbits == 0:
                continue
            if i in sensor:
                motion.append(i); continue
            rng = cmax - cmin
            if rng > 32:
                ctrl.append(f"off{i} ANALOG {cmin}..{cmax} (rest={rmode[i]})")
            else:
                ctrl.append(f"off{i} bit=0x{chbits:02x} ({rmode[i]:#04x}->{rmode[i]|chbits:#04x})")
                for b in range(8):
                    if chbits & (1 << b):
                        digital_map[(i, 1 << b)] = lab
        tag = "  ".join(ctrl) if ctrl else "(no control-region change)"
        extra = f"   [+motion {motion}]" if motion else ""
        print(f"== {lab:14s} {tag}{extra}")
    print("\n=== consolidated digital button bitfield (offset, bit) ===")
    for (off, bit) in sorted(digital_map):
        print(f"  off{off:2d}  bit 0x{bit:02x}  = {digital_map[(off, bit)]}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "guided":
        guided()
    elif cmd == "grips":
        grips()
    elif cmd == "report":
        report()
    elif cmd == "rec":
        rec(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 5.0)
    elif cmd == "diff":
        diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
