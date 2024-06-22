#!/usr/bin/env python3
# Used to generate some icons
# Requires inkscape and imagemagick packages
import subprocess
import colorsys
import oxipng
from xml.etree import ElementTree as ET

ICODIR = "./images/"                  # Directory with icons
CICONS = "./images/controller-icons/" # Directory controller-icons
RECOLORS = {
	# Defines set of hue shifts for controller-icons
	# "0" : 0.0,	# Green - original
	"1" : 0.3,		# Blue
	"2" : 0.7,		# Red
	"3" : 0.9,		# Yellow
	"4" : 0.2,		# Cyan
	"5" : 0.8,		# Orange
	"6" : 0.5,		# Purple
}


# Generate svg state icons
for size in (24, 256):
	for state in ('alive', 'dead', 'error', 'unknown'):
		print(f"scc-statusicon-{state}.png")
		subprocess.call([
			"inkscape",
			f"{ICODIR}scc-statusicon-{state}.svg",
			"--export-area-page",
			f"--export-filename={ICODIR}{size}x{size}/status/scc-{state}.png",
			f"--export-width={size}",
			f"--export-height={size}"])
		oxipng.optimize(f"{ICODIR}{size}x{size}/status/scc-{state}.png", level=6, deflate=oxipng.Deflaters.zopfli(100))

def html_to_rgb(html: str) -> tuple[int,int,int,int]:
	""" Converts #rrggbbaa or #rrggbb to r, g, b,a in (0,1) ranges """
	html = html.strip("#")
	if len(html) == 6:
		html = html + "ff"
	elif html == "none":
		return 0, 0, 0, 0
	elif len(html) != 8:
		raise ValueError("Needs RRGGBB(AA) format, got '%s'" % (html, ))
	return tuple(( float(int(html[i:i+2],16)) / 255.0 for i in range(0, len(html), 2) ))


def rgb_to_html(r,g,b) -> str:
	""" Convets rgb back to html color code """
	return "#" + "".join(( "%02x" % int(x * 255) for x in (r,g,b) ))


def recolor(tree, add) -> None:
	""" Recursive part of recolor_strokes and recolor_background """
	if 'id' in tree.attrib and "overlay" in tree.attrib['id']:
		return
	for child in tree:
		if 'style' in child.attrib:
			styles = { a : b
				for (a, b) in (
					x.split(":", 1)
					for x in child.attrib['style'].split(';')
					if ":" in x
				)}
			if "fill" in styles or "stroke" in styles:
				for key in ("fill", "stroke"):
					if key in styles:
						# Convert color to HSV
						r,g,b,a = html_to_rgb(styles[key])
						h,s,v = colorsys.rgb_to_hsv(r,g,b)
						# Shift hue
						h += add
						while h > 1.0:
							h -= 1.0
						# Convert it back
						r,g,b = colorsys.hsv_to_rgb(h,s,v)
						# Store
						styles[key] = rgb_to_html(r,g,b)
				child.attrib["style"] = ";".join(( ":".join((x,styles[x])) for x in styles ))
		recolor(child, add)

# Generate different colors for controller icons
ET.register_namespace("","http://www.w3.org/2000/svg")
for tp in ("sc", "scbt", "fake", "ds4", "hid", "rpad"):
	# Read svg and parse it
	data = open(f"{CICONS}{tp}-0.svg", "r").read()
	# Create recolored images
	for key in RECOLORS:
		tree = ET.fromstring(data)
		# Walk recursively and recolor everything that has color
		recolor(tree, RECOLORS[key])

		out = f"{CICONS}{tp}-{key}.svg"
		with open(out, "w") as file:
			file.write(ET.tostring(tree).decode('utf-8'))
		subprocess.call([
			"svgo",
			"--multipass",
			f"--input={out}"])
		print(out)
