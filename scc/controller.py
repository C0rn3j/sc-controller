from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from scc.constants import HapticEffect, HapticPos

if TYPE_CHECKING:
	from scc.drivers.hiddrv import HIDDecoder
	from scc.mapper import Mapper

log = logging.getLogger("SCController")

next_id: int = 1  # Used with fallback controller id generator


class Controller:
	"""Base class for all controller drivers. Implementations are in scc.drivers package.

	Derived class should implement every method from here.
	"""

	flags: int = 0

	def __init__(self) -> None:
		global next_id
		self._decoder: HIDDecoder
		self.mapper: Mapper | None = None
		self._id: int | str = next_id
		next_id += 1
		self.lastTime: float = time.time()
		self.time_elapsed: float = 0.0

	def get_type(self) -> str:
		"""Has to return type identifier

		Returns a short string without spaces
		that describes type of controller which should be unique for each
		driver.
		String is used by UI to assign icons and, along with ID,
		to store controller settings.

		This method has to be overriden.
		"""
		raise RuntimeError("Controller.get_type not overriden")

	def get_id(self) -> int | str:
		"""Returns identifier that has to be unique at least until daemon is restarted.

		Ideally derived from HW device serial number.
		"""
		return self._id

	def get_gui_config_file(self) -> str | None:
		"""Returns file name of json file that GUI can use to load more data about controller

		(background image, button images, available buttons and axes, etc...)
		File name may be absolute path or just name of file in /usr/share/scc

		Returns None if there is no configuration file (GUI will use defaults in such case)
		"""
		return

	def set_mapper(self, mapper: Mapper) -> None:
		"""Sets mapper for controller"""
		self.mapper = mapper

	def get_mapper(self) -> Mapper | None:
		"""Returns mapper set for controller"""
		return self.mapper

	def apply_config(self, config) -> None:
		"""Called from daemon to apply controller configuration stored in config file.

		Does nothing by default.
		"""

	def set_led_level(self, level) -> None:
		"""Configures LED intensity, if supported.

		'level' goes from 0.0 to 100.0
		"""

	def set_gyro_enabled(self, enabled: bool) -> None:
		"""Enables or disables gyroscope, if supported"""

	def get_gyro_enabled(self) -> bool:
		"""Returns True if gyroscope is enabled"""
		return False

	def feedback(self, data) -> None:
		"""Generates feedback effect, if supported.

		'data' is HapticData instance.
		"""

	def rumble(self, strong: int, weak: int, duration_ms: int) -> bool:
		"""Plays continuous game rumble, if the hardware has real rumble motors.

		'strong' and 'weak' are the two FF_RUMBLE magnitudes (0..65535): the
		heavy low-frequency motor and the light high-frequency one. Returns True
		if handled. The default returns False, which makes the mapper fall back
		to emulating rumble as a train of haptic clicks -- the only option on a
		Steam Controller v1, whose "motors" are the pad actuators.
		"""
		return False

	def turnoff(self) -> None:
		"""Turns off controller, if supported"""

	def disconnected(self) -> None:
		"""Called from daemon after controller is disconnected"""


class HapticData:
	"""Simple container to hold haptic feedback settings"""

	def __init__(self, position: HapticPos, amplitude: int = 512, frequency: int = 4, period: int = 1024, count: int = 1,
			effect=HapticEffect.CLICK, duration=200, tone_frequency=160,
			end_frequency=40, lfo_frequency=0, lfo_depth=0, script_id=0) -> None:
		"""'frequency' is used only when emulating touchpad

		and describes how many pixels should mouse travel between two feedback ticks.

		Everything from 'effect' on describes richer effects that only some
		hardware can synthesise, and is ignored by drivers that cannot. They are
		kept out of the 'data' tuple deliberately: that tuple is unpacked
		positionally by existing drivers, so growing it would break them.

		'duration' is in milliseconds; 'tone_frequency', 'end_frequency' and
		'lfo_frequency' in Hz; 'lfo_depth' 0..255; 'script_id' selects a preset
		stored in the controller's own firmware.

		"""
		data: tuple[int, int, int, int] = (int(position), int(amplitude), int(period), int(count))
		if data[0] not in (HapticPos.LEFT, HapticPos.RIGHT, HapticPos.BOTH):
			raise ValueError("Invalid position")
		for i in (1, 2, 3):
			if data[i] > 0x8000 or data[i] < 0:
				raise ValueError("Value out of range: %s", data[i])
		# frequency is multiplied by 1000 just so I don't have big numbers everywhere;
		# it's float until here, so user still can make pad squeak if he wish
		frequency = int(max(1.0, frequency * 1000.0))

		self.data = data  # send to controller
		self.frequency = frequency  # used internally
		self.effect = HapticEffect(effect)
		self.duration = int(duration)
		self.tone_frequency = int(tone_frequency)
		self.end_frequency = int(end_frequency)
		self.lfo_frequency = int(lfo_frequency)
		self.lfo_depth = max(0, min(255, int(lfo_depth)))
		self.script_id = max(0, min(255, int(script_id)))

	def with_position(self, position: HapticPos) -> HapticData:
		"""Creates copy of HapticData with position value changed"""
		trash, amplitude, period, count = self.data
		rv = HapticData(position, amplitude, 1, period, count)
		# self.frequency is already scaled by 1000, so it cannot be handed back
		# to the constructor -- doing so multiplied it again on every copy, and
		# send_feedback() copies for every HapticPos.BOTH effect.
		rv.frequency = self.frequency
		for attr in ("effect", "duration", "tone_frequency", "end_frequency",
				"lfo_frequency", "lfo_depth", "script_id"):
			setattr(rv, attr, getattr(self, attr))
		return rv

	def get_position(self) -> HapticPos:
		return HapticPos(self.data[0])

	def get_amplitude(self):
		return self.data[1]

	def get_frequency(self) -> float:
		return float(self.frequency) / 1000.0

	def get_period(self):
		return self.data[2]

	def get_count(self):
		return self.data[3]

	def __mul__(self, by) -> HapticData:
		"""Allows multiplying HapticData by scalar to get same values with increased amplitude."""
		position, amplitude, period, count = self.data
		amplitude = min(amplitude * by, 0x8000)
		return HapticData(position, amplitude, self.frequency, period, count)
