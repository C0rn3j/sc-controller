#!/usr/bin/env python3
import argparse

from scc.paths import get_daemon_socket, get_pid_file
from scc.sccdaemon import SCCDaemon
from scc.tools import init_logging


def main() -> None:
	"""SCCDaemon launcher."""
	init_logging()
	parser = argparse.ArgumentParser()
	parser.add_argument("profile", type=str, nargs="*")
	parser.add_argument("command", type=str, choices=["start", "stop", "restart", "debug"])
	parser.add_argument("--alone", action="store_true", help="prevent scc-daemon from launching osd-daemon and autoswitch-daemon")
	parser.add_argument("--once", action="store_true", help="use with 'stop' to send single SIGTERM without waiting for daemon to exit")
	parser.add_argument("--foreground", action="store_true", help="run scc-daemon in foreground")
	daemon = SCCDaemon(get_pid_file(), get_daemon_socket())
	args = parser.parse_args()
	daemon.alone = args.alone

	profile = " ".join(args.profile)
	if profile:
		daemon.set_default_profile(profile)
		# If no default_profile is set, daemon will try to load last used
		# from config

	if args.command == "start":
		daemon.start(foreground = args.foreground)
	elif args.command == "stop":
		daemon.stop(once = args.once)
	elif args.command == "restart":
		daemon.restart()
	elif args.command == "debug":
		daemon.debug()


if __name__ == "__main__":
	main()
