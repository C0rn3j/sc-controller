#!/usr/bin/env bash
set -euo pipefail

# Run everything from repo root, so .po/.pot files don't have broken path references
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

pot_file=locale/sc-controller.pot
python_files=$(mktemp "${TMPDIR:-/tmp}/scc_POTFILES.python.XXXXXX")
ui_files=$(mktemp "${TMPDIR:-/tmp}/scc_POTFILES.ui.XXXXXX")
new_pot=$(mktemp "${TMPDIR:-/tmp}/sc-controller.pot.XXXXXX")
trap 'rm -f "$python_files" "$ui_files" "$new_pot"' EXIT

find scc -type f -name '*.py' | sort > "${python_files}"
find ui -type f -name '*.ui' | sort > "${ui_files}"

xgettext \
	--language=Python \
	--from-code=UTF-8 \
	--keyword=_ \
	--keyword=ngettext:1,2 \
	--keyword=pgettext:1c,2 \
	--add-comments=TRANSLATORS \
	--package-name=sc-controller \
	--files-from="${python_files}" \
	--output="${new_pot}"

xgettext \
	--language=Glade \
	--from-code=UTF-8 \
	--join-existing \
	--package-name=sc-controller \
	--files-from="${ui_files}" \
	--output="${new_pot}"

sed -i \
	's/^# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR\.$/# Martin Rys <martin@archlinux.org>, 2026./' \
	"${new_pot}"

# xgettext always updates POT-Creation-Date, ignore it
# Line placement etc are tracked in a comment, ignore that too
# Exit if there are no other differences
if [[ -f "${pot_file}" ]] && cmp -s \
	<(sed '/^"POT-Creation-Date:/d; /^#/d' "${pot_file}") \
	<(sed '/^"POT-Creation-Date:/d; /^#/d' "${new_pot}"); then
	exit 0
fi

# Update the .pot file
chmod 644 "${new_pot}"
mv "${new_pot}" "${pot_file}"

# Create language files - this needs to only ever run once per language
# Weblate takes care of this now
#if [[ ! -e "locale/cs/LC_MESSAGES/sc-controller.po" ]]; then
#	echo "cs LANGUAGE NOT FOUND, CREATING ANEW!"
#	msginit \
#		--input=locale/sc-controller.pot \
#		--locale=cs \
#		--output-file=locale/cs/LC_MESSAGES/sc-controller.po
#fi
