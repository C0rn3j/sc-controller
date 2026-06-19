<p align="center">
	<img src="images/sc-controller.svg?raw=true" width="192" alt="SC Controller icon">
</p>

<p align="center">
	<b>SC Controller</b>　// A powerful tool for all of your game controllers
</p>

<p align="center">
	<a href="https://ko-fi.com/martinrys">
		<img src="https://img.shields.io/badge/Ko--fi-Support%20development-8B5CF6?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-Fi">
	</a>
	<a href="https://discord.gg/Np7pgfTX6">
		<img src="https://img.shields.io/discord/1540822420104028200.svg?color=a483ef&style=for-the-badge" alt="Discord">
	</a>
	<a href="https://github.com/C0rn3j/sc-controller/actions/workflows/scc-linux.yml">
		<img src="https://img.shields.io/github/actions/workflow/status/C0rn3j/sc-controller/scc-linux.yml?branch=main&amp;style=for-the-badge&amp;label=CI%20tests" alt="CI tests">
	</a>
	<a href="https://github.com/C0rn3j/sc-controller/actions/workflows/appimage.yml">
		<img src="https://img.shields.io/github/actions/workflow/status/C0rn3j/sc-controller/appimage.yml?event=release&amp;style=for-the-badge&amp;label=AppImage" alt="Build and publish AppImages">
	</a>
</p>

<p align="center">
	<a href="docs/screenshot1.png?raw=true">
		<img src="docs/screenshot1.png?raw=true" width="320" alt="Screenshot 1">
	</a>
	<a href="docs/screenshot2.png?raw=true">
		<img src="docs/screenshot2.png?raw=true" width="320" alt="Screenshot 2">
	</a>
	<a href="docs/screenshot3.png?raw=true">
		<img src="docs/screenshot3.png?raw=true" width="320" alt="Screenshot 3">
	</a>
	<a href="docs/screenshot4.png?raw=true">
		<img src="docs/screenshot4.png?raw=true" width="320" alt="Screenshot 4">
	</a>
</p>

## Features
User-mode driver, mapper, and GTK 4 based GUI for game controllers, including but not limited to the Steam Controller (2015 &amp; 2026).

- Allows to setup, configure and use the Steam Controller (2015 & 2026) without ever launching Steam
- Emulates the Xbox 360 controller, mouse, trackball and keyboard
- Connect multiple controllers at the same time, each with its own remembered profile
- Supports profiles, switchable in the GUI, or with a controller button
- Joystick, Touchpad and Gyroscope input
- Haptic Feedback and in-game Rumble support
- Macros, button cycling, rapid fire, modeshift, mouse regions, …
- OSD, Menus, On-Screen Keyboard for desktop *and* in games - *except in [GNOME](https://github.com/C0rn3j/sc-controller/issues/18)*
- Automatic profile switching based on the active window - *X11 only for now*

### Supported controllers
All controllers *should* be supported at some level, either fully by a custom SC Controller driver, or best-effort by means of generic interfaces like evdev.

Controllers supported via a custom driver:
* Steam Controller (2015, 2026)
* Steam Deck
* DualShock 4 (v1, v2)
* DualSense
* DualSense Edge - untested, lacks support for the [4 extra buttons](https://github.com/C0rn3j/sc-controller/issues/89) at the moment

The controllers above will be autodetected and used without having to explicitly configure them.

#### Registering other controllers

If your controller is not in the list above, you have to add it via `Settings -> Controllers -> Register New Controller`.

Upon starting the registration process, your controller will be automatically mapped via SDL's [GameControllerDB](https://github.com/mdqinc/SDL_GameControllerDB), which has hundreds of supported devices.</br>
In case your controller is missing from the database, you will have to manually map each button in the UI, and afterwards you should [contribute](https://github.com/mdqinc/SDL_GameControllerDB#contributing) the layout.</br>

Beware that even when you do use automapper instead of manual assignment, you still have to press all the buttons as instructed, to automatically set up deadzones and thresholds for inputs like triggers and joysticks.

*Note that there is no automatic discovery of evdev nodes for gyroscope/touchpad, so if your controller has one of those, it currently needs SCC to implement a custom driver for it.*</br>
*That does mean that devices like Nintendo controllers do not have a working gyroscope, as I do not own any.*

## Using multiple controllers

SC Controller can drive several controllers at once — Steam Controllers (v1 and
v2), a DualShock 4 and others can all be connected together.

- **One window, one bar per controller.** Just connect them: each controller
  gets its own profile selector stacked in the main window, there is no separate
  window per device. The controller that connected *first* is the primary one —
  it is the one drawn on the big controller image and the default target when a
  command (a menu, the OSD) does not name a specific controller.
- **Each controller keeps its own profile.** Picking a profile from a
  controller's own bar applies only to that controller. The choice is remembered
  and restored automatically the next time that controller connects, so you do
  not have to re-pick it every session.
- **Disconnecting is safe.** Turning one controller off (or letting it go idle)
  leaves the window and the other controllers untouched; when it comes back it
  returns to its remembered profile.

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

## Community

For reporting bugs or having feature suggestions, head to the [Issues](https://github.com/C0rn3j/sc-controller/issues) tab.</br>
If you're not sure your topic belongs there, you can always head to [Discussions](https://github.com/C0rn3j/sc-controller/discussions) instead.

We also have a [Discord](https://discord.gg/Np7pgfTX6) available.

## Packages

<table>
	<tr>
		<td width="267" valign="top">
			<a href="https://repology.org/project/sc-controller/versions">
				<img src="https://repology.org/badge/vertical-allrepos/sc-controller.svg?exclude_unsupported=1&header=" width="240" alt="Packaging status">
			</a>
		</td>
		<td valign="top">
			<strong>Linux:</strong>
			<ul>
				<li>
					<strong>Arch Linux:</strong>
					Found in the official <a href="https://archlinux.org/packages/extra/x86_64/sc-controller/">extra</a> repository and
					<a href="https://aur.archlinux.org/packages/sc-controller-git/">AUR/sc-controller-git</a>.
					Install via <code>pacman -Syu sc-controller</code>.
				</li>
				<li>
					<strong>Debian:</strong>
					<a href="https://packages.debian.org/sid/sc-controller">Packaged</a>, but not yet released as stable. Also packaged as an
					<a href="https://github.com/C0rn3j/sc-controller/releases">AppImage</a>.
				</li>
				<li>
					<strong>Ubuntu (24.04 Noble, 26.04 Resolute):</strong> Packaged as an
					<a href="https://github.com/C0rn3j/sc-controller/releases">AppImage</a>,
					<em>which usually runs fine on other operating systems—the Noble
					image is currently the most compatible one.</em>
				</li>
				<li>
					<strong>Gentoo:</strong>
					Packaged as
					<a href="https://packages.gentoo.org/packages/games-util/sc-controller">games-util/sc-controller</a>.
				</li>
				<li>
					<strong>Void Linux:</strong>
					Packaged as
					<a href="https://github.com/void-linux/void-packages/blob/master/srcpkgs/sc-controller/template">sc-controller</a>.
					Install via <code>xbps-install -S sc-controller</code>.
				</li>
				<li>
					<strong>Others:</strong>
					You can attempt to use one of the AppImages (try all of them; AppImages
					built on older distributions have better compatibility), or a package
					intended for your parent distribution, if applicable.
				</li>
				<li><strong>Flatpak is planned.</strong></li>
			</ul>
			<strong>Windows:</strong>
			<ul>
				<li>
					Not planned. The half-finished C rewrite had Windows support, but it has
					been abandoned. See
					<a href="https://github.com/C0rn3j/sc-controller/issues/44">issue #44</a>
					for more information.
				</li>
			</ul>
			<strong>macOS:</strong>
			<ul>
				<li>
					Not planned.
				</li>
			</ul>
		</td>
	</tr>
</table>

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

## AI notice

If you contribute AI-assisted work, please disclose it, ensure you have tested the changes, and do not use unreviewed AI-generated text to communicate with maintainers.

Do **not** use AI-generated text to communicate with maintainers. You should understand and be able to explain your own work. Using AI to improve grammar or clarity is fine, but the substance of your responses must be your own.

If you wish to include context from an interaction with AI in your comments, it should be in a quote block (e.g., using >) and disclosed as such. It must be accompanied by your own commentary explaining the relevance and implications of the context.

## AI disclosure

This project uses AI tools to assist with debugging and writing code. AI output is reviewed, usually edited, and tested before being committed. In short, AI is treated as a development tool.

The exception to this is the contributed Steam Controller (2026) driver, which lives in its separate file, and its associated reverse engineering documentation.

---

*Based on [Standalone Steam Controller Driver](https://github.com/ynsta/steamcontroller) by [Ynsta](https://github.com/ynsta).*

*Donation links for kozec, who is the original developer, can be found on the [old upstream repository](https://github.com/kozec/sc-controller?tab=readme-ov-file#like-what-im-doing).*
