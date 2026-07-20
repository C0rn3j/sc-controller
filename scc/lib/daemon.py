"""Generic linux daemon base class."""

# Adapted from http://www.jejik.com/files/examples/daemon3x.py
# thanks to the original author
from __future__ import annotations

import atexit
import os
import signal
import sys
import syslog
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from typing import Never

class Daemon:
	"""A generic daemon class.

	Usage: subclass the daemon class and override the run() method.
	"""

	def __init__(self, pidfile: str) -> None:
		self.pidfile: str = pidfile

	def daemonize(self) -> None:
		"""Deamonize class. UNIX double fork mechanism."""
		try:
			pid = os.fork()
			if pid > 0:
				# exit first parent
				sys.exit(0)
		except OSError as err:
			sys.stderr.write(f"fork #1 failed: {err}\n")
			sys.exit(1)

		# decouple from parent environment
		os.chdir("/")
		os.setsid()
		os.umask(0)

		# do second fork
		try:
			pid = os.fork()
			if pid > 0:
				# exit from second parent
				sys.exit(0)
		except OSError as err:
			sys.stderr.write(f"fork #2 failed: {err}\n")
			sys.exit(1)

		# redirect standard file descriptors
		sys.stdout.flush()
		sys.stderr.flush()
		stdi = open(os.devnull)
		stdo = open(os.devnull, "a+")
		stde = open(os.devnull, "a+")

		os.dup2(stdi.fileno(), sys.stdin.fileno())
		os.dup2(stdo.fileno(), sys.stdout.fileno())
		os.dup2(stde.fileno(), sys.stderr.fileno())

		# write pidfile
		self.write_pid()

	def write_pid(self) -> None:
		"""Write pid file"""
		atexit.register(self.delpid)

		pid = str(os.getpid())
		with open(self.pidfile, "w+") as fd:
			fd.write(pid + "\n")

	def delpid(self) -> None:
		"""Delete pid file"""
		os.remove(self.pidfile)

	def start(self, foreground: bool = False) -> Never:
		"""Start the daemon."""
		# Check for a pidfile to see if the daemon already runs
		try:
			with open(self.pidfile) as pidf:
				pid = int(pidf.read().strip())
		except Exception:
			pid = None

		if pid:
			# Check if PID coresponds to running daemon process and fail if yes
			try:
				assert os.path.exists("/proc")  # Just in case of BSD...
				with open(f"/proc/{pid}/cmdline") as file:
					cmdline = file.read().replace("\x00", " ").strip()
				if sys.argv[0] in cmdline:
					raise Exception("already running")
			except OSError:
				# No such process
				pass
			except Exception:
				message = "pidfile {0} already exist. " + "Daemon already running?\n"
				sys.stderr.write(message.format(self.pidfile))
				sys.exit(1)

			sys.stderr.write("Overwriting stale pidfile\n")

		# Start the daemon
		if not foreground:
			self.daemonize()
		else:
			self.write_pid()
		syslog.syslog(syslog.LOG_INFO, f"{os.path.basename(sys.argv[0])}: started")
		self.on_start()
		while True:
			try:
				self.run()
			except Exception as e:  # pylint: disable=W0703
				syslog.syslog(syslog.LOG_ERR, f"{os.path.basename(sys.argv[0])}: {e!s}")
			time.sleep(2)

	def on_start(self) -> None:
		pass

	def stop(self, once: bool = False) -> None:
		"""Stop the daemon."""
		# Get the pid from the pidfile
		try:
			with open(self.pidfile) as pidf:
				pid = int(pidf.read().strip())
		except Exception:
			pid = None

		if not pid:
			message = "pidfile {0} does not exist. " + "Daemon not running?\n"
			sys.stderr.write(message.format(self.pidfile))
			return  # not an error in a restart

		# Try killing the daemon process
		try:
			for _x in range(10):  # Waits max 1s
				os.kill(pid, signal.SIGTERM)
				if once:
					break
				for _y in range(50):
					os.kill(pid, 0)
					time.sleep(0.1)
				time.sleep(0.1)
			os.kill(pid, signal.SIGKILL)
		except OSError as err:
			e = str(err.args)
			if e.find("No such process") > 0:
				if os.path.exists(self.pidfile):
					os.remove(self.pidfile)
			else:
				print(str(err.args))
				sys.exit(1)
		syslog.syslog(syslog.LOG_INFO, f"{os.path.basename(sys.argv[0])}: stopped")

	def restart(self) -> Never:
		"""Restart the daemon."""
		self.stop()
		time.sleep(2)
		self.start()

	def run(self) -> None:
		"""You should override this method when you subclass Daemon.

		It will be called after the process has been daemonized by
		start() or restart().
		"""
