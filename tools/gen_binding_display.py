#!/usr/bin/env python3
"""Generate the binding-display layout SVG for the v2 Steam Controller.

The OSD "Display Current Bindings" window (scc/osd/binding_display.py) draws each
control's binding into boxes laid out around a controller picture, using a
per-controller template SVG (binding-display-<gui background>.svg). This tool
assembles that template for the v2 controller.

What it emits (images/binding-display-sc2.svg), all required by Generator:
  - a 1280x720 canvas with `background` (sizes the layout), `label_template`
    (label font/metrics) and `root` (boxes are drawn into it) elements;
  - the restyled controller drawing, inlined verbatim from the source asset
    tools/binding-display-sc2-art.svg (edit that in Inkscape to change the
    look -- it carries its own placement transform);
  - the six `markers_<box>` groups (system/lshoulder/rshoulder/lthumb/rthumb/
    face -- the v2 box set in binding_display.py LAYOUTS["sc2"]), each with
    circles placed at the matching AREA_* anchor centres of sc2.svg, mapped
    into canvas coordinates. Each box draws a connector line to up to two.

Markers come from the GUI image's (sc2.svg) AREA_* anchors -- they live in an
untransformed layer in final display coords, so their centres map into the
canvas via the ART_MAX_*_FRAC transform below. The art asset was placed to
register with that mapping; if you change ART_MAX_*_FRAC, re-place the art.

Run from repo root:  python3 tools/gen_binding_display.py
"""
import os
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
SRC = "images/controller-images/sc2.svg"          # AREA anchors for markers
ART = "tools/binding-display-sc2-art.svg"          # restyled controller drawing
OUT = "images/binding-display-sc2.svg"

CANVAS_W, CANVAS_H = 1280, 720

# Defines the controller's footprint in the canvas, i.e. the sc2.svg-coords ->
# canvas transform used to place the AREA-anchor markers. The art asset
# (tools/binding-display-sc2-art.svg) was drawn/placed to register with this.
ART_MAX_W_FRAC = 0.38
ART_MAX_H_FRAC = 0.70

# Generator box name -> AREA_* anchors its connector lines point at. A box draws
# at most two lines; missing anchors are skipped (so a box may get 1 or 2). These
# match the v2 (sc2) box set in scc/osd/binding_display.py LAYOUTS["sc2"].
MARKERS = {
    "system":    ["BACK", "START"],
    "lshoulder": ["LB", "LGRIPTOUCH"],
    "rshoulder": ["RB", "RGRIPTOUCH"],
    "lthumb":    ["STICK", "LPAD"],
    "rthumb":    ["RSTICK", "RPAD"],
    "face":      ["Y", "A"],
}

ET.register_namespace("", SVG)


def q(tag):
    return "{%s}%s" % (SVG, tag)


def parse_viewbox(svg):
    vb = svg.get("viewBox")
    if vb:
        p = [float(x) for x in vb.replace(",", " ").split()]
        return p[2], p[3]
    return float(svg.get("width")), float(svg.get("height"))


def read_area_centers(root):
    """AREA_<NAME> rects sit in an untransformed layer in display coords, so
    their centres are read directly."""
    centers = {}
    for rect in root.iter(q("rect")):
        rid = rect.get("id") or ""
        if rid.startswith("AREA_"):
            x, y = float(rect.get("x")), float(rect.get("y"))
            w, h = float(rect.get("width")), float(rect.get("height"))
            centers[rid[5:]] = (x + w / 2.0, y + h / 2.0)
    return centers


def main():
    if not os.path.exists(SRC):
        raise SystemExit("run from repo root: %s not found" % SRC)
    src = ET.parse(SRC).getroot()
    cw, ch = parse_viewbox(src)               # controller art size (685x493)
    centers = read_area_centers(src)

    # Scale + centre the art in the free middle band.
    s = min(CANVAS_W * ART_MAX_W_FRAC / cw, CANVAS_H * ART_MAX_H_FRAC / ch)
    ox = (CANVAS_W - cw * s) / 2.0
    oy = (CANVAS_H - ch * s) / 2.0

    def to_canvas(pt):
        return ox + s * pt[0], oy + s * pt[1]

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

    # controller art: the hand-restyled drawing, inlined verbatim from the source
    # asset (kept separate so this generator reproduces it and the look is edited
    # in Inkscape). It carries its own placement transform, made to register with
    # the AREA-anchor marker mapping above.
    if not os.path.exists(ART):
        raise SystemExit("%s not found" % ART)
    for child in list(ET.parse(ART).getroot()):
        if child.tag.split("}")[-1] == "defs":
            continue
        out.append(child)

    # foreground: label_template + root (boxes drawn here) + the marker groups.
    root = ET.SubElement(out, q("g"), {"id": "root", "style": "display:inline"})
    lt = ET.SubElement(root, q("text"), {
        "id": "label_template",
        "style": "font-size:22px;font-family:'Ubuntu Mono';fill:#ffffff",
        "width": "11", "height": "15", "x": "-100", "y": "-100"})
    lt.text = "X"

    missing = []
    for name, anchors in MARKERS.items():
        g = ET.SubElement(root, q("g"), {"id": "markers_%s" % name})
        for a in anchors:
            if a not in centers:
                missing.append(a)
                continue
            cx, cy = to_canvas(centers[a])
            ET.SubElement(g, q("circle"), {
                "cx": "%g" % cx, "cy": "%g" % cy, "r": "5",
                "style": "fill:#000000;fill-opacity:0;stroke:#06a400;stroke-width:1"})

    ET.ElementTree(out).write(OUT, encoding="unicode", xml_declaration=True)
    print("wrote", OUT)
    print("  art inlined from %s; marker mapping scale %.3f at (%.1f, %.1f)"
          % (ART, s, ox, oy))
    if missing:
        print("  WARNING: AREA anchors not found in %s: %s" % (SRC, ", ".join(missing)))


if __name__ == "__main__":
    main()
