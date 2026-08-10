from __future__ import annotations

import logging
import os
import time
import traceback
from typing import TYPE_CHECKING

from scc.actions import Action, ButtonAction, GyroAction
from scc.aliases import ALL_AXES, ALL_BUTTONS
from scc.config import Config
from scc.constants import (
	CPAD,
	DPAD,
	FE_PAD,
	FE_STICK,
	FE_TRIGGER,
	LSTICK,
	LSTICKTILT,
	RSTICK,
	STICK_PAD_MAX,
	ControllerFlags,
	HapticPos,
	SCButtons,
	SCPads,
	SCPadsLR,
	SCSticks,
	SCTouchpads,
	SCTriggers,
)
from scc.controller import HapticData
from scc.lib import xwrappers as X
from scc.uinput import Dummy, Keyboard, Mouse, UInput

if TYPE_CHECKING:
	from scc.controller import Controller
	from scc.drivers.ds5drv import DualSenseBTControllerInput
	from scc.drivers.evdevdrv import EvdevControllerInput
	from scc.drivers.hiddrv import HIDControllerInput
	from scc.drivers.sc_dongle import ControllerInput
	from scc.poller import Poller
	from scc.profile import Profile
	from scc.scheduler import Scheduler, Task
	type CInput = DualSenseBTControllerInput | ControllerInput | HIDControllerInput | EvdevControllerInput

log = logging.getLogger("Mapper")


class Mapper:
	DEBUG: bool = False
	# We always output mouse movement at this 4ms/250Hz interval
	# Maybe we should make this configurable in case some madman with a 300Hz+ screen wishes to have a smoother movement
	BT_STICK_MOUSE_INTERVAL: float = 1.0 / 250
	# Max delta time between ticks that can be used for movement calculation
	# This shouldn't trigger in the first place and is a safety measure
	# Prevents cursor jumping all over the place in case SCC daemon stalls for some reason
	# Extra explanation: That would mean that an interval of less than 40Hz would start losing total movement
	BT_STICK_MOUSE_MAX_DT: float = 0.025

	def __init__(
		self,
		profile: Profile,
		scheduler: Scheduler,
		keyboard: bytes = b"SCController Keyboard",
		mouse: bytes = b"SCController Mouse",
		gamepad: bool = True,
		poller: Poller | None = None,
	) -> None:
		"""If any of keyboard, mouse or gamepad is set to None, that device will not be emulated.

		Emulated gamepad will have rumble enabled only if poller is set to instance and configuration allows it.
		"""
		self.profile: Profile = profile
		# TODO(Martin): This probably isn't Controller but needs to be a subset class of all the EvdevController etc
		self.controller: Controller | None = None
		self.xdisplay = None
		self.scheduler: Scheduler = scheduler

		# Create virtual devices
		log.debug("Creating virtual devices")
		self.keyboard: Keyboard | Dummy = self.create_keyboard(keyboard) if keyboard else Dummy()
		log.debug(f"Keyboard: {self.keyboard}")
		self.mouse: Mouse | Dummy = self.create_mouse(mouse) if mouse else Dummy()
		log.debug(f"Mouse:    {self.mouse}")
		self.gamepad: UInput | Dummy | None = self.create_gamepad(gamepad, poller) if gamepad else Dummy()
		log.debug(f"Gamepad:  {self.gamepad}")

		# Set by SCCDaemon instance; Used to handle actions
		# from scc.special_actions
		self._sa_handler = None

		# Setup emulation
		self.keypress_list = []
		self.keyrelease_list = []
		self.mouse_movements = [0,0,0,0,0,0]  # mouse x, y, wheel vertical, horizontal, stick mouse x, stick mouse y
		self.feedbacks: list[HapticData | None] = [None, None]  # left, right
		self.pressed = {}  # for ButtonAction, holds number of times virtual button was pressed without releasing it first
		self.syn_list = set()
		self.buttons: SCButtons = SCButtons(0)
		self.old_buttons: SCButtons = SCButtons(0)
		self.lpad_touched = False
		self.state: CInput | None = None
		self.old_state: CInput | None = None
		self.force_event: set[int] = set() # FE_STICK, FE_TRIGGER, FE_PAD or FE_GYRO
		self.time_elapsed = 0.0
		self._bt_stick_mouse_velocities: dict[tuple[Action, SCSticks], tuple[float, float]] = {}
		self._bt_stick_mouse_task: Task | None = None
		self._bt_stick_mouse_last_tick: float = 0.0
		self._bt_stick_mouse_logged: bool = False

	def create_gamepad(self, enabled: bool, poller: Poller | None) -> UInput | None:
		"""Parses gamepad configuration and creates apropriate unput device"""
		if not enabled or "SCC_NOGAMEPAD" in os.environ:
			# Completly undocumented and for debuging purposes only.
			# If set, no gamepad is emulated
			self.gamepad = Dummy()
			return None
		cfg = Config()
		keys = ALL_BUTTONS[0 : cfg["output"]["buttons"]]
		vendor = int(cfg["output"]["vendor"], 16)
		product = int(cfg["output"]["product"], 16)
		version = int(cfg["output"]["version"], 16)
		name = cfg["output"]["name"]
		rumble = cfg["output"]["rumble"] and poller is not None
		axes: list[tuple[int, int, int, int, int]] = []
		i = 0
		for min, max in cfg["output"]["axes"]:
			fuzz, flat = 0, 0
			if abs(max - min) > STICK_PAD_MAX:
				fuzz, flat = 16, 128
			try:
				axes.append((ALL_AXES[i], min, max, fuzz, flat))
			except IndexError:
				# Out of axes
				break
			i += 1

		ui = UInput(
			vendor=vendor, product=product, version=version, name=name, keys=keys, axes=axes, rels=[], rumble=rumble,
		)
		if poller and rumble:
			poller.register(ui.getDescriptor(), poller.POLLIN, self._rumble_ready)
		return ui

	def create_keyboard(self, name: bytes) -> Keyboard:
		return Keyboard(name=name)

	def create_mouse(self, name: bytes) -> Mouse:
		return Mouse(name=name)

	def _rumble_ready(self, fd, event) -> None:
		# Taken from Steam Controller Singer project
		# https://gitlab.com/Pilatomic/SteamControllerSinger
		STEAM_CONTROLLER_MAGIC_PERIOD_RATIO = 495483.0
		ef = self.gamepad.ff_read()
		#log.warning("Received virtual gamepad rumble event")
		#log.warning(
		#	"FF event: level=%s duration=%s repetitions=%s",
		#	ef.level if ef else None,
		#	ef.duration if ef else None,
		#	ef.repetitions if ef else None,
		#)
		if ef:  # tale of...
			if self.controller and self.controller.get_type() != "sc":
				amplitude = min(abs(ef.level), 0x7FFF) if ef.repetitions > 0 else 0
				period_command = 1024
				duration_seconds = ef.duration / 1000.0 * ef.repetitions
				count = min(round(duration_seconds * 0x10000 / period_command), 0x7FFF) if amplitude else 0
				self.send_feedback(
					HapticData(HapticPos.BOTH, period=period_command, amplitude=amplitude, count=count),
				)
				self.generate_feedback()
				return

			# Controllers with real rumble motors take the magnitude directly;
			# only fall through to the click-train emulation below if they
			# cannot, which on a v1 is always, its "motors" being pad actuators.
			strong, weak = ef.strong, ef.weak
			if not strong and not weak and ef.level > 0:
				# Only FF_RUMBLE carries the two magnitudes. Every other effect
				# type -- and any older libuinput -- provides just the averaged
				# level, so drive both motors from that instead of handing the
				# controller a silent (0, 0) and returning as if it played.
				strong = weak = ef.level
			if self.controller and self.controller.rumble(
					strong, weak, int(ef.duration * max(1, ef.repetitions))):
				return
			period_command = 0
			amplitude = 0
			if ef.level != 0 and ef.repetitions > 0:
				tempRatio = ef.level / 32767.5
				period_command = (6000 - 25000) * tempRatio + 25000
				amplitude = (900 - 600) * tempRatio + 600

			raw_period = period_command / STEAM_CONTROLLER_MAGIC_PERIOD_RATIO
			# duration_seconds = 1
			duration_seconds = ef.duration / 1000.0 * ef.repetitions
			count = 0
			if raw_period != 0:
				count = min(int(duration_seconds * 1.5 / raw_period), 0x7FFF)

			# log.debug(f"{ef.level} {ef.duration} {ef.repetitions} {count}")
			self.send_feedback(
				HapticData(
					HapticPos.BOTH,
					period=period_command,
					amplitude=amplitude,
					count=count,
					# period = 20000,
					# amplitude = max(0, ef.level),
					# count = min(0x7FFF, ef.duration * ef.repetitions / 30)
				),
			)
			self.generate_feedback()

	def get_gamepad_name(self) -> str | None:
		"""Returns name of emulated gamepad (as displayed by jstest & co) or None if Dummy is assigned."""
		if isinstance(self.gamepad, Dummy):
			return None
		return self.gamepad.name

	def sync(self) -> None:
		"""Syncs generated events"""
		if len(self.syn_list):
			for dev in self.syn_list:
				dev.synEvent()
			self.syn_list = set()

	def set_controller(self, c) -> None:
		"""Sets controller device, used by some (one so far) actions"""
		self.controller = c

	def get_controller(self):
		"""Returns assigned controller device or None if no controller is set"""
		return self.controller

	def set_special_actions_handler(self, sa) -> None:
		self._sa_handler = sa

	def get_special_actions_handler(self):
		return self._sa_handler

	def set_xdisplay(self, x) -> None:
		self.xdisplay = x

	def get_xdisplay(self):
		return self.xdisplay

	def get_current_window(self):
		"""Returns window id of current window or None if xdisplay is not set"""
		if self.xdisplay:
			return X.get_current_window(self.xdisplay)
		return None

	def schedule(self, delay, cb) -> Task:
		"""Schedules callback to be ran no sooner than after delay.

		Delay is float number in seconds.
		Callback is called with mapper as only argument.
		"""
		return self.scheduler.schedule(delay, cb, self)

	def cancel_task(self, task: Task) -> bool:
		"""Removes scheduled task."""
		return self.scheduler.cancel_task(task)

	def mouse_move(self, dx, dy) -> None:
		"""Schedules mouse movement to be done at end of processing callback.

		Called from actions while callback is being processed.
		"""
		self.mouse_movements[0] += dx
		self.mouse_movements[1] += dy

	def mouse_wheel(self, wx, wy) -> None:
		"""Schedules mouse wheel movement to be done at end of processing callback.

		Called from actions while callback is being processed.
		"""
		self.mouse_movements[2] += wx
		self.mouse_movements[3] += wy

	def mouse_move_stick(self, dx, dy) -> None:
		"""Schedules mouse movement to be done at end of processing callback.

		Called from actions while callback is being processed.
		"""
		self.mouse_movements[4] += dx
		self.mouse_movements[5] += dy

	def set_bt_stick_mouse_velocity(self, source: Action, what: SCSticks, vx: float, vy: float) -> bool:
		"""Hold and emit Bluetooth stick mouse velocity at the Hz rate defined in BT_STICK_MOUSE_INTERVAL.

		It might be useful to expand this past BT, as a wireless proprietary 2.4GHz dongle may not
		have the best of input rates either.

		It might actually make sense to do this for wired devices too, in case we run into a controller
		with funny-low input rate like 125Hz.
		"""
		if self.controller is None or not self.controller.is_bluetooth():
			return False

		key = (source, what)
		if vx or vy:
			self._bt_stick_mouse_velocities[key] = (vx, vy)
		else:
			self._bt_stick_mouse_velocities.pop(key, None)
			if not self._bt_stick_mouse_velocities and self._bt_stick_mouse_task is not None:
				self._bt_stick_mouse_task.cancel()
				self._bt_stick_mouse_task = None

		if self._bt_stick_mouse_velocities and self._bt_stick_mouse_task is None:
			self._bt_stick_mouse_last_tick = time.monotonic()
			self._bt_stick_mouse_task = self.schedule(self.BT_STICK_MOUSE_INTERVAL, self._tick_bt_stick_mouse)
			if not self._bt_stick_mouse_logged:
				log.debug("Bluetooth stick mouse output resampling enabled")
				self._bt_stick_mouse_logged = True
		return True

	def clear_bt_stick_mouse_velocity(self, source: Action | None = None) -> None:
		if source is None:
			self._bt_stick_mouse_velocities.clear()
		else:
			for key in tuple(self._bt_stick_mouse_velocities):
				if key[0] is source:
					del self._bt_stick_mouse_velocities[key]

		if not self._bt_stick_mouse_velocities and self._bt_stick_mouse_task is not None:
			self._bt_stick_mouse_task.cancel()
			self._bt_stick_mouse_task = None

	def _tick_bt_stick_mouse(self, mapper: Mapper) -> None:
		self._bt_stick_mouse_task = None
		if not self._bt_stick_mouse_velocities:
			return

		now = time.monotonic()
		dt = min(max(now - self._bt_stick_mouse_last_tick, 0.0), self.BT_STICK_MOUSE_MAX_DT)
		self._bt_stick_mouse_last_tick = now
		vx = sum(velocity[0] for velocity in self._bt_stick_mouse_velocities.values())
		vy = sum(velocity[1] for velocity in self._bt_stick_mouse_velocities.values())
		self.mouse.moveStickEvent(vx * dt, vy * -dt, dt)
		self._bt_stick_mouse_task = self.schedule(self.BT_STICK_MOUSE_INTERVAL, self._tick_bt_stick_mouse)

	def send_feedback(self, hapticdata: HapticData) -> None:
		"""Schedules haptic feedback to be sent at end of processing callback.

		Called from actions while callback is being processed.
		"""
		if hapticdata.get_position() == HapticPos.BOTH:
			# HapticPos.BOTH is special case as controller doesn't
			# really support doing that by itself.
			self.feedbacks[0] = hapticdata.with_position(HapticPos.LEFT)
			self.feedbacks[1] = hapticdata.with_position(HapticPos.RIGHT)
		else:
			self.feedbacks[hapticdata.get_position()] = hapticdata

	def controller_flags(self) -> int:
		"""Returns controller flags or, if there is no controller set to this mapper, sc_by_cable driver matching defaults."""
		return 0 if self.controller is None else self.controller.flags

	def is_touched(self, what: SCTouchpads) -> bool:
		"""Returns True if specified pad is being touched.

		May randomly return False for aphephobic pads.

		'what' should be LPAD, RPAD or CPAD - if anything else is passed(how), return False
		"""
		if what == SCPads.LPAD:
			return bool(self.buttons & SCButtons.LPADTOUCH)
		if what == SCPads.RPAD:
			return bool(self.buttons & SCButtons.RPADTOUCH)
		if what == SCPads.CPAD:
			return bool(self.buttons & SCButtons.CPADTOUCH)
		return False

	def was_touched(self, what: SCTouchpads) -> bool:
		"""As is_touched, but returns True if pad *was* touched in previous known state.

		This is used as:
		is_touched() and not was_touched() -> pad was just pressed
		not is_touched() and was_touched() -> pad was just released
		"""
		if what == SCPads.LPAD:
			return bool(self.old_buttons & SCButtons.LPADTOUCH)
		if what == SCPads.RPAD:
			return bool(self.old_buttons & SCButtons.RPADTOUCH)
		if what == SCPads.CPAD:
			return bool(self.old_buttons & SCButtons.CPADTOUCH)
		return False

	def is_pressed(self, button: SCPadsLR | int) -> bool:
		"""Returns True if button is pressed"""
		if button == SCPads.LPAD:
			button = SCButtons.LPAD
		elif button == SCPads.RPAD:
			button = SCButtons.RPAD
		return bool(self.buttons & button)

	def was_pressed(self, button: SCPadsLR | int) -> bool:
		"""Returns True if button was pressed in previous known state"""
		if button == SCPads.LPAD:
			button = SCButtons.LPAD
		elif button == SCPads.RPAD:
			button = SCButtons.RPAD
		return bool(self.old_buttons & button)

	def get_pressed_button(self) -> SCButtons | None:
		"""Gets button that was pressed by very last handled event or None, if last event doesn't involved button pressing."""
		for x in SCButtons:
			if x & self.buttons & ~self.old_buttons:
				return x
		return None

	def set_button(self, button: SCTouchpads | SCSticks | int, state: bool) -> None:
		"""Sets button state on input.

		Set value will stay only for duration of one event loop iteration.

		Used _temporarily_ by RingAction to emulate finger lifting from a pad or a stick.
		"""
		if button == SCPads.LPAD:
			button = SCButtons.LPADTOUCH
		elif button == SCPads.RPAD:
			button = SCButtons.RPADTOUCH
		elif button == SCSticks.RSTICK:
			button = SCButtons.RSTICKTOUCH
		elif button == SCSticks.LSTICK:
			button = SCButtons.LSTICKTOUCH
		elif button == SCPads.CPAD:
			button = SCButtons.CPADTOUCH
		elif isinstance(button, str):
			log.debug("set_button() received %s, ignoring", button)
			return

		if state:
			self.buttons |= button
		else:
			self.buttons &= ~button

	def set_was_pressed(self, button: SCTouchpads | SCSticks | int, state: bool) -> None:
		"""As set_button, but changes value remembered from loop iteration before current.

		Used _temporarily_ by RingAction to emulate finger lifting from a pad or a stick.
		"""
		if button == SCPads.LPAD:
			button = SCButtons.LPADTOUCH
		elif button == SCPads.RPAD:
			button = SCButtons.RPADTOUCH
		elif button == SCSticks.RSTICK:
			button = SCButtons.RSTICKTOUCH
		elif button == SCSticks.LSTICK:
			button = SCButtons.LSTICKTOUCH
		elif button == SCPads.CPAD:
			button = SCButtons.CPADTOUCH
		elif isinstance(button, str):
			log.debug("set_was_pressed() received %s, ignoring", button)
			return

		if state:
			self.old_buttons |= button
		else:
			self.old_buttons &= ~button

	def release_virtual_buttons(self) -> None:
		"""Called when daemon is killed or USB dongle is disconnected.

		Sends button release event for every virtual button that is still being pressed.
		"""
		to_release, self.pressed = self.pressed, {}
		for x in to_release:
			ButtonAction._button_release(self, x, True)

	def cancel_all(self) -> None:
		"""Called when profile is changed to let all actions to cancel long-running effects they may have created"""
		for a in self.profile.get_actions():
			a.cancel(self)
		self.clear_bt_stick_mouse_velocity()

	def reset_gyros(self) -> None:
		# GyroAction covers GyroAbsAction (subclass): absolute actions re-capture
		# their orientation reference (ir), relative ones their lean-to-turn
		# neutral pose. Rate-based outputs (laser-pointer mouse, relative stick)
		# have no reference by nature, so recentering rightly leaves them alone.
		for a in self.profile.get_all_actions():
			if isinstance(a, GyroAction):
				a.reset()

	def input(self, controller: Controller, old_state: CInput, state: CInput) -> None:
		# print(type(controller), type(old_state), type(state))
		#controller.record_mapper_input()
		# Store states
		self.old_state = old_state
		self.old_buttons = self.buttons

		self.state = state
		self.buttons = state.buttons

		t = time.time()
		controller.time_elapsed = self.time_elapsed = t - controller.lastTime
		controller.lastTime = t

		if self.buttons & SCButtons.LPAD and not self.buttons & (SCButtons.LPADTOUCH | LSTICKTILT):
			self.buttons = (self.buttons & ~SCButtons.LPAD) | SCButtons.LSTICKPRESS

		fe = self.force_event
		self.force_event = set()

		# Check buttons
		xor = self.old_buttons ^ self.buttons
		btn_rem = xor & self.old_buttons
		btn_add = xor & self.buttons

		try:
			if btn_add or btn_rem:
				# At least one button was pressed
				for x in self.profile.buttons:
					if x & btn_add:
						self.profile.buttons[x].button_press(self)
					elif x & btn_rem:
						self.profile.buttons[x].button_release(self)

			# Check sticks
			if controller.flags & ControllerFlags.SEPARATE_LSTICK:
				if FE_STICK in fe or self.old_state.lstick_x != state.lstick_x or self.old_state.lstick_y != state.lstick_y:
					self.profile.lstick.whole(self, state.lstick_x, state.lstick_y, LSTICK)
			elif not self.buttons & SCButtons.LPADTOUCH:
				if FE_STICK in fe or self.old_state.lpad_x != state.lpad_x or self.old_state.lpad_y != state.lpad_y:
					self.profile.lstick.whole(self, state.lpad_x, state.lpad_y, LSTICK)
			# HAS_RSTICK controllers store the right stick either as a real rstick
			# (Steam Controller 2 / Deck) or, for gamepads on the generic HID decoder
			# (DS4/DS5), as the right pad (pads[RIGHT]). The latter's state struct
			# (HIDControllerInput) has no rstick_* fields, so guard the access:
			# without it every event raised AttributeError here, which aborted the
			# rest of input processing (right pad, triggers, touchpad) -- the reason
			# those controls were dead on the DS4.
			if self.controller.flags & ControllerFlags.HAS_RSTICK and hasattr(state, "rstick_x"):
				if (
					FE_STICK in fe
					or self.old_state.rstick_x != state.rstick_x
					or self.old_state.rstick_y != state.rstick_y
				):
					self.profile.rstick.whole(self, state.rstick_x, state.rstick_y, RSTICK)

			# Check gyro
			if controller.get_gyro_enabled():
				self.profile.gyro.gyro(
					self, state.gpitch, state.gyaw, state.groll, state.q1, state.q2, state.q3, state.q4,
				)

			# Check triggers
			if FE_TRIGGER in fe or state.ltrig != self.old_state.ltrig:
				if SCTriggers.LT in self.profile.triggers:
					self.profile.triggers[SCTriggers.LT].trigger(self, state.ltrig, self.old_state.ltrig)
			if FE_TRIGGER in fe or state.rtrig != self.old_state.rtrig:
				if SCTriggers.RT in self.profile.triggers:
					self.profile.triggers[SCTriggers.RT].trigger(self, state.rtrig, self.old_state.rtrig)

			# Check pads
			# RPAD
			if controller.flags & ControllerFlags.IS_DECK:
				if FE_PAD in fe or self.old_state.rpad_x != state.rpad_x or self.old_state.rpad_y != state.rpad_y:
					self.profile.pads[SCPads.RPAD].whole(self, state.rpad_x, state.rpad_y, SCPads.RPAD)
			elif FE_PAD in fe or self.buttons & SCButtons.RPADTOUCH or SCButtons.RPADTOUCH & btn_rem:
				self.profile.pads[SCPads.RPAD].whole(self, state.rpad_x, state.rpad_y, SCPads.RPAD)
			# DPAD
			if controller.flags & ControllerFlags.HAS_DPAD and hasattr(state, "dpad_x"):
				if FE_PAD in fe or self.old_state.dpad_x != state.dpad_x or self.old_state.dpad_y != state.dpad_y:
					self.profile.pads[DPAD].whole(self, state.dpad_x, state.dpad_y, SCPads.DPAD)

			# LPAD
			if controller.flags & ControllerFlags.SEPARATE_LSTICK:
				if FE_PAD in fe or self.old_state.lpad_x != state.lpad_x or self.old_state.lpad_y != state.lpad_y:
					self.profile.pads[SCPads.LPAD].whole(self, state.lpad_x, state.lpad_y, SCPads.LPAD)
			elif self.buttons & SCButtons.LPADTOUCH:
				# Pad is being touched now
				if not self.lpad_touched:
					self.lpad_touched = True
				self.profile.pads[SCPads.LPAD].whole(self, state.lpad_x, state.lpad_y, SCPads.LPAD)
				if self.old_state.buttons & LSTICKTILT and not self.buttons & LSTICKTILT:
					# LPAD and stick share axes and so when they are used simultaneously (by someone with 3 hands or so :)
					# this is how mapper can tell that stick was recentered
					self.profile.lstick.whole(self, 0, 0, LSTICK)
			elif not self.buttons & LSTICKTILT:
				# Pad is not being touched
				if self.lpad_touched:
					self.lpad_touched = False
					self.profile.pads[SCPads.LPAD].whole(self, 0, 0, SCPads.LPAD)

			# CPAD (touchpad on DS4/DualSense controller)
			if controller.flags & ControllerFlags.HAS_CPAD:
				if (
					(FE_PAD in fe)
					or (self.old_state.cpad_x != state.cpad_x)
					or (self.old_state.cpad_y != state.cpad_y)
					or ((self.old_buttons & SCButtons.CPADTOUCH) and not (self.buttons & SCButtons.CPADTOUCH))
				):
					if self.buttons & SCButtons.CPADTOUCH:
						self.profile.pads[CPAD].whole(self, state.cpad_x, state.cpad_y, SCPads.CPAD)
					elif self.old_buttons & SCButtons.CPADTOUCH:
						self.profile.pads[CPAD].whole(self, 0, 0, SCPads.CPAD)
		except Exception:
			# Log error but don't crash here, it breaks too many things at once
			if hasattr(self, "_testing"):
				raise
			log.error("Error while processing controller event")
			log.error(traceback.format_exc())

		# TODO: Is it important to run scheduled stuff before generate_events?
		self.scheduler.run()
		self.generate_events()
		self.generate_feedback()

	def generate_events(self) -> None:
		# Generate events - keys
		if len(self.keypress_list):
			self.keyboard.pressEvent(self.keypress_list)
			self.keypress_list = []
		if len(self.keyrelease_list):
			self.keyboard.releaseEvent(self.keyrelease_list)
			self.keyrelease_list = []
		# Generate events - mouse
		mx, my, wx, wy, sx, sy = self.mouse_movements
		if mx != 0 or my != 0:
			self.mouse.moveEvent(int(mx), int(my * -1), self.time_elapsed)
			self.syn_list.add(self.mouse)
		if wx != 0 or wy != 0:
			self.mouse.scrollEvent(wx, wy)
			self.syn_list.add(self.mouse)
		if sx != 0 or sy != 0:
			# log.debug("STARTING")
			# log.debug(f"{sx} {sy}")
			self.mouse.moveStickEvent(sx, sy * -1, self.time_elapsed)
			self.syn_list.add(self.mouse)

		self.mouse_movements = [0, 0, 0, 0, 0, 0]
		self.sync()

	def generate_feedback(self) -> None:
		if self.controller:
			left, right = self.feedbacks
			if (
				self.controller.get_type() in ("ds4", "ds4evdev", "ds5evdev")
				and left
				and right
				and left.data[1:] == right.data[1:]
			):
				self.feedbacks = [None, None]
				self.controller.feedback(left.with_position(HapticPos.BOTH))
				return
			for x in (0, 1):
				if self.feedbacks[x]:
					self.controller.feedback(self.feedbacks[x])
					self.feedbacks[x] = None
