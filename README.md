# SC Controller

[![SCC Linux CI](https://github.com/C0rn3j/sc-controller/actions/workflows/scc-linux.yml/badge.svg)](https://github.com/C0rn3j/sc-controller/actions/workflows/scc-linux.yml) [![Build and publish AppImages](https://github.com/C0rn3j/sc-controller/actions/workflows/appimage.yml/badge.svg)](https://github.com/C0rn3j/sc-controller/actions/workflows/appimage.yml)

User-mode driver, mapper and GTK3 based GUI for Steam Controller, DS4 and similar controllers.

[![screenshot1](docs/screenshot1-tn.png?raw=true)](docs/screenshot1.png?raw=true)
[![screenshot2](docs/screenshot2-tn.png?raw=true)](docs/screenshot2.png?raw=true)
[![screenshot3](docs/screenshot3-tn.png?raw=true)](docs/screenshot3.png?raw=true)
[![screenshot3](docs/screenshot4-tn.png?raw=true)](docs/screenshot4.png?raw=true)

## Features
- Allows to setup, configure and use Steam Controller(s) without ever launching Steam
- Supports profiles switchable in GUI or with controller button
- Stick, Pads and Gyroscope input
- Haptic Feedback and in-game Rumble support
- OSD, Menus, On-Screen Keyboard for desktop *and* in games.
- Automatic profile switching based on active window.
- Macros, button cycling, rapid fire, modeshift, mouse regions...
- Emulates Xbox360 controller, mouse, trackball and keyboard.

Based on [Standalone Steam Controller Driver](https://github.com/ynsta/steamcontroller) by [Ynsta](https://github.com/ynsta).

## Like what I'm doing?

You can check out the ways to donate on [my website](https://rys.rs/donate), or just go straight to my [Ko-Fi](https://ko-fi.com/martinrys).

Donation links for kozec, who is the original developer, can be found on the [old upstream repository](https://github.com/kozec/sc-controller?tab=readme-ov-file#like-what-im-doing).

## Packages

Linux:
  - **Arch Linux:** Found in [AUR/sc-controller](https://aur.archlinux.org/packages/sc-controller/) and [AUR/sc-controller-git](https://aur.archlinux.org/packages/sc-controller-git/)
  - **Ubuntu (22.04-jammy, 24.04-noble):** Packaged as AppImage in [GitHub releases](https://github.com/C0rn3j/sc-controller/releases), ***which may also run fine on other operating systems - jammy image is currently the most compatible one***
  - **Gentoo:** Packaged as [game-util/sc-controller](https://packages.gentoo.org/packages/games-util/sc-controller)
  - **Void Linux:** Packaged as [sc-controller](https://github.com/void-linux/void-packages/blob/master/srcpkgs/sc-controller/template) - Run `xbps-install -S sc-controller` in a terminal, points to archived Ryochan7's fork at the time of writing
  - **Others:** You can attempt to use one of the AppImages (try all, AppImages built on older distributions tend to work better), or a package meant for your parent distribution if applicable. Flatpak is planned.

Windows:
  - It should be possible to get it running as per the [upstream wiki](https://github.com/kozec/sc-controller/wiki/Running-SC-Controller-on-Windows), but this is untested and might be broken, report a bug if so


## Building the package by yourself

### Dependencies
  - Python 3.8+
  - GTK 3.22+
  - [PyGObject](https://live.gnome.org/PyGObject)
  - [python-gi-cairo](https://packages.debian.org/sid/python-gi-cairo) and [gir1.2-rsvg-2.0](https://packages.debian.org/sid/gir1.2-rsvg-2.0) on Debian-based distributions (included in PyGObject elsewhere)
  - [setuptools](https://pypi.python.org/pypi/setuptools)
  - [python-evdev](https://python-evdev.readthedocs.io/en/latest/)
  - [python-pylibacl](http://pylibacl.k1024.org/)
  - [python-vdf](https://pypi.org/project/vdf/)
  - [python-libusb1](https://github.com/vpelletier/python-libusb1)
  - [python-ioctl-opt](https://pypi.org/project/ioctl-opt/)
  - [gtk-layer-shell](https://github.com/wmww/gtk-layer-shell)

### Installing
  - Download and extract [latest release](https://github.com/C0rn3j/sc-controller/releases/latest)
  - `python3 setup.py build`
  - `python3 setup.py install`


## Running with non distro-specific package
  - Download and extract [latest release](https://github.com/C0rn3j/sc-controller/releases/latest)
  - Navigate to extracted directory and execute `./run.sh`
