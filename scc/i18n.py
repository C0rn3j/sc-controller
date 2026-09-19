"""Shared Python and GTK translation setup."""

import builtins
import gettext
import locale
import logging
import os
import sys
from pathlib import Path

DOMAIN = "sc-controller"
_translation = gettext.NullTranslations()
_catalogs: list[str] = []
_localedir = ""
log = logging.getLogger(__name__)


def get_locale_path() -> str:
	"""Locate catalogs in source checkouts, AppImages, and installed packages."""
	package = Path(__file__).resolve().parent
	if (package.parent / "pyproject.toml").is_file():
		return str(package / "locale")
	if appdir := os.environ.get("APPDIR"):
		return str(Path(appdir) / "usr/share/locale")
	installed = Path(sys.prefix) / "share/locale"
	if any(installed.glob(f"*/LC_MESSAGES/{DOMAIN}.mo")):
		return str(installed)
	if (package / "locale").is_dir():
		return str(package / "locale")
	return str(installed)


def log_selection() -> None:
	"""Report the selected catalogs once application logging is configured."""
	if _catalogs:
		languages = ", ".join(Path(path).parent.parent.name for path in _catalogs)
		log.info("Translation language: %s; catalogs: %s", languages, ", ".join(_catalogs))
	else:
		log.info("Translation language: English (source fallback); no matching catalog in %s", _localedir)
	log.info("GTK message locale: %s; gettext domain: %s", locale.setlocale(locale.LC_MESSAGES), DOMAIN)


def init(localedir: str | None = None) -> None:
	global _translation, _catalogs, _localedir

	if localedir is None:
		localedir = get_locale_path()
	_localedir = localedir
	try:
		locale.setlocale(locale.LC_ALL, "")
	except locale.Error:
		logging.getLogger(__name__).warning("Cannot activate the requested system locale")
	locale.bindtextdomain(DOMAIN, localedir)  # Native gettext used by GTK.
	locale.textdomain(DOMAIN)
	_translation = gettext.translation(DOMAIN, localedir=localedir, fallback=True)
	_catalogs = gettext.find(DOMAIN, localedir=localedir, all=True)
	builtins._ = _
	# Logging isn't setup yet, so it won't be visible, we log elsewhere later too
	log_selection()


def _(message: str) -> str:
	return _translation.gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
	return _translation.ngettext(singular, plural, count)
