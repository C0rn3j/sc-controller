import logging
import os
import time
import traceback

from scc.actions import ButtonAction, GyroAbsAction
from scc.aliases import ALL_AXES, ALL_BUTTONS
from scc.config import Config
from scc.constants import (
	CPAD,
	DPAD,
	FE_PAD,
	FE_STICK,
	FE_TRIGGER,
	GYRO,
	LEFT,
	RIGHT,
	RSTICK,
	STICK,
	STICK_PAD_MAX,
	STICKTILT,
	ControllerFlags,
	HapticPos,
	SCButtons,
)
from scc.controller import HapticData
from scc.lib import xwrappers as X
from scc.profile import Profile
from scc.uinput import Dummy, Keyboard, Mouse, Rels, UInput

log = logging.getLogger("Mapper")

class Mapper:
	DEBUG = False

	def __init__(self, profile, scheduler, keyboard=b"SCController Keyboard",
				mouse=b"SCController Mouse",
				gamepad=True, poller=None):
		"""If any of keyboard, mouse or gamepad is set to None, that device will not be emulated.

		Emulated gamepad will have rumble enabled only if poller is set to instance and configuration allows it.
		"""
		self.profile = profile
		self.controller = None
		self.xdisplay = None
		self.scheduler = scheduler

		# Create virtual devices
		log.debug("Creating virtual devices")
		self.keyboard = self.create_keyboard(keyboard) if keyboard else Dummy()
		log.debug("Keyboard: %s" % (self.keyboard, ))
		self.mouse = self.create_mouse(mouse) if mouse else Dummy()
		log.debug("Mouse:    %s" % (self.mouse, ))
		self.gamepad = self.create_gamepad(gamepad, poller) if gamepad else Dummy()
		log.debug("Gamepad:  %s" % (self.gamepad, ))

		# Set by SCCDaemon instance; Used to handle actions
		# from scc.special_actions
		self._sa_handler = None

		# Setup emulation
		self.keypress_list = []
		self.keyrelease_list = []
		self.mouse_movements = [0, 0, 0, 0, 0, 0]		# mouse x, y, wheel vertical, horisontal, stick mouse x, stick mouse y
		self.feedbacks = [ None, None ]			# left, right
		self.pressed = {}						# for ButtonAction, holds number of times virtual button was pressed without releasing it first
		self.syn_list = set()
		self.buttons, self.old_buttons = 0, 0
		self.lpad_touched = False
		self.state, self.old_state = None, None
		self.force_event = set()
		self.time_elapsed = 0.0


	def create_gamepad(self, enabled, poller):
		""" Parses gamepad configuration and creates apropriate unput device """
		if not enabled or "SCC_NOGAMEPAD" in os.environ:
			# Completly undocumented and for debuging purposes only.
			# If set, no gamepad is emulated
			self.gamepad = Dummy()
			return
		cfg = Config()
		keys = ALL_BUTTONS[0:cfg["output"]["buttons"]]
		vendor = int(cfg["output"]["vendor"], 16)
		product = int(cfg["output"]["product"], 16)
		version = int(cfg["output"]["version"], 16)
		name = cfg["output"]["name"]
		rumble = cfg["output"]["rumble"] and poller != None
		axes = []
		i = 0
		for min, max in cfg["output"]["axes"]:
			fuzz, flat = 0, 0
			if abs(max - min) > STICK_PAD_MAX:
				fuzz, flat = 16, 128
			try:
				axes.append(( ALL_AXES[i], min, max, fuzz, flat ))
			except IndexError:
				# Out of axes
				break
			i += 1

		ui = UInput(vendor=vendor, product=product, version=version,
			name=name, keys=keys, axes=axes, rels=[], rumble=rumble)
		if poller and rumble:
			poller.register(ui.getDescriptor(), poller.POLLIN, self._rumble_ready)
		return ui


	def create_keyboard(self, name):
		return Keyboard(name=name)


	def create_mouse(self, name):
		return Mouse(name=name)


	def _rumble_ready(self, fd, event):
		# Taken from Steam Controller Singer project
		# https://gitlab.com/Pilatomic/SteamControllerSinger
		STEAM_CONTROLLER_MAGIC_PERIOD_RATIO = 495483.0
		ef = self.gamepad.ff_read()
		if ef:	# tale of...
			period_command = 0
			amplitude = 0
			if ef.level != 0:
				tempRatio = ef.level / 32767.5
				period_command = ((6000 - 25000) * tempRatio + 25000)
				amplitude = ((900 - 600) * tempRatio + 600);

			raw_period = period_command / STEAM_CONTROLLER_MAGIC_PERIOD_RATIO
			#duration_seconds = 1
			duration_seconds = ef.duration / 1000.0 * ef.repetitions
			count = 0
			if raw_period != 0:
				count = min(int(duration_seconds * 1.5 / raw_period), 0x7FFF)

			#log.debug(f"{ef.level} {ef.duration} {ef.repetitions} {count}")
			self.send_feedback(HapticData(
				HapticPos.BOTH,
				period = period_command,
				amplitude = amplitude,
				count = count,
				#period = 20000,
				#amplitude = max(0, ef.level),
				#count = min(0x7FFF, ef.duration * ef.repetitions / 30)
			))


	def get_gamepad_name(self):
		"""
		Returns name of emulated gamepad (as displayed by jstest & co)
		or None if Dummy is assigned.
		"""
		if isinstance(self.gamepad, Dummy):
			return None
		return self.gamepad.name


	def sync(self):
		""" Syncs generated events """
		if len(self.syn_list):
			for dev in self.syn_list:
				dev.synEvent()
			self.syn_list = set()


	def set_controller(self, c):
		""" Sets controller device, used by some (one so far) actions """
		self.controller = c


	def get_controller(self):
		""" Returns assigned controller device or None if no controller is set """
		return self.controller


	def set_special_actions_handler(self, sa):
		self._sa_handler = sa


	def get_special_actions_handler(self):
		return self._sa_handler


	def set_xdisplay(self, x):
		self.xdisplay = x


	def get_xdisplay(self):
		return self.xdisplay


	def get_current_window(self):
		"""
		Returns window id of current window or None if xdisplay is not set
		"""
		if self.xdisplay:
			return X.get_current_window(self.xdisplay)
		return None


	def schedule(self, delay, cb):
		"""
		Schedules callback to be ran no sooner than after delay.
		Delay is float number in seconds.
		Callback is called with mapper as only argument.
		"""
		return self.scheduler.schedule(delay, cb, self)


	def cancel_task(self, task):
		""" Removes scheduled task. """
		return self.scheduler.cancel_task(task)


	def mouse_move(self, dx, dy):
		"""
		Schedules mouse movement to be done at end of processing callback.
		Called from actions while callback is being processed.
		"""
		self.mouse_movements[0] += dx
		self.mouse_movements[1] += dy


	def mouse_wheel(self, wx, wy):
		"""
		Schedules mouse wheel movement to be done at end of processing callback.
		Called from actions while callback is being processed.
		"""
		self.mouse_movements[2] += wx
		self.mouse_movements[3] += wy


	def mouse_move_stick(self, dx, dy):
		"""
		Schedules mouse movement to be done at end of processing callback.
		Called from actions while callback is being processed.
		"""
		self.mouse_movements[4] += dx
		self.mouse_movements[5] += dy


	def send_feedback(self, hapticdata):
		"""
		Schedules haptic feedback to be sent at end of processing callback.
		Called from actions while callback is being processed.
		"""
		if hapticdata.get_position() == HapticPos.BOTH:
			# HapticPos.BOTH is special case as controller doesn't
			# really support doing that by itself.
			self.feedbacks[0]  = hapticdata.with_position(HapticPos.LEFT)
			self.feedbacks[1]  = hapticdata.with_position(HapticPos.RIGHT)
		else:
			self.feedbacks[hapticdata.get_position()] = hapticdata


	def controller_flags(self):
		"""
		Returns controller flags or, if there is no controller set to
		this mapper, sc_by_cable driver matching defaults.
		"""
		return 0 if self.controller is None else self.controller.flags


	def is_touched(self, what) -> bool:
		"""
		Returns True if specified pad is being touched.
		May randomly return False for aphephobic pads.

		'what' should be LEFT or RIGHT (from scc.constants)
		"""
		if what == LEFT:
			return self.buttons & SCButtons.LPADTOUCH
		elif what == RIGHT:
			return self.buttons & SCButtons.RPADTOUCH
		elif what == CPAD:
			return self.buttons & SCButtons.CPADTOUCH
		else:
			return False


	def was_touched(self, what):
		"""
		As is_touched, but returns True if pad *was* touched
		in previous known state.

		This is used as:
		is_touched() and not was_touched() -> pad was just pressed
		not is_touched() and was_touched() -> pad was just released
		"""
		if what == LEFT:
			return self.old_buttons & SCButtons.LPADTOUCH
		elif what == RIGHT:
			return self.old_buttons & SCButtons.RPADTOUCH
		elif what == CPAD:
			return self.old_buttons & SCButtons.CPADTOUCH
		else:
			return False


	def is_pressed(self, button):
		"""
		Returns True if button is pressed
		"""
		if button == LEFT:
			button = SCButtons.LPAD
		elif button == RIGHT:
			button = SCButtons.RPAD
		return self.buttons & button


	def was_pressed(self, button):
		"""
		Returns True if button was pressed in previous known state
		"""
		if button == LEFT:
			button = SCButtons.LPAD
		elif button == RIGHT:
			button = SCButtons.RPAD
		return self.old_buttons & button


	def get_pressed_button(self):
		"""
		Gets button that was pressed by very last handled event or None,
		if last event doesn't involved button pressing.
		"""
		for x in SCButtons:
			if x & self.buttons & ~self.old_buttons:
				return x
		return None


	def set_button(self, button, state):
		"""
		Sets button state on input.
		Set value will stay only for durration of one event loop iteration.

		Used _temporarely_ by RingAction to emulate finger lifting from pad.
		"""
		if button == LEFT:
			button = SCButtons.LPADTOUCH
		elif button == RIGHT:
			button = SCButtons.RPADTOUCH

		if state:
			self.buttons |= button
		else:
			self.buttons &= ~button


	def set_was_pressed(self, button, state):
		"""
		As set_button, but changes value remembered
		from loop iteration before current.

		Used _temporarely_ by RingAction to emulate finger lifting from pad.
		"""
		if button == LEFT:
			button = SCButtons.LPADTOUCH
		elif button == RIGHT:
			button = SCButtons.RPADTOUCH

		if state:
			self.old_buttons |= button
		else:
			self.old_buttons &= ~button


	def release_virtual_buttons(self):
		"""
		Called when daemon is killed or USB dongle is disconnected.
		Sends button release event for every virtual button that is still being
		pressed.
		"""
		to_release, self.pressed = self.pressed, {}
		for x in to_release:
			ButtonAction._button_release(self, x, True)


	def cancel_all(self):
		"""
		Called when profile is changed to let all actions to cancel
		long-running effects they may have created
		"""
		for a in self.profile.get_actions():
			a.cancel(self)


	def reset_gyros(self):
		for a in self.profile.get_all_actions():
			if isinstance(a, GyroAbsAction):
				a.reset()


	def input(self, controller, old_state, state):
#		print(type(controller), type(old_state), type(state))
		# Store states
		self.old_state = old_state
		self.old_buttons = self.buttons

		self.state = state
		self.buttons = state.buttons

		t = time.time()
		controller.time_elapsed = self.time_elapsed = t - controller.lastTime
		controller.lastTime = t

		if self.buttons & SCButtons.LPAD and not self.buttons & (SCButtons.LPADTOUCH | STICKTILT):
			self.buttons = (self.buttons & ~SCButtons.LPAD) | SCButtons.STICKPRESS

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
			if self.controller.flags & ControllerFlags.SEPARATE_STICK:
				if FE_STICK in fe or self.old_state.stick_x != state.stick_x or self.old_state.stick_y != state.stick_y:
					self.profile.stick.whole(self, state.stick_x, state.stick_y, STICK)
			elif not self.buttons & SCButtons.LPADTOUCH:
				if FE_STICK in fe or self.old_state.lpad_x != state.lpad_x or self.old_state.lpad_y != state.lpad_y:
					self.profile.stick.whole(self, state.lpad_x, state.lpad_y, STICK)
			if self.controller.flags & ControllerFlags.IS_DECK:
				if FE_STICK in fe or self.old_state.rstick_x != state.rstick_x or self.old_state.rstick_y != state.rstick_y:
					self.profile.rstick.whole(self, state.rstick_x, state.rstick_y, RSTICK)

			# Check gyro
			if controller.get_gyro_enabled():
				self.profile.gyro.gyro(self, state.gpitch, state.gyaw, state.groll, state.q1, state.q2, state.q3, state.q4)

			# Check triggers
			if FE_TRIGGER in fe or state.ltrig != self.old_state.ltrig:
				if LEFT in self.profile.triggers:
					self.profile.triggers[LEFT].trigger(self, state.ltrig, self.old_state.ltrig)
			if FE_TRIGGER in fe or state.rtrig != self.old_state.rtrig:
				if RIGHT in self.profile.triggers:
					self.profile.triggers[RIGHT].trigger(self, state.rtrig, self.old_state.rtrig)

			# Check pads
			# RPAD
			if controller.flags & ControllerFlags.IS_DECK:
				if FE_PAD in fe or self.old_state.rpad_x != state.rpad_x or self.old_state.rpad_y != state.rpad_y:
					self.profile.pads[RIGHT].whole(self, state.rpad_x, state.rpad_y, RIGHT)
			elif controller.flags & ControllerFlags.HAS_RSTICK:
				if FE_PAD in fe or self.old_state.rpad_x != state.rpad_x or self.old_state.rpad_y != state.rpad_y:
					self.profile.pads[RIGHT].whole(self, state.rpad_x, state.rpad_y, RIGHT)
			elif FE_PAD in fe or self.buttons & SCButtons.RPADTOUCH or SCButtons.RPADTOUCH & btn_rem:
				self.profile.pads[RIGHT].whole(self, state.rpad_x, state.rpad_y, RIGHT)
			# DPAD
			if controller.flags & ControllerFlags.IS_DECK:
				if FE_PAD in fe or self.old_state.dpad_x != state.dpad_x or self.old_state.dpad_y != state.dpad_y:
					self.profile.pads[DPAD].whole(self, state.dpad_x, state.dpad_y, DPAD)

			# LPAD
			if self.controller.flags & ControllerFlags.SEPARATE_STICK:
				if FE_PAD in fe or self.old_state.lpad_x != state.lpad_x or self.old_state.lpad_y != state.lpad_y:
					self.profile.pads[LEFT].whole(self, state.lpad_x, state.lpad_y, LEFT)
			else:
				if self.buttons & SCButtons.LPADTOUCH:
					# Pad is being touched now
					if not self.lpad_touched:
						self.lpad_touched = True
					self.profile.pads[LEFT].whole(self, state.lpad_x, state.lpad_y, LEFT)
					if self.old_state.buttons & STICKTILT and not self.buttons & STICKTILT:
						# LPAD and stick share axes and so when they are used simultaneously (by someone with 3 hands or so :)
						# this is how mapper can tell that stick was recentered
						self.profile.stick.whole(self, 0, 0, STICK)
				elif not self.buttons & STICKTILT:
					# Pad is not being touched
					if self.lpad_touched:
						self.lpad_touched = False
						self.profile.pads[LEFT].whole(self, 0, 0, LEFT)

			# CPAD (touchpad on DS4 controller)
			if controller.flags & ControllerFlags.HAS_CPAD:
				if ((FE_PAD in fe)
						or (self.old_state.cpad_x != state.cpad_x)
						or (self.old_state.cpad_y != state.cpad_y)
						or ((self.old_buttons & SCButtons.CPADTOUCH) and not (self.buttons & SCButtons.CPADTOUCH))
					):
					if self.buttons & SCButtons.CPADTOUCH:
						self.profile.pads[CPAD].whole(self, state.cpad_x, state.cpad_y, CPAD)
					elif self.old_buttons & SCButtons.CPADTOUCH:
						self.profile.pads[CPAD].whole(self, 0, 0, CPAD)
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


	def generate_events(self):
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
			#log.debug("STARTING")
			#log.debug(f"{sx} {sy}")
			self.mouse.moveStickEvent(sx, sy * -1, self.time_elapsed)
			self.syn_list.add(self.mouse)

		self.mouse_movements = [ 0, 0, 0, 0, 0, 0 ]
		self.sync()


	def generate_feedback(self):
		if self.controller:
			for x in (0, 1):
				if self.feedbacks[x]:
					self.controller.feedback(self.feedbacks[x])
					self.feedbacks[x] = None
