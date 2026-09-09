# SC Controller

[![SCC Linux CI](https://github.com/C0rn3j/sc-controller/actions/workflows/scc-linux.yml/badge.svg?branch=python3)](https://github.com/C0rn3j/sc-controller/actions/workflows/scc-linux.yml)
[![Build and publish AppImages](https://github.com/C0rn3j/sc-controller/actions/workflows/appimage.yml/badge.svg?event=release)](https://github.com/C0rn3j/sc-controller/actions/workflows/appimage.yml)

User-mode driver, mapper, and GTK 4 based GUI for game controllers, including but not limited to the Steam Controller (2015 & 2026).

[![screenshot1](docs/screenshot1-tn.png?raw=true)](docs/screenshot1.png?raw=true)
[![screenshot2](docs/screenshot2-tn.png?raw=true)](docs/screenshot2.png?raw=true)
[![screenshot3](docs/screenshot3-tn.png?raw=true)](docs/screenshot3.png?raw=true)
[![screenshot3](docs/screenshot4-tn.png?raw=true)](docs/screenshot4.png?raw=true)

*Based on [Standalone Steam Controller Driver](https://github.com/ynsta/steamcontroller) by [Ynsta](https://github.com/ynsta).*

## Features
- Allows to setup, configure and use the Steam Controller (2015 & 2026) without ever launching Steam
- Connect multiple controllers at the same time
- Supports profiles switchable in GUI or with controller button
- Joystick, Touchpad and Gyroscope input
- Haptic Feedback and in-game Rumble support
- OSD, Menus, On-Screen Keyboard for desktop *and* in games
- Automatic profile switching based on the active window
- Macros, button cycling, rapid fire, modeshift, mouse regions, …
- Emulates the Xbox 360 controller, mouse, trackball and keyboard


### List of supported controllers
Controllers supported via custom drivers:
* Steam Controller (2015, 2026)
* Steam Deck
* DualShock 4 (v1, v2)
* DualSense
* DualSense Edge - untested, lacks support for the [4 extra buttons](https://github.com/C0rn3j/sc-controller/issues/89) at the moment

Controllers without a custom driver work too, you can add one via `Settings -> Controllers -> Register New Controller`.</br>
Your controller will be automatically mapped via SDL's [GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB), which has hundreds of supported devices.</br>
In case support for yours is missing, you should [contribute](https://github.com/mdqinc/SDL_GameControllerDB#contributing) a layout for your controller to it.</br>
Beware that even when you do use the automap feature, instead of the manual option, you still have to go through pressing all the buttons, to set up deadzones and thresholds for inputs like triggers and joysticks.

Note that there is no automatic discovery of connected gyro/touchpad evdev nodes on controllers that do have a gyroscope or a touchpad(s), so if your controller has one of those, it currently needs SCC to implement a custom driver for it.</br>
That does mean that devices like Nintendo controllers do not have a working gyroscope, as I do not own any.

## Like what I'm doing?

You can check out the ways to donate on [my website](https://rys.rs/donate), or just go straight to my [Ko-Fi](https://ko-fi.com/martinrys).

*Donation links for kozec, who is the original developer, can be found on the [old upstream repository](https://github.com/kozec/sc-controller?tab=readme-ov-file#like-what-im-doing).*

## Packages

[![Packaging status](https://repology.org/badge/vertical-allrepos/sc-controller.svg?exclude_unsupported=1)](https://repology.org/project/sc-controller/versions)

Linux:
  - **Arch Linux:** Found in the official [extra](https://archlinux.org/packages/extra/x86_64/sc-controller/) repository and [AUR/sc-controller-git](https://aur.archlinux.org/packages/sc-controller-git/) - Install via `pacman -Syu sc-controller`
  - **Debian:** [Packaged](https://packages.debian.org/sid/sc-controller), but not yet released as stable. Also packaged as an [AppImage](https://github.com/C0rn3j/sc-controller/releases).
  - **Ubuntu (24.04-noble, 26.04-resolute):** Packaged as [AppImage](https://github.com/C0rn3j/sc-controller/releases), ***which usually runs fine on other operating systems - noble image is currently the most compatible one***
  - **Gentoo:** Packaged as [game-util/sc-controller](https://packages.gentoo.org/packages/games-util/sc-controller)
  - **Void Linux:** Packaged as [sc-controller](https://github.com/void-linux/void-packages/blob/master/srcpkgs/sc-controller/template) - Install via `xbps-install -S sc-controller`
  - **Others:** You can attempt to use one of the AppImages (try all, AppImages built on older distributions have better compatibility), or a package meant for your parent distribution if applicable.
  - **Flatpak is planned.**

Windows/macOS:
  - Not planned, the half-finished C rewrite has Windows support but it has been abandoned, see https://github.com/C0rn3j/sc-controller/issues/44 for more info


## Building the package by yourself

### Dependencies
  - Python 3.12+
  - GTK 4.14+
  - [gtk4-layer-shell](https://github.com/wmww/gtk4-layer-shell)
  - [PyGObject](https://live.gnome.org/PyGObject)
  - [python-gi-cairo](https://packages.debian.org/sid/python-gi-cairo) and [gir1.2-rsvg-2.0](https://packages.debian.org/sid/gir1.2-rsvg-2.0) on Debian-based distributions (included in PyGObject elsewhere)
  - [python-evdev](https://python-evdev.readthedocs.io/en/latest/)
  - [python-pylibacl](http://pylibacl.k1024.org/)
  - [python-vdf](https://pypi.org/project/vdf/)
  - [python-libusb1](https://github.com/vpelletier/python-libusb1)
  - [python-hidraw-pure](https://github.com/vpelletier/python-hidraw) - Note: Temporarily vendored as v1.2 can conflict with python-hidapi, but system version is preferred by the code if present
  - [python-ioctl-opt](https://pypi.org/project/ioctl-opt/)
  - [setuptools](https://pypi.python.org/pypi/setuptools)

### Via Python into a local build directory
  - ~~Download and extract [latest release](https://github.com/C0rn3j/sc-controller/releases/latest)~~ .zip releases without .git directory are currently broken - tracked in [#50](https://github.com/C0rn3j/sc-controller/issues/50)
  - Clone the repository `git clone https://github.com/C0rn3j/sc-controller.git` and navigate into it: `cd sc-controller`
  - `python3 -m build --wheel`
  - `python3 -m installer --destdir="./build" dist/*.whl`
  - Run the app via: `SCC_SHARED="${PWD}" PYTHONPATH="./build/usr/lib/python3.14/site-packages" PATH="${PWD}/build/usr/bin:${PATH}" ./build/usr/bin/sc-controller`

### Via Docker
A test build with Docker can be created using the following way:

```bash
docker build -o build-output --build-arg BASE_CODENAME=noble .
```

### Via Python venv through run.sh
  - ~~Download and extract [latest release](https://github.com/C0rn3j/sc-controller/releases/latest)~~ .zip releases without .git directory are currently broken - tracked in [#50](https://github.com/C0rn3j/sc-controller/issues/50)
  - Clone the repository `git clone https://github.com/C0rn3j/sc-controller.git` and navigate into it: `cd sc-controller`
  - Optionally checkout a branch or a tag, like `main`(default) or `v0.6.2`
  - Execute `./run.sh`, this automatically builds the project into a venv called `.venv`, activates it and runs sc-controller, which in turn runs scc-daemon if one does not run already
  - If you are debugging an issue, running `./run.sh daemon` first will launch the daemon in debug mode, allowing you to launch sc-controller in another terminal with `./run.sh` - note that sc-controller launched via `run.sh` always runs in debug mode too.

## AI notice

If you contribute AI-assisted work, please disclose it, ensure you have tested the changes, and do not use unreviewed AI-generated text to communicate with maintainers.

Do **not** use AI-generated text to communicate with maintainers. You should understand and be able to explain your own work. Using AI to improve grammar or clarity is fine, but the substance of your responses must be your own.

If you wish to include context from an interaction with AI in your comments, it should be in a quote block (e.g., using >) and disclosed as such. It must be accompanied by your own commentary explaining the relevance and implications of the context.

## AI disclosure

This project uses AI tools to assist with debugging and writing code. AI output is reviewed, usually edited, and tested before being committed. In short, AI is treated as a development tool.

The exception to this is the contributed Steam Controller (2026) driver, which lives in its separate file, and its associated reverse engineering documentation.
