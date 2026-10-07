"""Generic daemon base class."""

# Adapted from http://www.jejik.com/files/examples/daemon3x.py
# thanks to the original author
from __future__ import annotations

import atexit
import ctypes
import logging
import os
import signal
import sys
import time
from ctypes import wintypes
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

	def _stop_windows(self, pid: int) -> None:
		"""Terminate and wait using a handle; os.kill(pid, 0) kills on Windows."""
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		open_process = kernel32.OpenProcess
		open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
		open_process.restype = wintypes.HANDLE
		terminate = kernel32.TerminateProcess
		terminate.argtypes = [wintypes.HANDLE, wintypes.UINT]
		terminate.restype = wintypes.BOOL
		wait = kernel32.WaitForSingleObject
		wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
		wait.restype = wintypes.DWORD
		close = kernel32.CloseHandle
		close.argtypes = [wintypes.HANDLE]
		close.restype = wintypes.BOOL

		# PROCESS_TERMINATE | SYNCHRONIZE. Keep the handle while waiting so
		# a recycled PID cannot make us target another process mid-shutdown.
		handle = open_process(0x0001 | 0x00100000, False, pid)
		if not handle:
			error = ctypes.get_last_error()
			if error != 87:  # ERROR_INVALID_PARAMETER: PID no longer exists.
				raise ctypes.WinError(error)
		else:
			try:
				state = wait(handle, 0)
				if state == 0xFFFFFFFF:  # WAIT_FAILED
					raise ctypes.WinError(ctypes.get_last_error())
				if state != 0:  # WAIT_OBJECT_0 means already exited.
					if not terminate(handle, signal.SIGTERM):
						error = ctypes.get_last_error()
						if wait(handle, 0) != 0:
							raise ctypes.WinError(error)
					result = wait(handle, 5000)
					if result == 0xFFFFFFFF:  # WAIT_FAILED
						raise ctypes.WinError(ctypes.get_last_error())
					if result != 0:
						raise TimeoutError(f"Daemon PID {pid} did not exit within 5 seconds")
			finally:
				close(handle)
		# TerminateProcess bypasses the daemon's atexit PID-file cleanup.
		try:
			os.remove(self.pidfile)
		except FileNotFoundError:
			log.exception("PID file not found")

	def stop(self, once: bool = False) -> None:
		"""Stop the daemon."""
		# Get the pid from the pidfile
		try:
			with open(self.pidfile) as pidf:
				pid = int(pidf.read().strip())
		except Exception:
			log.exception("Failed opening PID file")
			pid = None

		if not pid:
			message = "pidfile {0} does not exist. " + "Daemon not running?\n"
			sys.stderr.write(message.format(self.pidfile))
			return  # not an error in a restart

		# Try killing the daemon process
		if sys.platform == "win32":
			try:
				if pid <= 0 or pid > 0xFFFFFFFF:
					raise ValueError(f"Invalid daemon PID: {pid}")
				self._stop_windows(pid)
			except Exception:
				log.exception("Failed killing scc-daemon")
				sys.exit(1)
		else:
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
