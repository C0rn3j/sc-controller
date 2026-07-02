# package.nix for sc-controller-cc
#
# sc-controller-cc — an LLM-assisted fork of sc-controller, the user-mode driver
# and GTK3 GUI for the Steam Controller, DS4 and similar controllers.
# Upstream: https://github.com/Patola/sc-controller-cc
#
# This is a portable, source-built Nix derivation (nothing here is specific to
# any one machine), so it works both on this rootless nix-user-chroot (e.g. on SteamOS)
# and on any other Nix/NixOS system. It is modelled on the Arch `sc-controller-cc`
# PKGBUILD (same dependency set, build a wheel then install it), plus three
# portability fixes the PKGBUILD gets "for free" from a normal FHS system but
# that a self-contained Nix package must handle itself:
#
#   1. Kernel input constants — scc/uinput.py builds its Keys/Axes enums by
#      parsing linux/input-event-codes.h at *runtime*. On FHS it reads
#      /usr/include; here we copy that one header (from linuxHeaders, a
#      build-time-only input) into the installed scc/ package dir, which is the
#      first location scc/uinput.py looks. Nothing from linuxHeaders ends up in
#      the runtime closure — just the copied text file.
#
#   2. ctypes-loaded X11 libs — scc/lib/xwrappers.py dlopens libX11/libXfixes/
#      libXext by soname, and scc/lib/xinput.py shells out to the `xinput`
#      binary. The Nix Python loader does not search /usr/lib, so we put those
#      libraries on LD_LIBRARY_PATH and `xinput` on PATH via the wrapper.
#
#   3. libudev — scc/lib/eudevmonitor.py dlopens libudev.so.1 for controller
#      hotplug detection. We ship libudev-zero (a tiny, self-contained
#      libudev.so.1 with no systemd dependency). The host's real libudev cannot
#      be used from a Nix process: it needs libcap.so.2 etc. from /usr/lib, and
#      putting all of /usr/lib on LD_LIBRARY_PATH would shadow this package's
#      own glibc/GTK libraries. libudev-zero implements the netlink monitor and
#      sysfs enumeration scc relies on, so hotplug works without systemd.
#
# It is wired into the flake overlay as:
#     sc-controller-cc = final.callPackage ./sc-controller-cc.nix { };
# and referenced in home.nix's `home.packages`.
#
# Note on udev rules: the package installs scripts/69-sc-controller.rules to
# $out/lib/udev/rules.d, but a rootless home-manager setup cannot load system
# udev rules. On a Steam Deck the controllers are already accessible so no rules
# are needed; on other systems, copy that file into /etc/udev/rules.d (as root)
# if a non-Valve controller needs write access.
#
# To bump the version: change `rev` (and `version`), set `hash` to
# lib.fakeHash, run `home-manager switch`, then paste the real hash from the
# "got:" line of the mismatch error.
{ lib
, fetchFromGitHub
, python3
, gobject-introspection
, wrapGAppsHook3
, gtk3
, gtk-layer-shell
, libayatana-appindicator
, librsvg
, zlib
, xorg
, libudev-zero
, bluez
, linuxHeaders
}:

let
  # Libraries scc dlopens by soname at runtime via ctypes (the Nix Python loader
  # does not search /usr/lib). Shared by the runtime wrapper and the test phase.
  runtimeLibraries = [
    xorg.libX11
    xorg.libXfixes
    xorg.libXext
    libudev-zero
    bluez # libbluetooth.so.3, for Bluetooth controller detection
  ];
in
python3.pkgs.buildPythonApplication rec {
  pname = "sc-controller-cc";
  version = "0.6.0.1";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "Patola";
    repo = "sc-controller-cc";
    rev = "461c34d83dd4bef716004b4f234d9f4fe99219f3";
    hash = "sha256-bk8CADJ9ZJO7e53+LSqVarj8jL6z9VMoE/34t1aFNWo=";
  };

  # The project's version is "dynamic" via setuptools_scm, which reads it from
  # git tags. fetchFromGitHub strips the .git directory, so hand setuptools_scm
  # the version explicitly instead of letting it fail with "no version found".
  env.SETUPTOOLS_SCM_PRETEND_VERSION = version;

  build-system = with python3.pkgs; [
    setuptools
    setuptools-scm
    wheel
  ];

  # gobject-introspection + wrapGAppsHook3 make the GTK3 GUI find its GObject
  # typelibs (Gtk, GtkLayerShell, AyatanaAppIndicator3), GdkPixbuf SVG loaders
  # and GSettings schemas at runtime.
  nativeBuildInputs = [
    gobject-introspection
    wrapGAppsHook3
    # Test runner for the post-install pytest gate (see postFixup).
    python3.pkgs.pytest
    python3.pkgs.toml
  ];

  buildInputs = [
    gtk3
    gtk-layer-shell
    libayatana-appindicator
    librsvg # so GTK can render the app's SVG icons via gdk-pixbuf
    zlib # the libcemuhook C extension links against libz
  ];

  # Python runtime dependencies — mirrors the PKGBUILD's python-* depends.
  # Note: libusb1 (the Python binding) already loads the C libusb by an absolute
  # /nix/store path baked into its loader by nixpkgs (usb1/_libusb1.py), so —
  # unlike the old official sc-controller package — the C libusb does NOT need to
  # go on LD_LIBRARY_PATH; it is a pinned closure dependency and cannot silently
  # go missing.
  dependencies = with python3.pkgs; [
    evdev
    pygobject3
    ioctl-opt
    libusb1
    pylibacl
    vdf
    setuptools # scc imports pkg_resources at runtime
  ];

  # Tests run in postFixup (see below), not checkPhase: buildPythonApplication's
  # checkPhase runs before install, but the CC fork's scc/constants.py needs the
  # package's installed dist metadata at import time
  # (packages_distributions()["scc"]), which only exists once the wheel is in $out.
  doCheck = false;

  # scc/device_monitor.py resolves libbluetooth via ctypes.util.find_library,
  # which does not consult LD_LIBRARY_PATH and returns None under Nix (so
  # HAVE_BLUETOOTH_LIB stays False and Bluetooth controller detection is
  # incomplete). Point it straight at the soname; the actual load then honours
  # the bluez path we add to LD_LIBRARY_PATH below. Same fix the official
  # nixpkgs sc-controller package uses.
  postPatch = ''
    substituteInPlace scc/device_monitor.py \
      --replace-fail 'find_library("bluetooth")' '"libbluetooth.so.3"'
  '';

  # scc/uinput.py parses linux/input-event-codes.h at import time. Its preferred
  # source is a copy sitting next to the module itself, so drop one there (from
  # linuxHeaders) to make the package self-contained instead of depending on the
  # host having kernel headers under /usr/include (SteamOS ships none).
  postInstall = ''
    install -Dm644 ${linuxHeaders}/include/linux/input-event-codes.h \
      "$out/${python3.sitePackages}/scc/input-event-codes.h"
  '';

  # scc/x11/scc-osd-daemon.py and scc-autoswitch-daemon.py are NOT console
  # entry points — the daemon runs them directly as `[sys.executable, <script>]`
  # (see find_binary/find_python in scc/tools.py). Spawned that way they get the
  # bare interpreter with no access to scc or its deps (gi, evdev, …), so they
  # crash with ModuleNotFoundError. patchPythonScript injects the same sitedir
  # bootstrap that buildPythonApplication bakes into $out/bin wrappers. Same fix
  # the official nixpkgs sc-controller package uses.
  postFixup = ''
    (
      cd "$out/${python3.sitePackages}/scc/x11"
      patchPythonScript scc-osd-daemon.py
      patchPythonScript scc-autoswitch-daemon.py
    )

    # Post-install test gate. Runs here (not checkPhase) because scc only imports
    # once its dist metadata exists in $out. Import the installed scc from $out
    # (has metadata + the bundled input-event-codes.h) rather than the source
    # tree: `python -P` drops the build cwd (which still holds ./scc) from
    # sys.path so `import scc` resolves via PYTHONPATH to $out. The X11/udev/
    # bluetooth libs scc dlopens at import must be reachable, hence LD_LIBRARY_PATH.
    echo "Running post-install test suite..."
    PYTHONPATH="$out/${python3.sitePackages}''${PYTHONPATH:+:$PYTHONPATH}" \
    SCC_SHARED="$out/share/scc" \
    LD_LIBRARY_PATH="${lib.makeLibraryPath runtimeLibraries}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    python -P -m pytest -q --import-mode=importlib tests/ \
      `# GUI test needs a display / GTK; skip it in the sandbox` \
      --ignore=tests/test_setup.py \
      `# three pre-existing upstream test-suite gaps (a missing "inverted"` \
      `# modifier test + an action-doc coverage gap), unrelated to packaging:` \
      --deselect 'tests/test_docs.py::TestDocs::test_every_action_has_docs' \
      --deselect 'tests/test_parser/test_modifiers.py::TestModifiers::test_tests' \
      --deselect 'tests/test_profile/test_modifiers.py::TestModifiers::test_tests'
  '';

  # buildPythonApplication does its own console-script wrapping, so disable the
  # separate GApps wrapper and fold its env (GI_TYPELIB_PATH,
  # GDK_PIXBUF_MODULE_FILE, XDG_DATA_DIRS, GSETTINGS_SCHEMAS_PATH) into the
  # Python wrappers, alongside:
  #   * LD_LIBRARY_PATH — the X11 + libudev libraries scc dlopens by soname via
  #     ctypes (the Nix Python loader does not look in /usr/lib).
  #   * PATH — `xinput`, which scc/lib/xinput.py shells out to.
  #   * SCC_SHARED — scc/paths.py locates its data (glade, images, default
  #     profiles/menus) relative to sys.prefix, which for a Nix app points at
  #     the Python interpreter's store path, not $out; without this it falls
  #     back to /usr/share/scc and the GUI fails to load app.glade. SCC_SHARED
  #     is scc's own documented override.
  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=(
      "''${gappsWrapperArgs[@]}"
      --set SCC_SHARED "$out/share/scc"
      --prefix PATH : ${lib.makeBinPath [ xorg.xinput ]}
      --prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath runtimeLibraries}
    )
  '';

  meta = {
    description = "LLM-assisted fork of sc-controller: user-mode driver and GTK3 GUI for Steam Controller, DS4 and similar controllers";
    homepage = "https://github.com/Patola/sc-controller-cc";
    license = lib.licenses.gpl2Only;
    mainProgram = "sc-controller";
    platforms = lib.platforms.linux;
  };
}
