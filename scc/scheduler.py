"""SC Controller - Scheduler

Centralized scheduler that should be used everywhere.
Runs in SCCDaemon's (single-threaded) mainloop. That means all callbacks are
also called on main thread.

Use schedule(delay, callback, *data) to register one-time task.
"""
from __future__ import annotations

import logging
import queue
import time

log = logging.getLogger("Scheduler")

# TODO: Maybe create actual thread for this? Use poler? Scrap everything and rewrite it in GO?


class Scheduler:
	def __init__(self) -> None:
		self._scheduled = queue.PriorityQueue()
		self._next = None
		self._now: float = time.time()

	def schedule(self, delay, callback, *data) -> Task:
		"""Schedules one-time task to be executed no sooner than after 'delay' of seconds.

		Delay may be float number. 'callback' is called as callback(*data).

		Returned Task instance can be used to cancel task once scheduled.
		"""
		task = Task(self._now + delay, callback, data)
		if self._next is None or task.time < self._next.time:
			if self._next:
				self._scheduled.put(self._next)
			self._next = task
		else:
			self._scheduled.put(task)
		return task

	def cancel_task(self, task: Task) -> bool:
		"""Returns True if task was sucessfully removed or False if task was already executed or not known at all.

		Note that this is slow as hell and completly thread-unsafe,
		so it _has_ to be called on main thread.
		"""
		if task == self._next:
			self._next = None if self._scheduled.empty() else self._scheduled.get()
			return True
		# Fun part: All tasks are removed from PriorityQueue
		# until correct is found. Then everything is put back
		tasks, found = [], False
		while not self._scheduled.empty():
			t = self._scheduled.get()
			if t == task:
				found = True
				break
			tasks.append(t)
		for t in tasks:
			self._scheduled.put(t)
		return found

	def run(self) -> None:
		self._now = time.time()
		while self._next and self._now >= self._next.time:
			callback, data = self._next.callback, self._next.data
			self._next = None if self._scheduled.empty() else self._scheduled.get()
			callback(*data)

	def get_poll_timeout(self, maximum: float = 0.01) -> float:
		"""Return a poll timeout that wakes the main loop for the next task."""
		if self._next is None:
			return maximum
		return max(0.0, min(maximum, self._next.time - time.time()))


class Task:
	def __init__(self, time, callback, data) -> None:
		self.time = time
		self.callback = callback
		self.data = data

	def cancel(self) -> None:
		"""Marks task as canceled, without actually removing it from scheduler"""
		self.callback = lambda *a, **b: False
		self.data = ()

	def __lt__(self, other) -> None:
		self.time < other.time
