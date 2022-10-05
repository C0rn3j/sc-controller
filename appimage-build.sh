#!/bin/bash
APP="sc-controller"
EXEC="scc"
LIB="lib"

EVDEV_VERSION=0.7.0
[ x"$BUILD_APPDIR" == "x" ] && BUILD_APPDIR=$(pwd)/appimage
PYTHON_VERSION=$(python -c 'import sys; version=sys.version_info[:3]; print("{0}.{1}".format(*version))')


function download_dep() {
	NAME=$1
	URL=$2
	if [ -e ../../${NAME}.obstargz ] ; then
		# Special case for OBS
		cp ../../${NAME}.obstargz /tmp/${NAME}.tar.gz
	elif [ -e ${NAME}.tar.gz ] ; then
		cp ${NAME}.tar.gz /tmp/${NAME}.tar.gz
	elif [ -e /tmp/${NAME}.tar.gz ] ; then
		echo "/tmp/${NAME}.tar.gz already downloaded"
	else
		wget -c "${URL}" -O /tmp/${NAME}.tar.gz
	fi
}

function build_dep() {
	NAME="$1"
	mkdir -p /tmp/${NAME}
	pushd /tmp/${NAME}
	tar --extract --strip-components=1 -f /tmp/${NAME}.tar.gz
	PYTHONPATH=${BUILD_APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages python3 \
		setup.py install --optimize=1 \
		--prefix="/usr/" --root="${BUILD_APPDIR}"
	mkdir -p "${BUILD_APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages/"
	python3 setup.py install --prefix="/usr/" --root="${BUILD_APPDIR}"
	popd
}

function unpack_dep() {
	NAME="$1"
	pushd ${BUILD_APPDIR}
	tar --extract --exclude="usr/include**" --exclude="usr/lib/pkgconfig**" \
			--exclude="usr/lib/python2.7**" -f /tmp/${NAME}.tar.gz
	popd
}

set -ex		# display commands, terminate after 1st failure

# Download deps
download_dep "python-evdev-0.7.0" "https://github.com/gvalkov/python-evdev/archive/v0.7.0.tar.gz"
download_dep "pylibacl-0.5.3" "https://github.com/iustin/pylibacl/releases/download/pylibacl-v0.5.3/pylibacl-0.5.3.tar.gz"
download_dep "python-gobject-3.36.1" "https://archive.archlinux.org/packages/p/python-gobject/python-gobject-3.36.1-1-x86_64.pkg.tar.zst"
download_dep "python-vdf-3.4" "https://github.com/ValvePython/vdf/archive/v3.4.tar.gz"
download_dep "python-cairo-1.18.2" "https://archive.archlinux.org/packages/p/python2-cairo/python2-cairo-1.18.2-3-x86_64.pkg.tar.xz"
download_dep "gobject-introspection-runtime-1.60" "https://archive.archlinux.org/packages/g/gobject-introspection-runtime/gobject-introspection-runtime-1.60.0-1-x86_64.pkg.tar.xz"
download_dep "libpng-1.6.34" "https://archive.archlinux.org/packages/l/libpng/libpng-1.6.34-2-x86_64.pkg.tar.xz"
download_dep "gdk-pixbuf-2.36.9" "https://archive.archlinux.org/packages/g/gdk-pixbuf2/gdk-pixbuf2-2.36.9-1-x86_64.pkg.tar.xz"
download_dep "libcroco-0.6.13" "https://archive.archlinux.org/packages/l/libcroco/libcroco-0.6.13-1-x86_64.pkg.tar.xz"
download_dep "libxml2-2.9.10" "https://archive.archlinux.org/packages/l/libxml2/libxml2-2.9.10-2-x86_64.pkg.tar.zst"
download_dep "librsvg-2.48.7" "https://archive.archlinux.org/packages/l/librsvg/librsvg-2%3A2.48.7-1-x86_64.pkg.tar.zst"
download_dep "icu-67.1" "https://archive.archlinux.org/packages/i/icu/icu-67.1-1-x86_64.pkg.tar.zst"
download_dep "zlib-1:1.2.12" "https://archive.archlinux.org/packages/z/zlib/zlib-1%3A1.2.12-2-x86_64.pkg.tar.zst"
download_dep "libffi-3.3" "https://archive.archlinux.org/packages/l/libffi/libffi-3.3-3-x86_64.pkg.tar.zst"

# Prepare & build deps
export PYTHONPATH=${BUILD_APPDIR}/usr/lib/python${PYTHON_VERSION}/site-packages/
mkdir -p "$PYTHONPATH"
if [[ $(grep ID_LIKE /etc/os-release) == *"suse"* ]] ; then
	# Special handling for OBS
	ln -s lib64 ${BUILD_APPDIR}/usr/lib
	export PYTHONPATH="$PYTHONPATH":${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/
	LIB=lib64
fi

build_dep "python-evdev-0.7.0"
build_dep "pylibacl-0.5.3"
build_dep "python-vdf-3.4"
unpack_dep "libpng-1.6.34"
unpack_dep "python-gobject-3.36.1"
unpack_dep "python-cairo-1.18.2"
unpack_dep "python-gobject-3.26.1"
unpack_dep "gobject-introspection-runtime-1.60"
unpack_dep "gdk-pixbuf-2.36.9"
unpack_dep "libcroco-0.6.13"
unpack_dep "libxml2-2.9.10"
unpack_dep "librsvg-2.48.7"
unpack_dep "icu-67.1"
unpack_dep "zlib-1:1.2.11"
unpack_dep "libffi-3.3"

# Remove uneeded files
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-ani.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-bmp.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-gif.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-icns.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-ico.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-jasper.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-jpeg.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-qtif.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-tga.so"
rm -f "${BUILD_APPDIR}/usr/${LIB}/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-tiff.so"
rm -R "${BUILD_APPDIR}/usr/lib/cmake"
rm -R "${BUILD_APPDIR}/usr/share/doc"
rm -R "${BUILD_APPDIR}/usr/share/gtk-doc"
rm -R "${BUILD_APPDIR}/usr/share/locale"
rm -R "${BUILD_APPDIR}/usr/share/man"
rm -R "${BUILD_APPDIR}/usr/share/thumbnailers"
rm -R "${BUILD_APPDIR}/usr/share/vala"
rm -R "${BUILD_APPDIR}/usr/share/icu"

# Build important part
python3 setup.py build

# Need to use single-version-externally-managed due to setuptools behavior
python3 setup.py install --single-version-externally-managed --prefix ${BUILD_APPDIR}/usr --record /dev/null

# Move udev stuff
mv ${BUILD_APPDIR}/usr/lib/udev/rules.d/69-${APP}.rules ${BUILD_APPDIR}/
rmdir ${BUILD_APPDIR}/usr/lib/udev/rules.d/
rmdir ${BUILD_APPDIR}/usr/lib/udev/
mkdir -p ${BUILD_APPDIR}/usr/${LIB}/python3.8/site-packages/scc/
cp "/usr/include/linux/input-event-codes.h" ${BUILD_APPDIR}/usr/${LIB}/python3.8/site-packages/scc/

# Move & patch desktop file
mv ${BUILD_APPDIR}/usr/share/applications/${APP}.desktop ${BUILD_APPDIR}/
sed -i "s/Icon=.*/Icon=${APP}/g" ${BUILD_APPDIR}/${APP}.desktop
sed -i "s/Exec=.*/Exec=.\/usr\/bin\/scc gui/g" ${BUILD_APPDIR}/${APP}.desktop

# Convert icon
convert -background none ${BUILD_APPDIR}/usr/share/pixmaps/${APP}.svg ${BUILD_APPDIR}/${APP}.png

# Copy appdata.xml
mkdir -p ${BUILD_APPDIR}/usr/share/metainfo/
cp scripts/${APP}.appdata.xml ${BUILD_APPDIR}/usr/share/metainfo/${APP}.appdata.xml

# Make symlinks
ln -sfr ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libcemuhook.cpython-310-x86_64-linux-gnu.so ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libcemuhook.so
ln -sfr ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libhiddrv.cpython-310-x86_64-linux-gnu.so ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libhiddrv.so
ln -sfr ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libremotepad.cpython-310-x86_64-linux-gnu.so ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libremotepad.so
ln -sfr ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libsc_by_bt.cpython-310-x86_64-linux-gnu.so ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libsc_by_bt.so
ln -sfr ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libuinput.cpython-310-x86_64-linux-gnu.so ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/libuinput.so
ln -sfr ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/posix1e.cpython-310-x86_64-linux-gnu.so ${BUILD_APPDIR}/usr/lib64/python${PYTHON_VERSION}/site-packages/posix1e.so

# Copy AppRun script
cp scripts/appimage-AppRun.sh ${BUILD_APPDIR}/AppRun
chmod +x ${BUILD_APPDIR}/AppRun

echo "Run appimagetool -n ${BUILD_APPDIR} to finish prepared appimage"
