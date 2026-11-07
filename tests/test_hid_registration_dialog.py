from types import SimpleNamespace

import pytest

from scc.constants import SCButtons
from scc.gui.creg import dialog
from scc.gui.creg.constants import AXIS_ORDER
from scc.gui.creg.data import AxisData


@pytest.mark.parametrize("area,button", [("LSTICK", SCButtons.LSTICKPRESS), ("RSTICK", SCButtons.RSTICKPRESS), ("DPAD", None)])
def test_registration_stick_press_mapping(monkeypatch, area, button):
	registration = object.__new__(dialog.ControllerRegistration)
	registration._axis_data = [AxisData(name, xy) for name, xy in AXIS_ORDER]
	page = object()
	stack = SimpleNamespace(observe_children=lambda: [object(), object(), page], get_visible_child=lambda: page)
	menu = SimpleNamespace()
	image = SimpleNamespace(_click_position=(123.0, 456.0))
	popups = []
	registration.app = SimpleNamespace(_popup_at=lambda *args: popups.append(args))
	sensitivity = []
	widgets = {"stDialog": stack, "mnuStick": menu, "mnuStickPress": SimpleNamespace(set_sensitive=sensitivity.append)}
	registration.builder = SimpleNamespace(get_object=widgets.get)
	grabbed = []
	monkeypatch.setattr(dialog, "InputGrabber", lambda parent, what, **kwargs: grabbed.append(what))
	registration.on_area_click(image, area)
	assert popups == [(menu, image, 123.0, 456.0)]
	registration.on_mnuStickPress_activate()
	assert sensitivity == [button is not None]
	assert grabbed == ([] if button is None else [button])
	# Reopening the menu must restore the press option for a stick.
	registration.on_area_click(image, "LSTICK")
	assert sensitivity[-1] is True
