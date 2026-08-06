#!/usr/bin/env python3
"""Generate the per-controller binding-display templates from controller art.

The OSD "Display Current Bindings" window (scc/osd/binding_display.py) draws each
control's binding into boxes laid out around a controller picture, using a
per-controller template SVG. This tool builds those templates -- one per entry
in CONTROLLERS -- straight from the existing controller drawings
(images/controller-images/<key>.svg), so there is no hand-drawn per-controller
art to maintain: change a controller image and rerun this.

For each controller it emits images/binding-display/<key>.svg, containing all the
elements Generator needs:
  - a 1280x720 canvas with `background` (sizes the layout + dark backdrop),
    `label_template` (label font/metrics) and `root` (boxes are drawn into it);
  - the controller drawing, scaled + centred into the canvas and recoloured into
    the "Matrix" binding-display palette (green outlines + two greys) so it reads
    as a subdued filled silhouette behind the bright binding boxes/labels;
  - the six `markers_<box>` groups (system/lshoulder/rshoulder/lthumb/rthumb/
    face -- the box set in binding_display.py LAYOUTS[<key>]), each a ring at the
    matching AREA_* anchor centre of the source drawing, mapped into canvas
    coords. Each box draws a connector line to up to two of them.

The AREA_* anchors live in an untransformed layer of the source drawing in its
own coords; the same drawing->canvas transform places both the drawing and the
markers, so they always register regardless of the source viewBox (sc2.svg has a
non-zero origin). If you change ART_MAX_*_FRAC, both move together.

Run from repo root:  python3 tools/gen_binding_display.py
"""
import copy
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _svgo  # noqa: E402

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)

CANVAS_W, CANVAS_H = 1280, 720
OUT_DIR = "images/binding-display"

# The controller drawing's footprint in the canvas (leaves the margins free for
# the binding boxes). Both the drawing and its AREA-anchor markers are placed
# through this, so they stay registered.
ART_MAX_W_FRAC = 0.38
ART_MAX_H_FRAC = 0.70

# "Matrix" binding-display palette: the GUI controller art is full-colour, but
# here it is flattened to green outlines over two greys on a dark backdrop, so it
# recedes behind the bright binding boxes and labels while staying readable.
GREEN = "#047100"        # every outline/stroke -> this green
GRAY_LIGHT = "#3d3d3d"   # lighter fills (luminance >= GRAY_SPLIT)
GRAY_DARK = "#262626"    # darker fills, and the default for un-filled shapes
GRAY_SPLIT = 80          # fill luminance split between GRAY_LIGHT and GRAY_DARK
MARKER_GREEN = "#06a400"  # marker rings + connector lines (matches Generator)

# Standard gamepads (ds4, ds5, x360) share one anchor set: left stick + d-pad
# (LPAD) on the left, right stick (RPAD) on the right, the ABXY face cluster, and
# the top bumpers/triggers. Their drawings use the same AREA_* names.
_GAMEPAD_MARKERS = {
    "system": ["BACK", "START"], "lshoulder": ["LB_1", "LT_1"],
    "rshoulder": ["RB_4", "RT_1"], "lthumb": ["STICK_1", "LPAD_1"],
    "rthumb": ["RPAD_1"], "face": ["Y", "A"],
}

# Per-controller source drawing + the AREA_* anchors each binding box points at.
# The box names match scc/osd/binding_display.py LAYOUTS[<key>]. A box draws at
# most two connector lines; anchor names differ per controller image.
CONTROLLERS = {
    "sc2": {
        "src": "images/controller-images/sc2.svg",
        "markers": {
            "system": ["BACK", "START"], "lshoulder": ["LB", "LGRIPTOUCH"],
            "rshoulder": ["RB", "RGRIPTOUCH"], "lthumb": ["STICK", "LPAD"],
            "rthumb": ["RSTICK", "RPAD"], "face": ["Y", "A"],
        },
    },
    "deck": {
        "src": "images/controller-images/deck.svg",
        # Deck AREA naming differs (segmented pads/bumpers, no grip-touch).
        "markers": {
            "system": ["BACK", "START"], "lshoulder": ["LB_2", "LT_2"],
            "rshoulder": ["RB_2", "RT_2"], "lthumb": ["STICK", "LPAD_1"],
            "rthumb": ["RSTICK", "RPAD_1"], "face": ["Y", "A"],
        },
    },
    "ds4": {"src": "images/controller-images/ds4.svg", "markers": _GAMEPAD_MARKERS},
    "ds5": {"src": "images/controller-images/ds5.svg", "markers": _GAMEPAD_MARKERS},
    "x360": {"src": "images/controller-images/x360.svg", "markers": _GAMEPAD_MARKERS},
}

_FILL = re.compile(r"fill:\s*#([0-9a-fA-F]{3,6})")
_STROKE = re.compile(r"stroke:\s*#([0-9a-fA-F]{3,6})")


def q(tag: str) -> str:
    return "{%s}%s" % (SVG, tag)


def parse_viewbox(svg: ET.Element) -> tuple[float, float, float, float]:
    """(x, y, w, h) of the source viewBox -- x/y may be non-zero (e.g. sc2.svg)."""
    vb = svg.get("viewBox")
    if vb:
        p = [float(x) for x in vb.replace(",", " ").split()]
        return p[0], p[1], p[2], p[3]
    return 0.0, 0.0, float(svg.get("width")), float(svg.get("height"))


# --- affine transforms (a, b, c, d, e, f) mapping (x,y) -> (ax+cy+e, bx+dy+f) ---
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_TRANSFORM = re.compile(r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)")


def _compose(a: tuple, b: tuple) -> tuple:
    """Return a after b (apply b first, then a) -- SVG's nested-transform order."""
    a1, b1, c1, d1, e1, f1 = a
    a2, b2, c2, d2, e2, f2 = b
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _parse_transform(s: str | None) -> tuple:
    """Parse an SVG transform attribute into one composed affine matrix. Handles
    space- OR comma-separated args and a list of transforms (leftmost outermost)."""
    m = IDENTITY
    if not s:
        return m
    for name, argstr in _TRANSFORM.findall(s):
        v = [float(x) for x in re.split(r"[\s,]+", argstr.strip()) if x]
        if name == "translate":
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            t = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif name == "matrix":
            t = tuple(v[:6])
        elif name == "rotate":
            rad = math.radians(v[0])
            cos, sin = math.cos(rad), math.sin(rad)
            t = (cos, sin, -sin, cos, 0.0, 0.0)
            if len(v) >= 3:  # rotate about (cx, cy)
                t = _compose(_compose((1.0, 0.0, 0.0, 1.0, v[1], v[2]), t),
                             (1.0, 0.0, 0.0, 1.0, -v[1], -v[2]))
        else:
            t = IDENTITY
        m = _compose(m, t)
    return m


def read_area_centers(root: ET.Element) -> dict[str, tuple[float, float]]:
    """Centre of each AREA_<NAME> rect in the drawing's user (viewBox) space.

    The rects may sit inside groups with their own transforms (the Deck nests
    them under translated groups in a separate layer), so the full ancestor
    transform chain is accumulated -- reading raw x/y put the Deck's shoulder
    anchors hundreds of units outside the viewBox. sc2's anchors are in an
    identity layer, so its result is unchanged."""
    centers = {}

    def walk(el: ET.Element, acc: tuple) -> None:
        acc = _compose(acc, _parse_transform(el.get("transform")))
        for child in el:
            rid = child.get("id") or ""
            if child.tag == q("rect") and rid.startswith("AREA_"):
                try:
                    x, y, w, h = (float(child.get(k)) for k in ("x", "y", "width", "height"))
                except (TypeError, ValueError):
                    continue
                a, b, c, d, e, f = acc
                cx, cy = x + w / 2.0, y + h / 2.0
                centers[rid[5:]] = (a * cx + c * cy + e, b * cx + d * cy + f)
            else:
                walk(child, acc)

    walk(root, IDENTITY)
    return centers


def _luminance(hexcolor: str) -> float:
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _gray(hexcolor: str) -> str:
    """Map a source fill to one of the two binding-display greys by luminance, so
    light body panels stay lighter than dark detailing."""
    return GRAY_LIGHT if _luminance(hexcolor) >= GRAY_SPLIT else GRAY_DARK


def recolor(el: ET.Element) -> None:
    """Recolour a drawing subtree into the Matrix palette in place: every stroke
    becomes GREEN, every explicit fill becomes one of the two greys. Shapes with
    no fill inherit the drawing group's GRAY_DARK default (so they read instead
    of falling back to SVG black); stroke-only outlines keep their fill:none."""
    style = el.get("style")
    if style:
        style = _FILL.sub(lambda m: "fill:" + _gray(m.group(1)), style)
        style = _STROKE.sub(lambda _m: "stroke:" + GREEN, style)
        el.set("style", style)
    if (el.get("fill") or "").startswith("#"):
        el.set("fill", _gray(el.get("fill")))
    if (el.get("stroke") or "").startswith("#"):
        el.set("stroke", GREEN)
    for child in el:
        recolor(child)


def strip_areas(el: ET.Element) -> None:
    """Remove AREA_* hotspot rects recursively -- they are invisible in the GUI
    but recolour() would give them a grey fill and cover the drawing."""
    for child in list(el):
        if (child.get("id") or "").startswith("AREA_"):
            el.remove(child)
        else:
            strip_areas(child)


def build(key: str, spec: dict) -> None:
    src_path = spec["src"]
    if not os.path.exists(src_path):
        raise SystemExit("run from repo root: %s not found" % src_path)
    src = ET.parse(src_path).getroot()
    vx, vy, cw, ch = parse_viewbox(src)
    centers = read_area_centers(src)

    # Scale + centre the drawing in the canvas.
    s = min(CANVAS_W * ART_MAX_W_FRAC / cw, CANVAS_H * ART_MAX_H_FRAC / ch)
    ox = (CANVAS_W - cw * s) / 2.0
    oy = (CANVAS_H - ch * s) / 2.0

    def to_canvas(pt: tuple[float, float]) -> tuple[float, float]:
        return ox + s * (pt[0] - vx), oy + s * (pt[1] - vy)

    out = ET.Element(q("svg"), {
        "width": str(CANVAS_W), "height": str(CANVAS_H),
        "viewBox": "0 0 %d %d" % (CANVAS_W, CANVAS_H), "version": "1.1"})
    ET.SubElement(out, q("defs"), {"id": "defs1"})

    # background: drives the Generator's layout (it reads width/height) and gives
    # the OSD a dark backdrop so the labels read.
    ET.SubElement(out, q("rect"), {
        "id": "background", "x": "0", "y": "0",
        "width": str(CANVAS_W), "height": str(CANVAS_H),
        "style": "fill:#000000;fill-opacity:0.85"})

    # The controller drawing, scaled into the canvas so it registers with the
    # markers, then recoloured. The group's GRAY_DARK default catches shapes with
    # no explicit fill (which would otherwise render SVG-black on the dark bg).
    g = ET.SubElement(out, q("g"), {
        "fill": GRAY_DARK,
        "transform": "translate(%g,%g) scale(%g) translate(%g,%g)" % (ox, oy, s, -vx, -vy)})
    for child in list(src):
        if child.get("id") == "layerAreas":
            continue
        g.append(copy.deepcopy(child))
    strip_areas(g)
    recolor(g)

    # foreground: label_template + root (boxes drawn here) + the marker groups.
    root = ET.SubElement(out, q("g"), {"id": "root", "style": "display:inline"})
    lt = ET.SubElement(root, q("text"), {
        "id": "label_template",
        "style": "font-size:22px;font-family:'Ubuntu Mono';fill:#ffffff",
        "width": "11", "height": "15", "x": "-100", "y": "-100"})
    lt.text = "X"

    missing = []
    for name, anchors in spec["markers"].items():
        mg = ET.SubElement(root, q("g"), {"id": "markers_%s" % name})
        for a in anchors:
            if a not in centers:
                missing.append(a)
                continue
            cx, cy = to_canvas(centers[a])
            ET.SubElement(mg, q("circle"), {
                "cx": "%g" % cx, "cy": "%g" % cy, "r": "5",
                "style": "fill:none;stroke:%s;stroke-width:1" % MARKER_GREEN})

    out_path = os.path.join(OUT_DIR, "%s.svg" % key)
    ET.ElementTree(out).write(out_path, encoding="unicode", xml_declaration=True)
    _svgo.optimize(out_path)
    print("wrote %s  (from %s, scale %.3f at %.1f,%.1f)" % (out_path, src_path, s, ox, oy))
    if missing:
        print("  WARNING: AREA anchors not found in %s: %s" % (src_path, ", ".join(missing)))


def main() -> None:
    """Build every controller's binding-display template into OUT_DIR."""
    os.makedirs(OUT_DIR, exist_ok=True)
    for key, spec in CONTROLLERS.items():
        build(key, spec)


if __name__ == "__main__":
    main()
