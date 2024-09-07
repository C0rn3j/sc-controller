# syntax=docker/dockerfile:1
ARG BASE_OS=ubuntu
ARG BASE_CODENAME=noble
FROM $BASE_OS:$BASE_CODENAME AS build-stage

# Download build dependencies
RUN <<EOR
  set -eu

  apt-get update
  apt-get install -y --no-install-recommends \
	  gcc \
	  librsvg2-bin \
	  linux-headers-generic \
	  python3-dev \
	  python3-setuptools \
	  python-is-python3
  apt-get clean && rm -rf /var/lib/apt/lists/*
EOR
# Prepare working directory and target
COPY . /work
WORKDIR /work
ARG TARGET=/build/usr

# Build and install
RUN <<EOR
  set -eu

  python setup.py build --executable "/usr/bin/env python3"
  python setup.py install --single-version-externally-managed --home "${TARGET}" --record /dev/null

  # Provide input-event-codes.h as fallback for runtime systems without linux headers
  cp -a \
	  "$(find /usr -type f -name input-event-codes.h -print -quit)" \
	  "$(find "${TARGET}" -type f -name uinput.py -printf '%h\n' -quit)"

  # Create short name symlinks for static libraries
  suffix=".cpython-*-$(uname -m)-linux-gnu.so"
  find "${TARGET}" -type f -path "*/site-packages/*${suffix}" \
    | while read -r path; do ln -sfr "${path}" "${path%${suffix}}.so"; done

  # Put AppStream metadata to required location according to https://wiki.debian.org/AppStream/Guidelines
  metainfo=/build/usr/share/metainfo
  mkdir -p "${metainfo}"
  cp -a scripts/sc-controller.appdata.xml "${metainfo}"

  # Convert icon to png format (required for icons in .desktop file)
  iconpath="${TARGET}/share/icons/hicolor/512x512/apps"
  mkdir -p "${iconpath}"
  rsvg-convert --background-color none -o "${iconpath}/sc-controller.png" images/sc-controller.svg
EOR

# Store build metadata
ARG TARGETOS TARGETARCH TARGETVARIANT
RUN export "TARGETMACHINE=$(uname -m)" && printenv | grep ^TARGET >>/build/.build-metadata.env

# Keep only files required for runtime
FROM scratch AS export-stage
COPY --from=build-stage /build /
