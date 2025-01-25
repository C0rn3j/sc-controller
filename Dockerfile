# syntax=docker/dockerfile:1
ARG BASE_OS=ubuntu
ARG BASE_CODENAME=noble
FROM $BASE_OS:$BASE_CODENAME AS build-stage

# Download build dependencies
RUN <<EOR
	set -eu

	# Workaround for outstanding fix of https://bugs.launchpad.net/ubuntu/+source/python-build/+bug/1992108
	. /etc/os-release
	if [ ${UBUNTU_CODENAME-} = 'jammy' ]; then
		echo >>/etc/apt/sources.list.d/jammy-proposed.list 'deb [arch=amd64] http://archive.ubuntu.com/ubuntu/     jammy-proposed universe'
		echo >>/etc/apt/sources.list.d/jammy-proposed.list 'deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports/ jammy-proposed universe'
	fi

	apt-get update
	export DEBIAN_FRONTEND=noninteractive
	apt-get install -y --no-install-recommends \
		gcc \
		git \
		librsvg2-bin \
		libxfixes3 \
		linux-headers-generic \
		python3-build \
		python3-dev \
		python3-setuptools \
		python3-usb \
		python3-venv \
		python-is-python3

	apt-get clean && rm -rf /var/lib/apt/lists/*
EOR
# Prepare working directory and target
COPY . /work
WORKDIR /work
ARG TARGET=/build

# Build and install
RUN <<EOR
	set -eu

	python -m build --wheel
	python -m venv .env
	. .env/bin/activate
	pip install libusb1 pytest toml vdf
	python -m pytest tests
	pip install --prefix "${TARGET}/usr" --no-warn-script-location dist/*.whl

	# Save version
	PYTHONPATH=$(find "${TARGET}" -type d -name site-packages) \
	python -c "from scc.constants import DAEMON_VERSION; print('VERSION=' + DAEMON_VERSION)" >>/build/.build-metadata.env

	# Fix shebangs of scripts from '#!/work/.env/bin/python'
	find "${TARGET}/usr/bin" -type f | xargs sed -i 's:work/.env:usr:'

	# Provide input-event-codes.h as fallback for runtime systems without linux headers
	cp -a \
		"$(find /usr -type f -name input-event-codes.h -print -quit)" \
		"$(find "${TARGET}" -type f -name uinput.py -printf '%h\n' -quit)"

	# Create short name symlinks for static libraries
	suffix=".cpython-*-$(uname -m)-linux-gnu.so"
	find "${TARGET}" -type f -path "*/site-packages/*${suffix}" \
		| while read -r path; do ln -sfr "${path}" "${path%${suffix}}.so"; done

	share="${TARGET}/usr/share"

	# Put AppStream metadata to required location according to https://wiki.debian.org/AppStream/Guidelines
	metainfo="${share}/metainfo"
	mkdir -p "${metainfo}"
	cp -a scripts/sc-controller.appdata.xml "${metainfo}"

	# Convert icon to png format (required for icons in .desktop file)
	iconpath="${share}/icons/hicolor/512x512/apps"
	mkdir -p "${iconpath}"
	rsvg-convert --background-color none -o "${iconpath}/sc-controller.png" images/sc-controller.svg
EOR

# Store build metadata
ARG TARGETOS TARGETARCH TARGETVARIANT
RUN export "TARGETMACHINE=$(uname -m)" && printenv | grep ^TARGET >>/build/.build-metadata.env

# Keep only files required for runtime
FROM scratch AS export-stage
COPY --from=build-stage /build /
