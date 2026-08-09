import json
from pathlib import Path
from xml.etree import ElementTree

RIGHT_STICK_CONTROLLERS = ("ds4", "ds5", "x360", "remotepad")


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
