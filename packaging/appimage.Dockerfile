# syntax=docker/dockerfile:1
ARG BASE_IMAGE=ghcr.io/pkgforge-dev/archlinux
FROM $BASE_IMAGE AS build-stage

# Download build dependencies
ARG ANYLINUX_URL=https://github.com/pkgforge-dev/Anylinux-AppImages/raw/refs/heads/main
RUN <<EOR
  set -eu

  pacman -Syu --noconfirm \
    base-devel \
    bluez-libs \
    git \
    gobject-introspection \
    gtk4-layer-shell \
    librsvg \
    libxfixes \
    python-build \
    python-cairo \
    python-evdev \
    python-gobject \
    python-hidapi \
    python-ioctl-opt \
    python-libusb1 \
    python-pip \
    python-pytest \
    python-pyusb \
    python-vdf \
    patchelf xorg-server-xvfb    # patchelf and xvfb are for AnyLinux

  # Download AnyLinux tools
  url="${ANYLINUX_URL}/useful-tools"
  curl -fsSL "${url}/quick-sharun.sh" | install /dev/stdin /usr/local/bin/quick-sharun.sh

  # Install debloated MESA, Vulkan, Qt, GTK, libicudata, and more
  curl -fsSL "${url}/get-debloated-pkgs.sh" | sh -s -- --add-common --add-mesa --prefer-nano
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

  arch=$(uname -m)
  export APPNAME=sc-controller
  export DESKTOP="packaging/io.github.c0rn3j.${APPNAME}.desktop"
  export ICON="packaging/io.github.c0rn3j.${APPNAME}.svg"
  export VERSION=$(python -c "from scc.constants import DAEMON_VERSION; print(DAEMON_VERSION)")
  export UPINFO="gh-releases-zsync|${OWNER}|${APPNAME}|latest|${APPNAME}-*-${arch}.AppImage.zsync"
  export OUTNAME="$(echo "${APPNAME}-${VERSION}-anylinux-${arch}" | tr '[:upper:]' '[:lower:]').AppImage"
  export OUTPATH=/appimage
  export DEPLOY_PYTHON=1
  export USE_HOST_DRIVERS=1
  export SQUASHFS_METADATA_SIDECAR=1

  quick-sharun.sh \
    /usr/bin/sc-controller \
    /usr/bin/scc* \
    /usr/lib/libbluetooth.so* \
    /usr/lib/libgtk4-layer-shell.so.*

  cp -a packaging/appimage.*.hook AppDir/bin/

  quick-sharun.sh --make-appimage
EOR

# Keep only files required for runtime
FROM scratch AS export-stage
COPY --from=build-stage /appimage /
