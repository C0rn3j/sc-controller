#!/usr/bin/env python3
import signal
import sys


def main() -> None:
	def sigint(*a):
		print("\n*break*")
		sys.exit(0)

	signal.signal(signal.SIGINT, sigint)

	from scc.tools import init_logging

	init_logging()

	from scc.osd.message import Message

	m = Message()
	if not m.parse_arguments(sys.argv):
		sys.exit(1)
	m.run()
	sys.exit(m.get_exit_code())


if __name__ == "__main__":
	main()
