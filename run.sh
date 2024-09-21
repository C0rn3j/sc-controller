#!/bin/bash
set -euo pipefail
C_MODULES=(uinput hiddrv sc_by_bt remotepad cemuhook)
C_VERSION_uinput=9
C_VERSION_hiddrv=5
C_VERSION_sc_by_bt=3
C_VERSION_remotepad=1
C_VERSION_cemuhook=1

function rebuild_c_modules() {
	echo "lib${1}.so is outdated or missing, building one"
	echo "Please wait, this should be done only once."
	echo ""
	# cpython-312-x86_64-linux-gnu
#	SOABI=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("SOABI").split("-")[0:2])');

	# lib.linux-x86_64-cpython-312 - directory where libuinput.so was just generated
	LIB=$( python3 -c 'import platform; import sysconfig; soabi = sysconfig.get_config_var("SOABI").split("-")[0:2]; print(f"lib.linux-{platform.machine()}-{soabi[0]}-{soabi[1]}")' )
	# .cpython-312-x86_64-linux-gnu.so
	EXT_SUFFIX=$( python3 -c 'import sysconfig ; print(sysconfig.get_config_var("EXT_SUFFIX"))' )
	for cmod in ${C_MODULES[@]}; do
		if [[ -e build/${LIB}/lib${cmod}${EXT_SUFFIX} ]]; then
			rm "build/${LIB}/lib${cmod}${EXT_SUFFIX}"
		fi
	done

	python3 setup.py build
	echo ""

	for cmod in ${C_MODULES[@]}; do
		if [[ ! -e lib${cmod}.so ]] ; then
			ln -s "build/${LIB}/lib${cmod}${EXT_SUFFIX}" "./lib${cmod}.so"
			echo "Symlinked ./lib${cmod}.so '->' build/${LIB}/lib${cmod}${EXT_SUFFIX}"
		fi
	done
	echo ""
}


# Ensure correct cwd
cd "$(dirname "$0")"

# Check if c modules are compiled and actual
for cmod in ${C_MODULES[@]}; do
	expected_version=\$C_VERSION_${cmod}
	if ! reported_version=$(PYTHONPATH="." python3 -c 'import os, ctypes; lib=ctypes.CDLL("./'lib${cmod}'.so"); print(lib.'${cmod}'_module_version())'); then
		echo "Failed to check module version for ${cmod}, this is normal"
	fi
	if [[ "$reported_version" != "${expected_version}" ]] ; then
		rebuild_c_modules "${cmod}"
	fi
done

# Set PATH
SCRIPTS="$(pwd)/scripts"
export PATH="${SCRIPTS}":"${PATH}"
export PYTHONPATH=".":"${PYTHONPATH-}"
export SCC_SHARED="$(pwd)"

# Execute
python3 'scripts/sc-controller' $@
