"""ae - Action Editor components"""

import logging
import os

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from scc.actions import Action, NoAction, XYAction
from scc.constants import SCButtons
from scc.gui.editor import ComboSetter
from scc.tools import _, ensure_size

log = logging.getLogger("AE")

# Rear-paddle display names. On controllers whose four rear paddles are
# physically labeled L4/L5/R4/R5 (Steam Controller 2, Steam Deck) the generic
# "Left Grip (2)" naming is confusing -- especially on the SC2, where "grip"
# reads as the capacitive handle sensor instead. The Steam Controller v1's
# LGRIP/RGRIP are its squeeze grips and keep the "Left/Right Grip" naming.
PADDLE_TYPES = ("sc2", "deck")
PADDLE_NAMES = {
	SCButtons.LGRIP: "L4",
	SCButtons.RGRIP: "R4",
	SCButtons.LGRIP2: "L5",
	SCButtons.RGRIP2: "R5",
}


def button_label(app, button, default):
	"""Per-controller display name for a button: the rear paddles are
	L4/L5/R4/R5 on paddle controllers (sc2/deck), the default (grip) name
	elsewhere. `app` may be None (falls back to the default label)."""
	ctype = None
	try:
		c = app.profile_switchers[0].get_controller() if app else None
		ctype = c.get_type() if c else None
	except Exception:
		pass
	if ctype in PADDLE_TYPES and button in PADDLE_NAMES:
		return PADDLE_NAMES[button]
	return default


# Buttons that only SOME controllers have and whose presence is reliably
# recorded in the controller's gui config "buttons" capability list (sc2 and
# deck ship configs; everything else falls back to DEFAULT_BUTTONS, which
# correctly lacks these). Only these are ever filtered out of button lists --
# filtering arbitrary buttons against the capability list would wrongly hide
# valid entries on configless controllers (e.g. the DS4's stick presses).
OPTIONAL_BUTTONS = {
	SCButtons.LGRIP2, SCButtons.RGRIP2,
	SCButtons.LGRIPTOUCH, SCButtons.RGRIPTOUCH,
	SCButtons.LSTICKTOUCH, SCButtons.RSTICKTOUCH,
}


def button_available(app, button) -> bool:
	"""True unless `button` is an optional extra (OPTIONAL_BUTTONS) that the
	currently displayed controller's capability list does not include."""
	if button not in OPTIONAL_BUTTONS:
		return True
	try:
		available = app.background.get_config()["buttons"] if app else None
	except Exception:
		available = None
	if not available:
		return True
	from scc.tools import nameof
	return nameof(button) in available


class AEComponent(ComboSetter):
	GLADE = None
	NAME = None
	PRIORITY = 0
	# Bit mask of contexes (Action.AC_BUTTON | Action.AC_TRIGGER...) that this
	# compoment can handle.
	CTXS = 0

	def __init__(self, app, editor):
		self.app = app
		self.editor = editor
		self.loaded = False

	def get_button_title(self):
		raise Exception("Implement me!")

	# TODO: Rename this to on_shown
	def shown(self):
		"""Called after user switches TO page"""

	# TODO: Rename this to on_shown
	def hidden(self):
		"""Called after user switches AWAY from page"""

	def on_ok(self, action):
		"""Called when user presses OK, after action is send to main window
		"""

	def load(self):
		"""Performs whatever component needs to get loaded.
		Can be called multiple times without breaking anything, but returns
		True when called first time and then False every to signalize repeated
		call.
		"""
		if self.loaded:
			return False
		self.builder = Gtk.Builder()
		self.builder.add_from_file(os.path.join(self.app.gladepath, self.GLADE))
		self.widget = self.builder.get_object(self.NAME)
		self.builder.connect_signals(self)
		self.loaded = True
		return True

	def is_loaded(self):
		return self.loaded

	def handles(self, mode, action):
		"""Returns True if component can display and edit specified action.
		If more than one component returns True from 'handles',
		higher PRIORITY is used
		"""
		return False

	def set_action(self, mode, action):
		"""Setups component widgets to display currently set action.
		"""

	def modifier_updated(self):
		"""Called when values of any modifier is changed.
		"""

	def get_widget(self):
		return self.widget


def describe_action(mode, cls, v):
	"""Returns action description with 'v' as parameter, unless unless v is None.
	Returns "not set" if v is None
	"""
	if v is None or type(v) in (
		int,
		float,
		str,
	):
		return _("(not set)")
	if isinstance(v, Action):
		if not mode:
			dsc = v.describe(Action.AC_STICK if cls == XYAction else Action.AC_BUTTON)
		else:
			dsc = v.describe(mode)

		if "\n" in dsc:
			dsc = "<small>" + "\n".join(dsc.split("\n")[0:2]) + "</small>"
		return dsc
	return (cls(v)).describe(mode)
