#!/usr/bin/env python3
import os
import signal
import sys


def main() -> None:
	def sigint(*a):
		print("\n*break*")
		sys.exit(0)

	signal.signal(signal.SIGINT, sigint)

	from scc.paths import get_share_path
	from scc.tools import init_logging

	init_logging()

	#import gi
	#gi.require_version("Gtk", "4.0")
	#from gi.repository import Gtk

	ui_files = os.path.join(get_share_path(), "ui")
	images = os.path.join(get_share_path(), "images")
	# GObject.threads_init()

	from scc.gui.app import App

	App(ui_files, images).run(sys.argv)


if __name__ == "__main__":
	main()
