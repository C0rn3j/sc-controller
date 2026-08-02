"""Optimise generated SVGs with svgo so the committed output stays small.

svgo is optional: when it is not on PATH the generators still work and just emit
un-minified SVGs (with a note). The config (tools/svgo.config.js) keeps the ids,
<rect> geometry, viewBox and display:none layers the GUI relies on.
"""
import shutil
import subprocess
import sys

CONFIG = "tools/svgo.config.js"


def optimize(*paths: str) -> None:
	"""Run svgo in place over paths; no-op with a note if svgo is missing."""
	svgo = shutil.which("svgo")
	if not svgo:
		print(f"note: svgo not on PATH; {len(paths)} generated SVG(s) left un-minified")
		return
	try:
		_ = subprocess.run(
			[svgo, "--config", CONFIG, *paths],
			check=True,
			capture_output=True,
			text=True,
		)
	except subprocess.CalledProcessError as exc:
		print(exc.stdout, end="")
		print(exc.stderr, end="", file=sys.stderr)
		raise
	print(f"svgo: optimised {len(paths)} SVG(s)")
