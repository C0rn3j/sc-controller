"""Generic daemon base class.

Adapted from http://www.jejik.com/files/examples/daemon3x.py

Thanks to the original author.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from typing import Never

log = logging.getLogger(__name__)
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
		except OSError:
			log.exception("Fork #1 failed")
			sys.exit(1)

		# decouple from parent environment
		os.chdir("/")
		os.setsid()
		os.umask(0o077)

		# do second fork
		try:
			pid = os.fork()
			if pid > 0:
				# exit from second parent
				sys.exit(0)
		except OSError:
			log.exception("Fork #2 failed")
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
		"""Start the daemon.

		Check if PID file exists, and if yes, verify the running process PID matches the one in the file.

		If it does not, check if the saved PID is running, if it does and it does not seem to be a PID re-used by another process, terminate the current daemon.
		"""
		# Check for a pidfile to see if the daemon already runs
		pid: int | None = None
		if Path(self.pidfile).exists():
			try:
				with open(self.pidfile) as pidf:
					pid = int(pidf.read().strip())
			except Exception:
				log.exception("Exception opening PID file - TODO(Martin): Rework this mess")

		if pid:
			# Check if PID corresponds to running daemon process and fail if yes
			if sys.platform == "win32":
				try:
					running = self._pid_running_windows(pid)
				except OSError:
					log.exception("Failed checking daemon PID")
					sys.exit(1)
				if running:
					log.warning("TODO(Martin): Check if this is truly our Daemon and not another process re-using the PID")
					log.error(f"PID {pid} saved in {self.pidfile} is running, killing self as another daemon exists.")
					sys.exit(1)
				pid = None
			elif sys.platform == "darwin":
				log.critical("TODO(Martin): PID check on macOS is currently not supported!")
				sys.exit(1)
			elif sys.platform == "linux":
				pidfile_cmdline: str = f"/proc/{pid}/cmdline"
				try:
					if Path(pidfile_cmdline).exists():
						with open(pidfile_cmdline) as file:
							cmdline = file.read().replace("\x00", " ").strip()
						if sys.argv[0] in cmdline:
							log.error(f"PID {pid} saved in {self.pidfile} is running, killing self as another daemon exists.")
							sys.exit(1)
				except Exception:
					log.exception("Exception handling PID check - TODO(Martin): Rework this mess to not raise custom exceptions wth")
					sys.exit(1)
			else:
				log.critical("PID check is not supported on this platform!")
				sys.exit(1)

			log.debug("Overwriting stale pidfile.")

		# Start the daemon
		if not foreground and sys.platform != "win32":
			self.daemonize()
		else:
			self.write_pid()
		log.info("%s: started", os.path.basename(sys.argv[0]))
		self.on_start()
		while True:
			try:
				self.run()
			except Exception:
				log.exception("%s failed", os.path.basename(sys.argv[0]))
			time.sleep(2)

	def on_start(self) -> None:
		pass

	def _pid_running_windows(self, pid: int) -> bool:
		"""Windows check if a PID is running."""
		if pid <= 0 or pid > 0xFFFFFFFF:
			return False
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		open_process = kernel32.OpenProcess
		open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
		open_process.restype = wintypes.HANDLE
		wait = kernel32.WaitForSingleObject
		wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
		wait.restype = wintypes.DWORD
		close = kernel32.CloseHandle
		close.argtypes = [wintypes.HANDLE]
		close.restype = wintypes.BOOL
		handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
		if not handle:
			error = ctypes.get_last_error()
			if error == 87:  # ERROR_INVALID_PARAMETER: PID no longer exists.
				return False
			raise ctypes.WinError(error)
		try:
			state = wait(handle, 0)
			if state == 0xFFFFFFFF:  # WAIT_FAILED
				raise ctypes.WinError(ctypes.get_last_error())
			return state == 258  # WAIT_TIMEOUT: process is still running.
		finally:
			close(handle)

	def stop(self, once: bool = False) -> None:
		"""Stop the daemon."""
		# Get the pid from the pidfile
		pid: int | None = None
		if Path(self.pidfile).exists():
			try:
				with open(self.pidfile) as pidf:
					pid = int(pidf.read().strip())
			except Exception:
				log.exception("Failed opening PID file")

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
		except ProcessLookupError:
			log.debug("Old pidfile seems to point to a PID that is no longer running...")
			if os.path.exists(self.pidfile):
				os.remove(self.pidfile)
		except Exception:
			log.exception("Failed killing scc-daemon")
			sys.exit(1)
		log.info("%s: stopped", os.path.basename(sys.argv[0]))

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
