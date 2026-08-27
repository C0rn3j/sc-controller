import json
from pathlib import Path
from xml.etree import ElementTree

RIGHT_STICK_CONTROLLERS = ("ds4", "ds5", "x360", "remotepad")
CONTROLLER_IMAGES = Path("images/controller-images")


def test_right_stick_controller_metadata_uses_rstick() -> None:
	for name in RIGHT_STICK_CONTROLLERS:
		config_name = f"{name}-config.json"
		config = json.loads(Path("images", config_name).read_text())
		buttons = config["gui"]["buttons"]
		assert "RSTICK" in buttons
		assert "RPAD" not in buttons


def test_right_stick_controller_images_have_rstick_test_areas() -> None:
	for name in RIGHT_STICK_CONTROLLERS:
		root = ElementTree.parse(Path("images/controller-images", f"{name}.svg")).getroot()
		ids = {element.get("id") for element in root.iter()}
		assert "AREA_RSTICKTEST" in ids
		assert "AREA_RPADTEST" not in ids


def test_controller_test_areas_have_no_stroke() -> None:
	"""The code assumes the exact AREA_*TEST coordinates (XYWH) are the area borders.

	Inkscape assumes the size of the area is coords+stroke-width if stroke is not none.
	Make sure stroke is always none or missing, to not get bamboozled by Inkscape.
	"""
	failures = []
	for path in sorted(CONTROLLER_IMAGES.glob("*.svg")):
		# Controller asset names are identifiers; ignore local backup copies.
		if not path.stem.isidentifier():
			continue
		root = ElementTree.parse(path).getroot()
		for element in root.iter():
			element_id = element.get("id", "")
			if not (element_id.startswith("AREA_") and element_id.endswith("TEST")):
				continue

			style = dict(
				part.split(":", 1)
				for part in element.get("style", "").split(";")
				if ":" in part
			)
			stroke = element.get("stroke", style.get("stroke"))
			if stroke != "none":
				failures.append(f"{path}: {element_id} has stroke {stroke or '<missing>'}")

	assert not failures, "Test areas with painted strokes:\n" + "\n".join(failures)
