"""SC Controller - Scheduler

Centralized scheduler that should be used everywhere.
Callbacks are executed on the main thread via run(). The schedule()
method may be called from any thread (e.g. socket handler threads).

Use schedule(delay, callback, *data) to register one-time task.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

log = logging.getLogger("Scheduler")

# TODO: Maybe create actual thread for this? Use poler? Scrap everything and rewrite it in GO?


class Scheduler:
	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._scheduled = queue.PriorityQueue()
		self._next = None
		self._now: float = time.time()
		self._seq = 0

	def schedule(self, delay, callback, *data) -> Task:
		"""Schedules one-time task to be executed no sooner than after 'delay' of seconds.

		Delay may be float number. 'callback' is called as callback(*data).

		Returned Task instance can be used to cancel task once scheduled.
		"""
		with self._lock:
			task = Task(self._now + delay, self._seq, callback, data)
			self._seq += 1
			if self._next is None or task.time < self._next.time:
				if self._next:
					self._scheduled.put(self._next)
				self._next = task
			else:
				self._scheduled.put(task)
			return task

	def cancel_task(self, task: Task) -> bool:
		"""Returns True if task was sucessfully removed or False if task was already executed or not known at all.

		Note that this is slow as hell, so it _has_ to be called on
		main thread.
		"""
		with self._lock:
			if task == self._next:
				self._next = None if self._scheduled.empty() else self._scheduled.get()
				return True
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
		while True:
			with self._lock:
				if not (self._next and self._now >= self._next.time):
					break
				callback, data = self._next.callback, self._next.data
				self._next = (None if self._scheduled.empty()
					else self._scheduled.get())
			callback(*data)


class Task:
	def __init__(self, time, seq, callback, data) -> None:
		self.time = time
		self.seq = seq
		self.callback = callback
		self.data = data

	def cancel(self) -> None:
		"""Marks task as canceled, without actually removing it from scheduler"""
		self.callback = lambda *a, **b: False
		self.data = ()

	def __lt__(self, other) -> None:
		if self.time != other.time:
			return self.time < other.time
		return self.seq < other.seq
