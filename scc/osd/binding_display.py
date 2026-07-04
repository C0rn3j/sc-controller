"""SC Controller - OSD Launcher

Display launcher with phone-like keyboard that user can use to select
application (list is generated using xdg) and start it.

Reuses styles from OSD Menu and OSD Dialog
"""
from __future__ import annotations

import base64
import logging
import os
import re
import sys
from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING, Self

from gi.repository import Gtk

from scc.actions import Action, AxisAction, DPadAction, MouseAction, MultiAction, XYAction
from scc.config import Config
from scc.constants import DPAD, LEFT, RIGHT, SCButtons
from scc.gui.daemon_manager import ControllerManager, DaemonManager
from scc.gui.svg_widget import SVGEditor, SVGWidget
from scc.modifiers import DoubleclickModifier, ModeModifier
from scc.osd import OSDWindow
from scc.parser import TalkingActionParser
from scc.paths import get_config_path, get_share_path
from scc.profile import Profile
from scc.special_actions import MenuAction
from scc.tools import _, nameof
from scc.uinput import Rels

if TYPE_CHECKING:
	from xml.etree import ElementTree as ET

log = logging.getLogger("osd.binds")


class BindingDisplay(OSDWindow):
	def __init__(self, config=None):
		self.bdisplay = os.path.join(get_config_path(), "binding-display.svg")
		if not os.path.exists(self.bdisplay):
			# Prefer image in ~/.config/scc, but load default one as fallback
			self.bdisplay = os.path.join(get_share_path(), "images", "binding-display.svg")

		OSDWindow.__init__(self, "osd-keyboard")
		self.daemon = None
		self.config = config or Config()
		self.group = None
		self.limits = {}
		self.background = None
		self._layout_key = None   # gui "background" name -> per-controller LAYOUTS

		self._eh_ids = []
		self._stick = 0, 0

		self.c = Gtk.Box()
		self.c.set_name("osd-keyboard-container")

	def on_profile_changed(self, daemon: DaemonManager, filename: str):
		self._draw_profile(filename)

	def _draw_profile(self, filename: str) -> None:
		"""(Re)draws the binding boxes for the given profile onto the current
		background. No-op until the background image has been built, which
		happens in on_daemon_connected() once the connected controller (and
		thus which per-controller image to load) is known.
		"""
		if self.background is None or not filename:
			return
		try:
			profile = Profile(TalkingActionParser()).load(filename)
		except Exception:
			log.exception("Failed to load profile %s", filename)
			return
		Generator(SVGEditor(self.background), profile, self._layout_key)

	def use_daemon(self, d):
		"""Allows (re)using already existing DaemonManager instance in same process."""
		self.daemon = d
		self._cononect_handlers()
		self.on_daemon_connected(self.daemon)

	def _add_arguments(self):
		OSDWindow._add_arguments(self)
		self.argparser.add_argument("image", type=str, nargs="?", default=self.bdisplay, help="keyboard image to use")
		self.argparser.add_argument(
			"--cancel-with", type=str, metavar="button", default="B", help="button used to close display (default: B)",
		)

	def compute_position(self):
		"""Fit the (per-controller) binding image to the active screen and centre
		it. Unlike other OSD windows this one is nearly screen-sized, so it is
		capped to 80% of the screen in BOTH dimensions and scaled down to fit."""
		iw, ih = self.background.image_width, self.background.image_height
		geometry = self.get_active_screen_geometry()
		if geometry is None:
			# The Steam Deck (gamescope) reports no active window; fall back to the
			# primary monitor so the image is still fitted instead of shown at full
			# 1280x720, which overflows the Deck's 1280x800 screen.
			screen = self.get_window().get_screen()
			geometry = screen.get_monitor_geometry(screen.get_primary_monitor())
		if geometry is None:
			return 10, 10
		# Cap to 80% of the screen in BOTH dimensions: width-only scaling left the
		# window overflowing on screens barely larger than the image (the Deck's
		# 1280x800 vs the 1280x720 image), and off-screen boxes made their
		# connector lines appear to shoot outside the window.
		scale = min(1.0, geometry.width * 0.8 / iw, geometry.height * 0.8 / ih)
		width, height = int(iw * scale), int(ih * scale)
		if scale < 1.0:
			self.background.resize(width, height)
			self.background.hilight({})
		x = geometry.x + (geometry.width - width) // 2
		y = geometry.y + (geometry.height - height) // 2
		return x, y

	def parse_argumets(self, argv):
		if not OSDWindow.parse_argumets(self, argv):
			return False
		self._cancel_with = self.args.cancel_with
		return True

	def _cononect_handlers(self):
		self._eh_ids += [
			(self.daemon, self.daemon.connect("dead", self.on_daemon_died)),
			(self.daemon, self.daemon.connect("error", self.on_daemon_died)),
			(self.daemon, self.daemon.connect("profile-changed", self.on_profile_changed)),
			(self.daemon, self.daemon.connect("alive", self.on_daemon_connected)),
		]

	def run(self):
		self.daemon = DaemonManager()
		self._cononect_handlers()
		OSDWindow.run(self)

	def on_daemon_connected(self, *a):
		def success(*a):
			log.info("Sucessfully locked input")

		c = self.choose_controller(self.daemon)
		if c is None or not c.is_connected():
			# There is no controller connected to daemon
			self.on_failed_to_lock("Controller not connected")
			return

		# The binding-display image is per-controller, so it can only be
		# resolved now that we know which controller is connected. show() left
		# the window unbuilt; build it here and draw the profile the controller
		# already has (the daemon may have reported the profile before the
		# window existed, so relying on the profile-changed signal alone would
		# leave the boxes blank until the next profile change).
		if self.background is None:
			self._build_and_show(self._resolve_image(c))
			self._draw_profile(c.get_profile())

		self._eh_ids += [
			(c, c.connect("event", self.on_event)),
			(c, c.connect("lost", self.on_controller_lost)),
		]

		# Lock everything
		locks = ["RB", "LB", self.args.cancel_with]
		c.lock(success, self.on_failed_to_lock, *locks)

	def _resolve_image(self, controller: ControllerManager) -> str:
		"""Picks the binding-display SVG for the connected controller.

		Order of preference:
		  1. an explicit image given on the command line
		  2. "binding_display" filename set in the controller's gui config
		  3. convention: binding-display/<gui background>.svg
		     (looked up in ~/.config/scc first, then the bundled images dir)
		  4. the generic binding-display.svg (user override, then bundled)
		The generic fallback keeps controllers without a dedicated layout
		working - they just render on the old template, as before.
		"""
		images_path = os.path.join(get_share_path(), "images")
		config_path = get_config_path()
		candidates = []
		# 1. explicit command-line image (default equals self.bdisplay)
		cli = getattr(self.args, "image", None)
		if cli and cli != self.bdisplay:
			candidates.append(cli)
		# 2./3. per-controller, from the controller's gui config
		try:
			config = controller.load_gui_config(images_path)
		except Exception:
			log.exception("Failed to load controller gui config")
			config = None
		gui = (config or {}).get("gui") or {}
		explicit = gui.get("binding_display")
		if explicit:
			if "/" in explicit:
				candidates.append(explicit)
			else:
				candidates.append(os.path.join(config_path, explicit))
				candidates.append(os.path.join(images_path, explicit))
		background = gui.get("background")
		self._layout_key = background   # selects the per-controller box layout
		if background:
			# per-controller templates live in the binding-display/ subdir, with
			# an optional user override under ~/.config/scc/binding-display/.
			fname = os.path.join("binding-display", "%s.svg" % (background,))
			candidates.append(os.path.join(config_path, fname))
			candidates.append(os.path.join(images_path, fname))
		# 4. generic fallback (already user-override-then-bundled)
		candidates.append(self.bdisplay)
		for path in candidates:
			if path and os.path.exists(path):
				log.debug("Using binding-display image: %s", path)
				return path
		return self.bdisplay

	def quit(self, code=-1):
		if self.get_controller():
			self.get_controller().unlock_all()
		for source, eid in self._eh_ids:
			source.disconnect(eid)
		self._eh_ids = []
		OSDWindow.quit(self, code)

	def show(self, *a):
		# The background image is per-controller and only known once the daemon
		# reports the connected controller, so the real show is deferred to
		# on_daemon_connected() -> _build_and_show(). Until the background
		# exists this is a no-op (run() calls show() before the daemon is up).
		if self.background is not None:
			OSDWindow.show(self, *a)
			self.move(*self.compute_position())

	def _build_and_show(self, image: str) -> None:
		"""Builds the window around the given background image and shows it."""
		self.realize()
		self.background = SVGWidget(image, init_hilighted=True)
		self.c.add(self.background)
		self.add(self.c)
		OSDWindow.show(self)
		self.move(*self.compute_position())

	def on_event(self, daemon, what, data):
		"""Called when button press, button release or stick / pad update is
		send by daemon.
		"""
		if what == self._cancel_with:
			if data[0] == 0:  # Button released
				self.quit(-1)


class Align(IntEnum):
	TOP = 1 << 0
	BOTTOM = 1 << 1
	LEFT = 1 << 2
	RIGHT = 1 << 3


def find_image(name):
	# TODO: This
	filename = "images/" + name + ".svg"
	if os.path.exists(filename):
		return filename
	return None


class Line:
	def __init__(self, icon, text):
		self.icons = [icon]
		self.text = text

	def get_size(self, gen):
		# TODO: This
		return gen.char_width * len(self.text), gen.line_height

	def add_icon(self, icon) -> Self:
		self.icons.append(icon)
		return self

	def to_string(self):
		return "%-10s: %s" % (",".join([x for x in self.icons if x]), self.text)


class LineCollection:
	"""Allows calling add_icon on multiple lines at once"""

	def __init__(self, *lines):
		self.lines = lines

	def add_icon(self, icon) -> Self:
		for line in self.lines:
			line.add_icon(icon)
		return self


class Box:
	PADDING = 5
	SPACING = 2
	MIN_WIDTH = 100
	MIN_HEIGHT = 50
	MIN_SCALE = 0.4   # smallest font shrink before lines may overflow anyway

	def __init__(self, anchor_x: int, anchor_y: int, align: Align, name: str, min_width: int = MIN_WIDTH,
	             min_height: int = MIN_HEIGHT, max_width: int = 999999, max_height: int = 999999) -> None:
		self.name = name
		self.lines = []
		self.anchor = anchor_x, anchor_y
		self.align = align
		self.min_height = min_height
		self.x, self.y = 0, 0
		self.min_width = min_width
		self.max_width = max_width
		self.max_height = max_height
		self.min_height = min_height

	def to_string(self):
		return "--- %s ---\n%s\n" % (self.name, "\n".join([x.to_string() for x in self.lines]))

	def add(self, icon, context, action):
		if not action:
			return LineCollection()
		if isinstance(action, MultiAction):
			if not action.is_key_combination():
				return LineCollection([self.add(icon, context, child) for child in action.actions])
		elif isinstance(action, ModeModifier):
			lines = [self.add(icon, context, action.default)]
			for x in action.mods:
				lines.append(self.add(nameof(x), context, action.mods[x]).add_icon(icon))
			return LineCollection(*lines)
		elif isinstance(action, DoubleclickModifier):
			lines = []
			if action.normalaction:
				lines.append(self.add(icon, context, action.normalaction))
			if action.action:
				lines.append(self.add("DOUBLECLICK", context, action.action).add_icon(icon))
			if action.holdaction:
				lines.append(self.add("HOLD", context, action.holdaction).add_icon(icon))
			return LineCollection(*lines)

		action = action.strip()
		if isinstance(action, MenuAction):
			if self.name in ("bcs", "system") and action.menu_id == "Default.menu":
				# Special case, this action is expected in every profile,
				# so there is no need to draw it here
				return LineCollection()
		elif isinstance(action, DPadAction):
			return LineCollection(
				self.add("DPAD_UP", Action.AC_BUTTON, action.actions[0]),
				self.add("DPAD_DOWN", Action.AC_BUTTON, action.actions[1]),
				self.add("DPAD_LEFT", Action.AC_BUTTON, action.actions[2]),
				self.add("DPAD_RIGHT", Action.AC_BUTTON, action.actions[3]),
			)
		elif isinstance(action, XYAction):
			if isinstance(action.x, MouseAction) and isinstance(action.y, MouseAction):
				if action.x.get_axis() in (Rels.REL_HWHEEL, Rels.REL_WHEEL):
					# Special case, pad bound to wheel
					line = Line(icon, _("Mouse Wheel"))
					self.lines.append(line)
					return line
			if isinstance(action.x, AxisAction) and isinstance(action.y, AxisAction):
				if action.x.axis and action.y.axis:
					line = Line(icon, action.x.describe(Action.AC_BUTTON))
					self.lines.append(line)
					return line
			return LineCollection(
				self.add("AXISX", Action.AC_BUTTON, action.x), self.add("AXISY", Action.AC_BUTTON, action.y),
			)
		line = Line(icon, action.describe(context))
		self.lines.append(line)
		return line

	def calculate(self, gen):
		self.width, self.height = self.min_width, 2 * self.PADDING
		self.icount = 0
		for line in self.lines:
			lw, lh = line.get_size(gen)
			self.width, self.height = max(self.width, lw), self.height + lh + self.SPACING
			self.icount = max(self.icount, len(line.icons))
		self.width += 2 * self.PADDING + self.icount * (gen.line_height + self.SPACING)
		self.width = min(self.width, self.max_width)
		self.height = max(self.height, self.min_height)
		# Auto-scale the font for this box so all its lines fit within max_height.
		# place() draws every line regardless of box height, so without this a
		# crowded box (e.g. a stick bound to a big radial/dpad, or mode-heavy face
		# buttons) overflows downward off the box and the screen.
		content = self.height - 2 * self.PADDING
		avail = self.max_height - 2 * self.PADDING
		if content > avail and content > 0:
			self.scale = max(self.MIN_SCALE, avail / content)
			self.height = self.max_height
		else:
			self.scale = 1.0

		anchor_x, anchor_y = self.anchor
		if (self.align & Align.TOP) != 0:
			self.y = anchor_y
		elif (self.align & Align.BOTTOM) != 0:
			self.y = gen.full_height - self.height - anchor_y
		else:
			self.y = (gen.full_height - self.height) / 2

		if (self.align & Align.LEFT) != 0:
			self.x = anchor_x
		elif (self.align & Align.RIGHT) != 0:
			self.x = gen.full_width - self.width - anchor_x
		else:
			self.x = (gen.full_width - self.width) / 2

	def place(self, gen, root):
		e = SVGEditor.add_element(
			root,
			"rect",
			style="opacity:1;fill-opacity:0.1;stroke-width:2.0;",
			fill="#00FF00",
			stroke="#06a400",
			id="box_%s" % (self.name,),
			width=self.width,
			height=self.height,
			x=self.x,
			y=self.y,
		)

		scale = getattr(self, "scale", 1.0)
		lh = gen.line_height * scale
		text_style = gen.label_style(scale)
		y = self.y + self.PADDING
		for line in self.lines:
			h = lh
			x = self.x + self.PADDING
			for icon in line.icons:
				image = find_image(icon)
				if image:
					# Fix: here stuff goes from weird to awfull, as rsvg
					# (library that gnome uses to render SVGs) can't render
					# linked images. Embeding is used instead.
					image = "data:image/svg+xml;base64,%s" % (base64.b64encode(open(image, "rb").read()))
					# Another problem: rsvg will NOT draw image unless href
					# tag uses namespace. No idea why is that, but I spent
					# 3 hours finding this, so I'm willing to murder.
					SVGEditor.add_element(
						root, "image", x=x, y=y, style="filter:url(#filterInvert)", width=h, height=h, href=image,
					)
				x += h + self.SPACING
			x = self.x + self.PADDING + self.icount * (h + self.SPACING)
			y += h
			txt = SVGEditor.add_element(root, "text", x=x, y=y, style=text_style)
			max_line_width = self.max_width - lh - self.PADDING
			while line.text and line.get_size(gen)[0] * scale > max_line_width:
				line.text = line.text[:-1]
			SVGEditor.set_text(txt, line.text)
			y += self.SPACING * scale

	def place_marker(self, gen, root):
		x1, y1 = self.x, self.y
		x2, y2 = x1 + self.width, y1 + self.height
		if self.align & (Align.LEFT | Align.RIGHT) == 0:
			edges = [[x2, y2], [x1, y2]]
		elif self.align & Align.BOTTOM == Align.BOTTOM:
			if self.align & Align.LEFT != 0:
				edges = [[x2, y2], [x1, y1]]
			elif self.align & Align.RIGHT != 0:
				edges = [[x2, y1], [x1, y2]]
		elif self.align & Align.TOP == Align.TOP:
			if self.align & Align.LEFT != 0:
				edges = [[x2, y1], [x2, y2]]
			elif self.align & Align.RIGHT != 0:
				edges = [[x1, y1], [x1, y2]]
		elif self.align & Align.LEFT != 0:
			edges = [[x2, y1], [x2, y2]]
		elif self.align & Align.RIGHT != 0:
			edges = [[x1, y1], [x2, y2]]

		targets = SVGEditor.get_element(root, "markers_%s" % (self.name,))
		if targets is None:
			return
		i = 0
		for target in targets:
			tx, ty = float(target.attrib["cx"]), float(target.attrib["cy"])
			try:
				edges[i] += [tx, ty]
				i += 1
			except IndexError:
				break
		edges = [i for i in edges if len(i) == 4]

		for x1, y1, x2, y2 in edges:
			e = SVGEditor.add_element(
				root,
				"line",
				style="opacity:1;stroke:#06a400;stroke-width:0.5;",
				# id = "box_%s_line0" % (self.name,),
				x1=x1,
				y1=y1,
				x2=x2,
				y2=y2,
			)


# --- per-controller binding-display layouts --------------------------------
# Which controls go in which box is semantic, so it lives here rather than in
# the template SVG (which only supplies marker positions + the canvas). Keyed by
# the controller's gui "background" name; controllers without an entry fall back
# to the v1 layout (Generator._build_v1). Box positions are auto-placed from the
# Align flags; size caps are fractions of the canvas. Only bound controls draw a
# line and a box with no bound controls is hidden (Generator._build_layout), so
# every variant (grip-squeeze, stick/pad touch & press, ...) can be listed and
# simply stays invisible until the user binds it.
_B, _T, _P, _S = Action.AC_BUTTON, Action.AC_TRIGGER, Action.AC_PAD, Action.AC_STICK


def _btn(name: str) -> Callable[[Profile], Action | None]:
	return lambda p: p.buttons.get(SCButtons[name])


def _pad(side: str) -> Callable[[Profile], Action | None]:
	return lambda p: p.pads.get(side)


def _trig(side: str) -> Callable[[Profile], Action | None]:
	return lambda p: p.triggers.get(side)


def _stick(p: Profile) -> Action:
	return p.stick


def _rstick(p: Profile) -> Action | None:
	return getattr(p, "rstick", None)


LAYOUTS = {
	# Steam Controller v2 (2026) -- Steam Deck control set: two sticks, a D-pad,
	# two trackpads, four system buttons, back paddles + grip-squeeze sensors.
	# Six boxes: four corners + top/bottom centre, controller art in the middle.
	"sc2": [
		dict(name="system", align=Align.TOP, ax=0, max_width_f=0.4, max_height_f=0.22,
		     controls=[("BACK", _B, _btn("BACK")), ("C", _B, _btn("C")),
		               ("START", _B, _btn("START")), ("DOTS", _B, _btn("DOTS"))]),
		dict(name="lshoulder", align=Align.LEFT | Align.TOP,
		     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
		     controls=[("LT", _T, _trig(LEFT)), ("LB", _B, _btn("LB")),
		               ("LGRIP", _B, _btn("LGRIP")), ("LGRIP2", _B, _btn("LGRIP2")),
		               ("LGRIPTOUCH", _B, _btn("LGRIPTOUCH"))]),
		dict(name="rshoulder", align=Align.RIGHT | Align.TOP,
		     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
		     controls=[("RT", _T, _trig(RIGHT)), ("RB", _B, _btn("RB")),
		               ("RGRIP", _B, _btn("RGRIP")), ("RGRIP2", _B, _btn("RGRIP2")),
		               ("RGRIPTOUCH", _B, _btn("RGRIPTOUCH"))]),
		dict(name="lthumb", align=Align.LEFT | Align.BOTTOM,
		     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
		     controls=[("STICK", _S, _stick), ("DPAD", _P, _pad(DPAD)),
		               ("LPAD", _P, _pad(LEFT))]),
		dict(name="rthumb", align=Align.RIGHT | Align.BOTTOM,
		     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
		     controls=[("RSTICK", _S, _rstick), ("RPAD", _P, _pad(RIGHT))]),
		dict(name="face", align=Align.BOTTOM, ax=0, max_width_f=0.4, max_height_f=0.22,
		     controls=[("A", _B, _btn("A")), ("B", _B, _btn("B")),
		               ("X", _B, _btn("X")), ("Y", _B, _btn("Y"))]),
	],
}

# The Steam Deck's built-in controller shares the v2's physical control set (same
# boxes, same controls), so it reuses the v2 layout. Controls the Deck lacks stay
# unbound and their boxes render nothing, so the shared list is safe.
LAYOUTS["deck"] = LAYOUTS["sc2"]

# Standard gamepads (DualShock 4, DualSense, Xbox 360). Their control model
# differs from the Steam controllers: the right stick is the right pad
# (pads[RIGHT], not rstick) and the d-pad is the left pad (pads[LEFT]); there are
# no trackpads or grip-touch. Same six-box frame. ds4/ds5/x360 are physically
# alike, so they share one layout.
_GAMEPAD_LAYOUT = [
	dict(name="system", align=Align.TOP, ax=0, max_width_f=0.4, max_height_f=0.22,
	     controls=[("BACK", _B, _btn("BACK")), ("C", _B, _btn("C")),
	               ("START", _B, _btn("START"))]),
	dict(name="lshoulder", align=Align.LEFT | Align.TOP,
	     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
	     controls=[("LT", _T, _trig(LEFT)), ("LB", _B, _btn("LB")),
	               ("LGRIP", _B, _btn("LGRIP"))]),
	dict(name="rshoulder", align=Align.RIGHT | Align.TOP,
	     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
	     controls=[("RT", _T, _trig(RIGHT)), ("RB", _B, _btn("RB")),
	               ("RGRIP", _B, _btn("RGRIP"))]),
	dict(name="lthumb", align=Align.LEFT | Align.BOTTOM,
	     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
	     controls=[("STICK", _S, _stick), ("DPAD", _P, _pad(LEFT))]),
	dict(name="rthumb", align=Align.RIGHT | Align.BOTTOM,
	     min_width_f=0.18, max_width_f=0.27, max_height_f=0.42,
	     controls=[("RSTICK", _P, _pad(RIGHT))]),
	dict(name="face", align=Align.BOTTOM, ax=0, max_width_f=0.4, max_height_f=0.22,
	     controls=[("A", _B, _btn("A")), ("B", _B, _btn("B")),
	               ("X", _B, _btn("X")), ("Y", _B, _btn("Y"))]),
]
LAYOUTS["ds4"] = LAYOUTS["ds5"] = LAYOUTS["x360"] = _GAMEPAD_LAYOUT


class Generator:
	PADDING = 10

	def __init__(self, editor: SVGEditor, profile: Profile, layout_key: str | None = None) -> None:
		background = SVGEditor.get_element(editor, "background")
		self.label_template = SVGEditor.get_element(editor, "label_template")
		self.line_height = int(float(self.label_template.attrib.get("height") or 8))
		self.char_width = int(float(self.label_template.attrib.get("width") or 8))
		self.full_width = int(float(background.attrib.get("width") or 800))
		self.full_height = int(float(background.attrib.get("height") or 800))
		self._label_style = self.label_template.attrib.get("style", "")
		m = re.search(r"font-size:\s*([\d.]+)", self._label_style)
		self.font_size = float(m.group(1)) if m else self.line_height * 1.45
		root = SVGEditor.get_element(editor, "root")

		layout = LAYOUTS.get(layout_key)
		if layout is None:
			self._build_v1(profile, root)
		else:
			self._build_layout(profile, root, layout)

		editor.commit()

	def _build_v1(self, profile: Profile, root: ET.Element) -> None:
		"""The original 5-box layout (Steam Controller v1: one stick, no D-pad,
		three system buttons). Used for v1 and any controller without a dedicated
		entry in LAYOUTS."""
		boxes = []
		box_bcs = Box(0, self.PADDING, Align.TOP, "bcs", max_height=self.full_height * 0.25)
		box_bcs.add("BACK", Action.AC_BUTTON, profile.buttons.get(SCButtons.BACK))
		box_bcs.add("C", Action.AC_BUTTON, profile.buttons.get(SCButtons.C))
		box_bcs.add("START", Action.AC_BUTTON, profile.buttons.get(SCButtons.START))
		boxes.append(box_bcs)

		box_left = Box(
			self.PADDING,
			self.PADDING,
			Align.LEFT | Align.TOP,
			"left",
			min_height=self.full_height * 0.5,
			min_width=self.full_width * 0.2,
			max_width=self.full_width * 0.275,
			max_height=self.full_height * 0.85,
		)
		box_left.add("LEFT", Action.AC_TRIGGER, profile.triggers.get(profile.LEFT))
		box_left.add("LB", Action.AC_BUTTON, profile.buttons.get(SCButtons.LB))
		box_left.add("LGRIP", Action.AC_BUTTON, profile.buttons.get(SCButtons.LGRIP))
		box_left.add("LPAD", Action.AC_PAD, profile.pads.get(profile.LEFT))
		boxes.append(box_left)

		box_right = Box(
			self.PADDING,
			self.PADDING,
			Align.RIGHT | Align.TOP,
			"right",
			min_height=self.full_height * 0.5,
			min_width=self.full_width * 0.2,
			max_width=self.full_width * 0.275,
			max_height=self.full_height * 0.85,
		)
		box_right.add("RIGHT", Action.AC_TRIGGER, profile.triggers.get(profile.RIGHT))
		box_right.add("RB", Action.AC_BUTTON, profile.buttons.get(SCButtons.RB))
		box_right.add("RGRIP", Action.AC_BUTTON, profile.buttons.get(SCButtons.RGRIP))
		box_right.add("RPAD", Action.AC_PAD, profile.pads.get(profile.RIGHT))
		boxes.append(box_right)

		box_abxy = Box(
			4 * self.PADDING, self.PADDING, Align.RIGHT | Align.BOTTOM, "abxy",
			max_width=self.full_width * 0.45, max_height=self.full_height * 0.25,
		)
		box_abxy.add("A", Action.AC_BUTTON, profile.buttons.get(SCButtons.A))
		box_abxy.add("B", Action.AC_BUTTON, profile.buttons.get(SCButtons.B))
		box_abxy.add("X", Action.AC_BUTTON, profile.buttons.get(SCButtons.X))
		box_abxy.add("Y", Action.AC_BUTTON, profile.buttons.get(SCButtons.Y))
		boxes.append(box_abxy)

		box_stick = Box(
			4 * self.PADDING, self.PADDING, Align.LEFT | Align.BOTTOM, "stick",
			max_width=self.full_width * 0.45, max_height=self.full_height * 0.25,
		)
		box_stick.add("STICK", Action.AC_STICK, profile.stick)
		boxes.append(box_stick)

		for b in boxes:
			b.calculate(self)

		# Set ABXY and Stick size & position
		box_abxy.height = box_stick.height = self.full_height * 0.25
		box_abxy.width = box_stick.width = self.full_width * 0.3
		box_abxy.y = self.full_height - self.PADDING - box_abxy.height
		box_stick.y = self.full_height - self.PADDING - box_stick.height
		box_abxy.x = self.full_width - self.PADDING - box_abxy.width

		self.equal_width(box_left, box_right)
		self.equal_height(box_left, box_right)

		for b in boxes:
			b.place_marker(self, root)
		for b in boxes:
			b.place(self, root)

	def _build_layout(self, profile: Profile, root: ET.Element, layout: list[dict]) -> None:
		"""Builds boxes from a per-controller LAYOUTS spec. Box positions are
		auto-placed from the Align flags; size caps come from canvas fractions.
		Boxes whose controls are all unbound draw nothing and are dropped."""
		boxes = []
		for spec in layout:
			box = Box(
				spec.get("ax", self.PADDING),
				spec.get("ay", self.PADDING),
				spec["align"],
				spec["name"],
				min_width=spec.get("min_width_f", 0) * self.full_width or Box.MIN_WIDTH,
				min_height=spec.get("min_height_f", 0) * self.full_height or Box.MIN_HEIGHT,
				max_width=spec.get("max_width_f", 1.0) * self.full_width,
				max_height=spec.get("max_height_f", 1.0) * self.full_height,
			)
			for icon, context, getter in spec["controls"]:
				box.add(icon, context, getter(profile))
			boxes.append(box)

		for b in boxes:
			b.calculate(self)
		# Hide boxes that ended up with no bound controls.
		boxes = [b for b in boxes if b.lines]

		for b in boxes:
			b.place_marker(self, root)
		for b in boxes:
			b.place(self, root)

	def label_style(self, scale: float) -> str:
		"""Label text style with font-size scaled by `scale` (used to shrink a
		crowded box so its lines fit). Returns the template style unchanged at
		scale 1.0."""
		if scale >= 0.999:
			return self._label_style
		fs = self.font_size * scale
		if re.search(r"font-size:\s*[\d.]+px", self._label_style):
			return re.sub(r"font-size:\s*[\d.]+px", "font-size:%.1fpx" % (fs,), self._label_style)
		return "font-size:%.1fpx;%s" % (fs, self._label_style)

	def equal_width(self, *boxes):
		"""Sets width of all passed boxes to width of widest box"""
		width = 0
		for b in boxes:
			width = max(width, b.width)
		for b in boxes:
			b.width = width
			if b.align & Align.RIGHT:
				b.x = self.full_width - b.width - self.PADDING

	def equal_height(self, *boxes):
		"""Sets height of all passed boxes to height of tallest box"""
		height = 0
		for b in boxes:
			height = max(height, b.height)
		for b in boxes:
			b.height = height


def main():
	m = BindingDisplay()
	if not m.parse_argumets(sys.argv):
		sys.exit(1)
	m.run()
	sys.exit(m.get_exit_code())


if __name__ == "__main__":
	from scc.tools import init_logging

	init_logging()
	main()
