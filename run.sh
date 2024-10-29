#!/usr/bin/env bash
set -euo pipefail

Red='\033[0;31m'
Green='\033[0;32m'
Yellow='\033[0;33m'
Purple='\033[0;35m'
NoColor='\033[0m'

function testDeps() {
	# Tests if dependencies are present on the system before attempting to build
#	if ! command -v python3-config >/dev/null; then
#		echo -e "${Red}python3-config not found, install it. ${Yellow}The package may be named python3-dev / python-dev on your distribution!${NoColor}"
#		exit 1
#	fi
#	if ! python -c "import importlib.util; exit(0 if importlib.util.find_spec('usb1') is not None else 1)"; then
#		echo -e "${Red}python3-libusb1 not found, install it. ${Yellow}The package may be named python-libusb1 on your distribution!${NoColor}"
#		exit 1
#	fi
	if ! python -c "import importlib.util; exit(0 if importlib.util.find_spec('setuptools') else 1)"; then
		echo -e "${Red}python3-setuptools not found, install it. ${Yellow}The package may be named python-setuptools on your distribution!${NoColor}"
		exit 1
	fi
#	if ! python -c "import importlib.util; exit(0 if importlib.util.find_spec('gi') else 1)"; then
#		echo -e "${Red}python3-gi not found, install it. ${Yellow}The package may be named python-gi on your distribution!${NoColor}"
#		exit 1
#	fi
#	if ! python -c "import importlib.util; exit(0 if importlib.util.find_spec('cairo') is not None else 1)"; then
#		echo -e "${Red}python3-gi-cairo not found, install it. ${Yellow}The package may be named python3-gobject or python-gobject on your distribution!${NoColor}"
#		exit 1
#	fi
#	if ! python -c "import importlib.util; exit(0 if importlib.util.find_spec('ioctl_opt') is not None else 1)"; then
#		echo -e "${Red}python3-ioctl-opt not found, install it. ${Yellow}The package may be named or python-ioctl-opt on your distribution, ioctl-opt on PyPi!${NoColor}"
#		exit 1
#	fi
#	if ! python -c "import importlib.util; exit(0 if importlib.util.find_spec('evdev') is not None else 1)"; then
#		echo -e "${Red}python3-evdev not found, install it. ${Yellow}The package may be named or python-evdev on your distribution!${NoColor}"
#		exit 1
#	fi
	# https://stackoverflow.com/a/48006925/8962143
	#import gi
	#gi.require_version("Gtk", "3.0")
	#from gi.repository import Gtk
	# + Another gi.require_version('Rsvg', '2.0') -> Rsvg -> gir1.2-rsvg-2.0 on Debian
#	if ! python -c "import importlib.util; exit(0 if (lambda: (__import__('gi').require_version('Gtk', '3.0') or __import__('gi').repository.Gtk)) is not None else 1)"; then
#		echo -e "${Red}gi.Gtk not found, install it. ${Yellow}The package may be named gtk3 or gir1.2-gtk-3.0 on your distribution!${NoColor}"
#		exit 1
#	fi
	if ! command -v x86_64-pc-linux-gnu-gcc >/dev/null; then
		echo -e "${Red}x86_64-pc-linux-gnu-gcc not found, install it. ${Yellow}The package is usually named gcc!${NoColor}"
		exit 1
	fi
}

testDeps

# Ensure correct cwd
cd "$(dirname "$0")"

#export PYTHONPATH="${PWD}:${PWD}/env:${PYTHONPATH-}"
export PYTHONPATH=".":"${PYTHONPATH-}"
export SCC_SHARED="${PWD}"
#export PATH="${PWD}/.env/bin:${PATH}"

rm -rf dist
python -m venv .env
source .env/bin/activate
pip install -r requirements.txt
pip install build
python -m build --wheel
#python -m installer --destdir=".env" dist/*.whl
pip install --prefix ".env" dist/*.whl --force-reinstall

# Start either the daemon in debug mode if first parameter is 'debug', or the regular sc-controller app
if [[ ${1-} == 'daemon' ]]; then
	# Kill any existing daemons before spawning our own
	pkill -f scc-daemon || true
	scc-daemon debug
else
	sc-controller $@
fi
