# syntax=docker/dockerfile:1
FROM ghcr.io/pkgforge-dev/archlinux AS build-stage

# Prepare Python build dependencies
RUN <<EOR
  set -eu

  pacman -Syu --noconfirm \
    base-devel \
    bluez-libs \
    cairo \
    gettext \
    git \
    gobject-introspection \
    gtk4 \
    gtk4-layer-shell \
    librsvg \
    libxfixes \
    linux-headers \
    python \
    python-build \
    python-cairo \
    python-evdev \
    python-gobject \
    python-hidraw-pure \
    python-ioctl-opt \
    python-libusb1 \
    python-pip \
    python-pytest \
    python-pyusb \
    python-vdf

  pacman -Scc
EOR

# Prepare AppImage Build dependencies
RUN <<EOR
  pacman -Syu --noconfirm patchelf xorg-server-xvfb
  tools="https://raw.githubusercontent.com/pkgforge-dev/Anylinux-AppImages/refs/heads/main/useful-tools"
  sharun="${tools}/quick-sharun.sh"
  debloated="${tools}/get-debloated-pkgs.sh"
  curl -fsSL "${sharun}" | install /dev/stdin /usr/local/bin/quick-sharun.sh
  curl -fsSL "${debloated}" | install /dev/stdin /usr/local/bin/get-debloated-pkgs.sh

  # Installs a debloated MESA, Vulkan, Qt, GTK, libicudata, and more
  get-debloated-pkgs.sh --add-mesa --prefer-nano

  pacman -Scc
EOR

# Build and install
ARG TARGETOS TARGETARCH TARGETVARIANT
ARG OWNER=owner
COPY . /work
WORKDIR /work
RUN <<EOR
  set -eu

  pip install --break-system-packages --root-user-action ignore .
  python -m pytest tests

  # Provide input-event-codes.h as fallback for runtime systems without linux headers
  input_event_codes="$(find /usr/lib/python*/site-packages/scc -type f -name uinput.py -printf '%h\n' -quit)/input-event-codes.h"
  cp -a /usr/include/linux/input-event-codes.h "${input_event_codes}"

  export APPNAME=sc-controller
  export DESKTOP="packaging/io.github.c0rn3j.${APPNAME}.desktop"
  export ICON="packaging/io.github.c0rn3j.${APPNAME}.svg"
  export VERSION=$(python -c "from scc.constants import DAEMON_VERSION; print(DAEMON_VERSION)")
  export UPINFO="gh-releases-zsync|${OWNER}|${APPNAME}|latest|${APPNAME}-*-${TARGETARCH}.AppImage.zsync"
  export OUTNAME="$(echo "${APPNAME}-${VERSION}-anylinux-${TARGETARCH}" | tr '[:upper:]' '[:lower:]').AppImage"
  export OUTPATH=/appimage
  export DEPLOY_PYTHON=1
  export MAIN_BIN=/usr/bin/scc

  quick-sharun.sh \
    /usr/bin/sc-controller \
    /usr/bin/scc* \
    /usr/lib/python*/site-packages/usb1/*.py \
    /usr/lib/libbluetooth.so \
    /usr/lib/librsvg-2.so \
    "${input_event_codes}"

  quick-sharun.sh --make-appimage
EOR

# Keep only files required for runtime
FROM scratch AS export-stage
COPY --from=build-stage /appimage /
