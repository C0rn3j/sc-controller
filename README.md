# SC Controller

[![SCC Linux CI](https://github.com/C0rn3j/sc-controller/actions/workflows/scc-linux.yml/badge.svg?branch=python3)](https://github.com/C0rn3j/sc-controller/actions/workflows/scc-linux.yml)
[![Build and publish AppImages](https://github.com/C0rn3j/sc-controller/actions/workflows/appimage.yml/badge.svg?event=release)](https://github.com/C0rn3j/sc-controller/actions/workflows/appimage.yml)

User-mode driver, mapper and GTK3 based GUI for Steam Controller, DS4 and many other controllers.

[![screenshot1](docs/screenshot1-tn.png?raw=true)](docs/screenshot1.png?raw=true)
[![screenshot2](docs/screenshot2-tn.png?raw=true)](docs/screenshot2.png?raw=true)
[![screenshot3](docs/screenshot3-tn.png?raw=true)](docs/screenshot3.png?raw=true)
[![screenshot3](docs/screenshot4-tn.png?raw=true)](docs/screenshot4.png?raw=true)

## Features
- Allows to setup, configure and use the Steam Controller without ever launching Steam
- Connect multiple controllers at the same time, each with its own remembered profile
- Supports profiles switchable in GUI or with controller button
- Stick, Pads and Gyroscope input
- Steam Controller 2 (2026) support, including its capacitive stick-touch and grip sensors — bind actions to them directly, or use them as conditions in mode-shift combinations
- Haptic Feedback and in-game Rumble support
- OSD, Menus, On-Screen Keyboard for desktop *and* in games.
- Automatic profile switching based on active window.
- Macros, button cycling, rapid fire, modeshift, mouse regions, …
- Emulates Xbox360 controller, mouse, trackball and keyboard.

Based on [Standalone Steam Controller Driver](https://github.com/ynsta/steamcontroller) by [Ynsta](https://github.com/ynsta).

## Using multiple controllers

SC Controller can drive several controllers at once — Steam Controllers (v1 and
v2), a DualShock 4 and others can all be connected together.

- **One window, two bars: pick the controller, then its profile.** Just connect
  them: a controller-selector bar lists every connected controller (by type,
  numbered when you have more than one of the same model) together with its
  current profile; choosing one shows it on the big controller image, and a
  second bar sets that controller's profile. There is no separate window per
  device. The controller that connected *first* is the primary one — it is the
  one drawn by default and the target when a command (a menu, the OSD) does not
  name a specific controller.
- **Each controller keeps its own profile.** Selecting a controller and setting
  a profile applies only to that controller. The choice is remembered and
  restored automatically the next time that controller connects, so you do not
  have to re-pick it every session.
- **Disconnecting is safe.** Turning one controller off (or letting it go idle)
  leaves the window and the other controllers untouched; when it comes back it
  returns to its remembered profile.

![SC Controller with three controllers connected](docs/multiple-controllers.jpg?raw=true)

*Two Steam Controller v1s and a Steam Controller v2 connected at once: the
selector at the top lists each controller — numbered when there are duplicates —
alongside its current profile.*

### Telling controllers apart

How a controller is identified — and therefore which remembered profile and
per-controller settings it gets — is governed by **Use Serial Numbers to
Identify Controllers** in *Settings*:

- **Off (default):** controllers are identified by connection order (first
  connected, second connected, …). This is simplest for a fixed setup, but if
  you change which controller powers on first they will swap profiles.
- **On:** each controller is identified by its own hardware serial number, so
  its profile and settings follow the physical device no matter what order
  things connect in.

Turn this **on** when you regularly use more than one controller — especially
two of the same model, such as two Steam Controllers — and want each to reliably
keep its own profile.

## Like what I'm doing?

You can check out the ways to donate on [my website](https://rys.rs/donate), or just go straight to my [Ko-Fi](https://ko-fi.com/martinrys).

Donation links for kozec, who is the original developer, can be found on the [old upstream repository](https://github.com/kozec/sc-controller?tab=readme-ov-file#like-what-im-doing).

## Packages

[![Packaging status](https://repology.org/badge/vertical-allrepos/sc-controller.svg?exclude_unsupported=1)](https://repology.org/project/sc-controller/versions)

Linux:
  - **Arch Linux:** Found in official [extra](https://archlinux.org/packages/extra/x86_64/sc-controller/) repository and [AUR/sc-controller-git](https://aur.archlinux.org/packages/sc-controller-git/)
  - **Ubuntu (24.04-noble, 26.04-resolute):** Packaged as AppImage in [GitHub releases](https://github.com/C0rn3j/sc-controller/releases), ***which may also run fine on other operating systems - noble image is currently the most compatible one***
  - **Gentoo:** Packaged as [game-util/sc-controller](https://packages.gentoo.org/packages/games-util/sc-controller)
  - **Void Linux:** Packaged as [sc-controller](https://github.com/void-linux/void-packages/blob/master/srcpkgs/sc-controller/template) - Run `xbps-install -S sc-controller` in a terminal, points to archived Ryochan7's fork at the time of writing
  - **Others:** You can attempt to use one of the AppImages (try all, AppImages built on older distributions tend to work better), or a package meant for your parent distribution if applicable. Flatpak is planned.

Windows:
  - It should be possible to get it running as per the [wiki](https://github.com/C0rn3j/sc-controller/wiki/Running-SC-Controller-on-Windows), but this is untested and might be broken, report a bug if so


## Building the package by yourself

### Dependencies
  - Python 3.11+
  - GTK 3.24+
  - [PyGObject](https://live.gnome.org/PyGObject)
  - [python-gi-cairo](https://packages.debian.org/sid/python-gi-cairo) and [gir1.2-rsvg-2.0](https://packages.debian.org/sid/gir1.2-rsvg-2.0) on Debian-based distributions (included in PyGObject elsewhere)
  - [setuptools](https://pypi.python.org/pypi/setuptools)
  - [python-evdev](https://python-evdev.readthedocs.io/en/latest/)
  - [python-pylibacl](http://pylibacl.k1024.org/)
  - [python-vdf](https://pypi.org/project/vdf/)
  - [python-libusb1](https://github.com/vpelletier/python-libusb1)
  - [python-ioctl-opt](https://pypi.org/project/ioctl-opt/)
  - [gtk-layer-shell](https://github.com/wmww/gtk-layer-shell)

### Via Python into a local build directory
  - ~~Download and extract [latest release](https://github.com/C0rn3j/sc-controller/releases/latest)~~ .zip releases without .git directory are currently broken - tracked in [#50](https://github.com/C0rn3j/sc-controller/issues/50)
  - Clone the repository `git clone https://github.com/C0rn3j/sc-controller.git` and navigate into it: `cd sc-controller`
  - `python3 -m build --wheel`
  - `python3 -m installer --destdir="./build" dist/*.whl`
  - Run the app via: `SCC_SHARED="${PWD}" PYTHONPATH="./build/usr/lib/python3.12/site-packages" PATH="${PWD}/build/usr/bin:${PATH}" ./build/usr/bin/sc-controller`

### Via Docker
A test build with Docker can be created using the following way:

```bash
docker build -o build-output --build-arg BASE_CODENAME=noble .
```

### Via Python venv through run.sh
  - ~~Download and extract [latest release](https://github.com/C0rn3j/sc-controller/releases/latest)~~ .zip releases without .git directory are currently broken - tracked in [#50](https://github.com/C0rn3j/sc-controller/issues/50)
  - Clone the repository `git clone https://github.com/C0rn3j/sc-controller.git` and navigate into it: `cd sc-controller`
  - Optionally checkout a branch or a tag, like `main`(default) or `v0.6.2`
  - Execute `./run.sh`, this automatically builds the project into a venv called `.env`, activates it and runs sc-controller, which in turn runs scc-daemon if one does not run already
  - If you are debugging an issue, running `./run.sh daemon` first will launch the daemon in debug mode, allowing you to launch sc-controller in another terminal with `./run.sh` - note that sc-controller launched via `run.sh` always runs in debug mode too.

### Regenerating controller artwork (for contributors)

Some SVG assets under `images/` are **generated** from source drawings by scripts
in `tools/`, so edit the source and rerun the script rather than hand-editing the
committed output. All scripts run from the repository root and optimise their
output with [`svgo`](https://github.com/svg/svgo) when it is on `PATH` (optional;
without it the SVGs are just left un-minified). The `svgo` config
(`tools/svgo.config.js`) deliberately preserves the element ids, `<rect>`
geometry, `viewBox` and `display:none` layers that the GUI relies on.

- **`tools/gen_sc2_image.py`** — builds the Steam Controller v2 GUI artwork
  (`images/controller-images/sc2.svg`, the face-button glyphs and side-panel
  icons) from the traced sources in `tools/` (`sc2-source.svg`, `sc2-assets/`).

- **`tools/gen_binding_display.py`** — builds the per-controller *Display Current
  Bindings* templates in `images/binding-display/<gui-background>.svg`. Instead of
  a hand-drawn asset per controller, it derives each template straight from that
  controller's GUI drawing (`images/controller-images/<name>.svg`): it scales the
  drawing into the OSD canvas, recolours it into the binding-display palette
  (green outlines over two greys on a dark backdrop) and drops a marker ring at
  each control's `AREA_*` anchor so the binding boxes can draw connector lines to
  them. The OSD then picks the file up automatically via the controller's gui
  `background` name (see `scc/osd/binding_display.py`, `_resolve_image`).

  To add a controller: give it an entry in the script's `CONTROLLERS` table (its
  source drawing + which `AREA_*` anchors each binding box points at) and a
  matching box layout in `LAYOUTS` in `scc/osd/binding_display.py`, then rerun the
  script. Controllers that share a physical control set can share a layout.
