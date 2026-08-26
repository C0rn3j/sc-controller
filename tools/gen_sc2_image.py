"""Generate the v2 (Steam Controller 2026) GUI assets from traced source SVGs.

Sources (in tools/):
  sc2-source.svg          -- controller artwork (Inkscape layer g1)
  sc2-assets/scnovo-grips-fim.svg -- two grip-touch surface overlays (g6,g7)

Outputs:
  images/controller-images/sc2.svg   -- background image
  images/button-images/sc2_*.svg     -- face-button overlay glyphs (8)
  images/sc2/<NAME>.svg              -- side-panel icons
and prints the gui.buttons list for images/sc2-config.json.

Notes:
  * _fill_button_images REPLACES the placed glyph's `transform`, so a glyph's
    normalisation transform must live on an INNER group (the `button` group is
    overwritten). Content is pre-scaled to display size and placed at scale 1.
  * Side-panel icons render at their SVG width/height; source-coord sizes are
    huge, so each is shrunk by a per-control factor.
  * Hover highlight recolours the element whose id == control name; the kept
    controls and the grip-touch overlays carry those ids.

Run from repo root:  python -m tools.gen_sc2_image
"""

import os
import xml.etree.ElementTree as ET

from . import _svgo, _svgpath

SVG = "http://www.w3.org/2000/svg"
INK = "http://www.inkscape.org/namespaces/inkscape"
SRC = "tools/sc2-source.svg"
GRIPS = "tools/sc2-assets/scnovo-grips-fim.svg"
OUT_IMG = "images/controller-images/sc2.svg"
OUT_DEBUG = "/tmp/sc2-debug.svg"
GLYPH_DIR = "images/button-images"
PANEL_DIR = "images/sc2"

SCALE = 0.5
#VB_W, VB_H = 1370.9014, 986.0376
source_root = ET.parse(SRC).getroot()
_vbx, _vby, VB_W, VB_H = map(float, source_root.get("viewBox").split())
W, H = VB_W * SCALE, VB_H * SCALE
G1TX, G1TY = -33.923347, -23.468467

# TODO(Martin): Just manually recalculate REGION and unscrew scnovo svg and remove the OLD_G1TY and offset hacks
OLD_G1TY = -55.346467
region_y_offset = G1TY - OLD_G1TY

BODY_FILL = "#b8b8b8"
SYMBOL_FILL = "#000000"
GRIP_SHIFT_X = 2.0  # source units (~1px at display scale) nudge right, for a neat fit

KEEP = {
	"dpad": "DPAD",
	"lstick": "LSTICK",
	"rstick": "RSTICK",
	"lpad": "LPAD",
	"rpad": "RPAD",
	"lb": "LB",
	"rb": "RB",
	"LT": "LT",
	"RT": "RT",
	"steamcontrollerbody": "BODY",
	"LSTICKPRESS": "LSTICKPRESS",
	"LSTICKTOUCH": "LSTICKTOUCH",
	"RSTICKPRESS": "RSTICKPRESS",
	"RSTICKTOUCH": "RSTICKTOUCH",
	"LGRIP": "LGRIP",
	"RGRIP": "RGRIP",
	"LGRIP2": "LGRIP2",
	"RGRIP2": "RGRIP2",
}
FACE = {"abxy": None, "steam": "C", "view": "BACK", "menu": "START", "dots": "DOTS"}

# side-panel icon shrink factors (icons render at source-coord size otherwise)
PANEL_FACTOR = {
	"LSTICK": 2.5,
	"RSTICK": 2.5,
	"LPAD": 3.0,
	"RPAD": 3.0,
	"DPAD": 2.5,
	"BACK": 2.5,
	"START": 2.5,
	"C": 2.5,
	"DOTS": 2.5,
}
# Rear-paddle panel icons are extracted from these groups in sc2-source.svg.
PADDLE_ICON = ("LGRIP", "RGRIP", "LGRIP2", "RGRIP2")

ET.register_namespace("", SVG)


def clean(
	e: ET.Element,
	keep: tuple[str, ...] = (
		"id",
		"d",
		"style",
		"transform",
		"x",
		"y",
		"width",
		"height",
		"rx",
		"ry",
		"cx",
		"cy",
		"r",
	),
) -> ET.Element:
	"""Deep-copy an element keeping only safe attributes (drop inkscape/sodipodi)."""
	tag = e.tag.split("}")[-1]
	new = ET.Element(f"{{{SVG}}}{tag}", {k: v for k, v in e.attrib.items() if k in keep})
	# Preserve text/tspan content (the L4/R4/L5/R5 paddle labels).
	new.text = e.text
	new.tail = e.tail
	for ch in e:
		new.append(clean(ch, keep))
	return new


def src_elements() -> tuple[ET.Element, dict[str, ET.Element]]:
	root = ET.parse(SRC).getroot()
	g1 = next(e for e in root.iter() if e.get("id") == "g1")
	return g1, {
		(e.get(f"{{{INK}}}label") or e.get("id")): e
		for e in g1
		if e.get(f"{{{INK}}}label") or e.get("id")
	}


def abxy_split(abxy: ET.Element) -> dict[str, str]:
	absd = _svgpath.to_absolute(abxy.get("d"))
	subs = _svgpath.split_subpaths(absd)
	cc = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in (_svgpath.bbox(s) for s in subs)]
	ab = _svgpath.bbox(absd)
	ox, oy = (ab[0] + ab[2]) / 2, (ab[1] + ab[3]) / 2
	centers = {
		"Y": (ox, ab[1] + (ab[3] - ab[1]) * 0.18),
		"A": (ox, ab[1] + (ab[3] - ab[1]) * 0.82),
		"X": (ab[0] + (ab[2] - ab[0]) * 0.18, oy),
		"B": (ab[0] + (ab[2] - ab[0]) * 0.82, oy),
	}
	groups = {k: [] for k in centers}
	for s, (mx, my) in zip(subs, cc):
		groups[min(centers, key=lambda b: (centers[b][0] - mx) ** 2 + (centers[b][1] - my) ** 2)].append(s)
	return {k: " ".join(v) for k, v in groups.items()}


def local_to_display_bbox(lb: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
	return (lb[0] + G1TX) * SCALE, (lb[1] + G1TY) * SCALE, (lb[2] - lb[0]) * SCALE, (lb[3] - lb[1]) * SCALE


def write_glyph(path: str, local_d: str) -> tuple[float, float, float, float]:
	"""Overlay glyph: symbol pre-scaled to display size on an INNER group

	so the `button` group transform (overwritten by _fill_button_images) doesn't matter.
	Placed at its display AREA with scale 1, it reproduces the button exactly.
	"""
	lb = _svgpath.bbox(local_d)
	lx, ly, dw, dh = lb[0], lb[1], (lb[2] - lb[0]) * SCALE, (lb[3] - lb[1]) * SCALE
	svg = ET.Element(
		f"{{{SVG}}}svg",
		{"viewBox": f"0 0 {dw:g} {dh:g}", "width": f"{dw:g}", "height": f"{dh:g}"},
	)
	# load_from_file() returns the FIRST <g>; get_element then looks for id=button
	# among its DESCENDANTS. So `button` must be wrapped in an outer <g> (mirrors
	# the stock glyphs' layer > button > inner structure) or it isn't found.
	layer = ET.SubElement(svg, f"{{{SVG}}}g", {"id": "glyph"})
	btn = ET.SubElement(layer, f"{{{SVG}}}g", {"id": "button"})
	inner = ET.SubElement(
		btn, f"{{{SVG}}}g", {"transform": f"scale({SCALE:g}) translate({-lx:g},{-ly:g})"}
	)
	ET.SubElement(inner, f"{{{SVG}}}path", {"d": local_d, "style": f"fill:{SYMBOL_FILL}"})
	ET.ElementTree(svg).write(path, encoding="unicode", xml_declaration=True)
	return local_to_display_bbox(lb)


def write_panel_icon(path: str, d: str, style: str | None, factor: float) -> None:
	b = _svgpath.bbox(d)
	w, h = b[2] - b[0], b[3] - b[1]
	pad = 0.06 * max(w, h)
	vbw, vbh = w + 2 * pad, h + 2 * pad
	svg = ET.Element(
		f"{{{SVG}}}svg",
		{
			"viewBox": f"{b[0] - pad:g} {b[1] - pad:g} {vbw:g} {vbh:g}",
			"width": "%g" % (vbw / factor),
			"height": "%g" % (vbh / factor),
		},
	)
	ET.SubElement(svg, f"{{{SVG}}}path", {"d": d, "style": style or (f"fill:{SYMBOL_FILL}")})
	ET.ElementTree(svg).write(path, encoding="unicode", xml_declaration=True)


def write_paddle_panel_icon(path: str, name: str, group_elem: ET.Element) -> None:
	"""Write a visible standalone icon from a paddle group in sc2-source.svg."""
	circle = next((e for e in group_elem.iter() if e.tag.endswith("circle")), None)
	if circle is None:
		raise ValueError(f"Paddle group {name} has no circle")

	cx, cy, radius = (float(circle.get(key)) for key in ("cx", "cy", "r"))
	pad = radius * 0.08
	size = 2 * (radius + pad)
	svg = ET.Element(
		f"{{{SVG}}}svg",
		{
			"viewBox": f"{cx - radius - pad:g} {cy - radius - pad:g} {size:g} {size:g}",
			"width": "36",
			"height": "36",
		},
	)

	group = clean(group_elem)
	group.set("id", name)
	# Transforms place this group and its children on the controller.  The panel
	# icon's viewBox is already based on the source circle's local coordinates.
	# Keep the authored geometry, but discard those controller-space transforms.
	for element in group.iter():
		element.attrib.pop("transform", None)
		# The source objects are hidden until the controller image highlights them.
		# A standalone panel icon must show the same authored circle and label.
		if "style" not in element.attrib:
			continue
		style = {
			key: value
			for key, value in (
				item.split(":", 1) for item in element.attrib["style"].split(";") if ":" in item
			)
		}
		style["opacity"] = "1"
		element.set("style", ";".join(f"{key}:{value}" for key, value in style.items()))

	svg.append(group)
	ET.ElementTree(svg).write(path, encoding="unicode", xml_declaration=True)


def grips() -> dict[str, tuple[ET.Element, tuple[float, float, float, float]]]:
	"""Return {'LGRIPTOUCH': (group_elem, src_bbox), 'RGRIPTOUCH': (...)}"""
	import subprocess

	root = ET.parse(GRIPS).getroot()
	out = subprocess.run(["inkscape", "--query-all", GRIPS], capture_output=True, text=True).stdout
	bb = {p[0]: tuple(map(float, p[1:])) for p in (l.split(",") for l in out.splitlines()) if len(p) == 5}
	res = {}
	for gid, name in (("g6", "LGRIPTOUCH"), ("g7", "RGRIPTOUCH")):
		g = next(e for e in root.iter() if e.get("id") == gid)
		el = clean(g)
		el.set("id", name)
		res[name] = (el, bb[gid])
	return res


def write_grip_panel_icon(path: str, group_elem: ET.Element, src_bbox: tuple[float, float, float, float]) -> None:
	x, y, w, h = src_bbox
	f = max(w, h) / 98.0  # height ~2x the other panel icons (tall thin shape)
	# width stretched 2x more (the silhouette is too narrow otherwise);
	# preserveAspectRatio=none makes the content actually fill the wider box
	# instead of being letter-boxed/padded.
	# src_bbox comes from the grips file where g6/g7 sit inside g1
	# (translate(-33.9,-55.3)); here the group is rendered WITHOUT that g1
	# translate, so shift the viewBox by -g1 to keep the drawing inside it.
	svg = ET.Element(
		f"{{{SVG}}}svg",
		{
			"viewBox": f"{x - G1TX:g} {y - G1TY:g} {w:g} {h:g}",
			"preserveAspectRatio": "none",
			"width": "%g" % (2 * w / f),
			"height": "%g" % (h / f),
		},
	)
	g = clean(group_elem)
	for p in g.iter(f"{{{SVG}}}path"):
		p.set("style", "fill:#666666;stroke:#1a1a1a;stroke-width:4")
	svg.append(g)
	ET.ElementTree(svg).write(path, encoding="unicode", xml_declaration=True)


def main() -> None:
	g1, lab = src_elements()
	os.makedirs(PANEL_DIR, exist_ok=True)
	grip = grips()

	# ---- face overlay glyphs + display AREAs ----
	face_local = {}
	abxy = abxy_split(lab["abxy"])
	for k in ("A", "B", "X", "Y"):
		face_local[k] = abxy[k]
	for label, name in (("steam", "C"), ("view", "BACK"), ("menu", "START"), ("dots", "DOTS")):
		face_local[name] = _svgpath.to_absolute(lab[label].get("d"))
	face_area = {n: write_glyph(os.path.join(GLYPH_DIR, f"sc2_{n}.svg"), d) for n, d in face_local.items()}

	# ---- side-panel icons ----
	PANEL = {
		"LSTICK": "lstick",
		"RSTICK": "rstick",
		"LPAD": "lpad",
		"RPAD": "rpad",
		"DPAD": "dpad",
		"BACK": "view",
		"START": "menu",
		"C": "steam",
		"DOTS": "dots",
	}
	for name, label in PANEL.items():
		el = lab[label]
		write_panel_icon(
			os.path.join(PANEL_DIR, f"{name}.svg"), _svgpath.to_absolute(el.get("d")), el.get("style"), PANEL_FACTOR[name]
		)
	for name in PADDLE_ICON:
		write_paddle_panel_icon(os.path.join(PANEL_DIR, f"{name}.svg"), name, lab[name])
	for name in ("LGRIPTOUCH", "RGRIPTOUCH"):  # grip-touch panel icon = the surface
		write_grip_panel_icon(os.path.join(PANEL_DIR, f"{name}.svg"), *grip[name])

	# ---- controller image ----
	def build(debug: bool = False) -> ET.ElementTree:
		svg = ET.Element(
			f"{{{SVG}}}svg",
			{
				"width": f"{W:g}",
				"height": f"{H:g}",
				"viewBox": f"0 0 {W:g} {H:g}",
				"version": "1.1",
			},
		)
		_ = ET.SubElement(svg, f"{{{SVG}}}defs", {"id": "defs1"})
		scaler = ET.SubElement(svg, f"{{{SVG}}}g", {"id": "scaler", "transform": f"scale({SCALE:g})"})
		art = ET.SubElement(scaler, f"{{{SVG}}}g", {"id": "art", "transform": g1.get("transform", "")})
		overlays = {
			"LSTICKPRESS",
			"LSTICKTOUCH",
			"RSTICKPRESS",
			"RSTICKTOUCH",
			"LGRIP",
			"RGRIP",
			"LGRIP2",
			"RGRIP2",
		}

		def append_source_element(label: str, element: ET.Element) -> None:
			copied = clean(element)
			copied.set("id", KEEP[label])
			if label == "steamcontrollerbody":
				copied.set("style", copied.get("style", "").replace("#c8c8c8", BODY_FILL))
			art.append(copied)

		# Draw the base controller first. Stick indicators and rear paddles are
		# deferred until after the grip-touch surfaces so they remain visible.
		for label, element in lab.items():
			if label in FACE or label not in KEEP or label in overlays:
				continue
			append_source_element(label, element)
		# grip-touch surfaces (overlay the handles; recolor green on hover).
		# In the source grips file g6/g7 live INSIDE g1 (translate -33.9,-55.3),
		# so they must go in `art` (same transform) or they shift down-right.
		for name in ("LGRIPTOUCH", "RGRIPTOUCH"):
			element = clean(grip[name][0])
			element.set("transform", "translate({:g},0) {}".format(GRIP_SHIFT_X, element.get("transform", "")))
			if debug:
				for p in element.iter(f"{{{SVG}}}path"):
					p.set("style", "fill:#00ff00;fill-opacity:.45")
			art.append(element)

		# Draw interactive overlays last, above the grip-touch surfaces.
		for label, element in lab.items():
			if label in overlays:
				append_source_element(label, element)

		_ = ET.SubElement(svg, f"{{{SVG}}}g", {"id": "controller"})

		areas = ET.SubElement(
			svg, f"{{{SVG}}}g", {"id": "layerAreas", "style": "display:inline" if debug else "display:none"}
		)

		def add_area(name: str, x: float, y: float, w: float, h: float) -> None:
			style = "fill:none;stroke:#ff0000;stroke-width:1" if debug else "fill:none;stroke:none"
			_ = ET.SubElement(
				areas,
				f"{{{SVG}}}rect",
				{
					"id": f"AREA_{name}",
					"x": f"{x:g}",
					"y": f"{y:g}",
					"width": f"{w:g}",
					"height": f"{h:g}",
					"style": style,
				},
			)

		for name, bb in face_area.items():
			add_area(name, *bb)
		REGION = {
			"LB": (173.9, 6.5, 203.9, 68.2),
			"RB": (999.5, 6.3, 204.2, 68.5),
			"LSTICK": (386.3, 222.0, 194.3, 196.2),
			"RSTICK": (795.8, 221.4, 195.7, 196.8),
			"LPAD": (263.1, 423.0, 314.5, 321.4),
			"RPAD": (798.6, 423.5, 313.6, 322.0),
			"DPAD": (145.7, 100.5, 219.7, 221.8),
			"LT": (170.2, -23.6, 146.2, 57.6),
			"RT": (1061.6, -23.6, 146.2, 57.6),
		}
		for name, (x, y, w, h) in REGION.items():
			add_area(name, x * SCALE, (y + region_y_offset) * SCALE, w * SCALE, h * SCALE)
		for name in ("LGRIPTOUCH", "RGRIPTOUCH"):  # AREA == grip surface bbox (+nudge)
			x, y, w, h = grip[name][1]
			add_area(name, (x + GRIP_SHIFT_X) * SCALE, (y + region_y_offset) * SCALE, w * SCALE, h * SCALE)
		for name, k in (
			("LPADTEST", "LPAD"),
			("RPADTEST", "RPAD"),
			("LSTICKTEST", "LSTICK"),
			("RSTICKTEST", "RSTICK"),
			("DPADTEST", "DPAD"),
		):
			x, y, w, h = REGION[k]
			add_area(name, x * SCALE, (y + region_y_offset) * SCALE, w * SCALE, h * SCALE)
		return ET.ElementTree(svg)

	build(False).write(OUT_IMG, encoding="unicode", xml_declaration=True)
	build(True).write(OUT_DEBUG, encoding="unicode", xml_declaration=True)

	# minify the committed outputs (the /tmp debug image is left readable)
	panel_names = list(PANEL) + list(PADDLE_ICON) + ["LGRIPTOUCH", "RGRIPTOUCH"]
	outputs = [OUT_IMG]
	outputs += [os.path.join(GLYPH_DIR, f"sc2_{n}.svg") for n in face_local]
	outputs += [os.path.join(PANEL_DIR, f"{n}.svg") for n in panel_names]
	_svgo.optimize(*outputs)

	gui = [
		"sc2_A",
		"sc2_B",
		"sc2_X",
		"sc2_Y",
		"sc2_BACK",
		"sc2_C",
		"sc2_START",
		"LB",
		"RB",
		"LT",
		"RT",
		"LSTICK",
		"TOUCHPAD",
		"TOUCHPAD",
		"RGRIP",
		"LGRIP",
		"sc2_DOTS",
	]
	print("wrote", OUT_IMG, "+ 8 glyphs +", len(os.listdir(PANEL_DIR)), "panel icons")
	print("gui.buttons =", gui)


if __name__ == "__main__":
	main()
