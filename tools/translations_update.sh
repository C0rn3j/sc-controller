#!/usr/bin/env bash
set -euo pipefail

find ../scc -type f -name '*.py' | sort > /tmp/scc_POTFILES.python
find ../ui -type f -name '*.ui' | sort > /tmp/scc_POTFILES.ui

xgettext \
	--language=Python \
	--from-code=UTF-8 \
	--keyword=_ \
	--keyword=ngettext:1,2 \
	--keyword=pgettext:1c,2 \
	--add-comments=TRANSLATORS \
	--package-name=sc-controller \
	--files-from=/tmp/scc_POTFILES.python \
	--output=../locale/sc-controller.pot

xgettext \
	--language=Glade \
	--from-code=UTF-8 \
	--join-existing \
	--package-name=sc-controller \
	--files-from=/tmp/scc_POTFILES.ui \
	--output=../locale/sc-controller.pot

rm /tmp/scc_POTFILES.python /tmp/scc_POTFILES.ui

# Create language files - this needs to only ever run once per language
if [[ ! -e "../locale/cs/LC_MESSAGES/sc-controller.po" ]]; then
	echo "cs LANGUAGE NOT FOUND, CREATING ANEW!"
	msginit \
		--input=../locale/sc-controller.pot \
		--locale=cs \
		--output-file=../locale/cs/LC_MESSAGES/sc-controller.po
fi
