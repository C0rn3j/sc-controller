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
	menu = SimpleNamespace(popup=lambda: None)
	sensitivity = []
	widgets = {"stDialog": stack, "mnuStick": menu, "mnuStickPress": SimpleNamespace(set_sensitive=sensitivity.append)}
	registration.builder = SimpleNamespace(get_object=widgets.get)
	grabbed = []
	monkeypatch.setattr(dialog, "InputGrabber", lambda parent, what, **kwargs: grabbed.append(what))
	registration.on_area_click(None, area)
	registration.on_mnuStickPress_activate()
	assert sensitivity == [button is not None]
	assert grabbed == ([] if button is None else [button])
	# Reopening the menu must restore the press option for a stick.
	registration.on_area_click(None, "LSTICK")
	assert sensitivity[-1] is True
