"""Shared Python and GTK translation setup."""

import builtins
import gettext
import json
import locale
import logging
import os
import sys
from pathlib import Path

from scc.paths import get_config_path

DOMAIN = "sc-controller"
_translation = gettext.NullTranslations()
_catalogs: list[str] = []
_localedir = ""
log = logging.getLogger(__name__)


def _get_configured_language() -> str:
	"""Read the language early, before the regular configuration is imported."""
	try:
		with (Path(get_config_path()) / "config.json").open(encoding="utf-8") as config_file:
			language = json.load(config_file).get("language", "")
		return language if isinstance(language, str) else ""
	except (AttributeError, OSError, ValueError, TypeError):
		log.exception("Failed getting language settings from the config file, first run?")
		return ""


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


def get_available_languages(localedir: str | None = None) -> list[tuple[str, str]]:
	"""Return language codes and display names for installed catalogs."""
	localedir = localedir or get_locale_path()
	languages = [("", _("System Default")), ("en", _("English"))]
	for catalog in sorted(Path(localedir).glob(f"*/LC_MESSAGES/{DOMAIN}.mo")):
		code = catalog.parent.parent.name
		if code == "en":
			continue
		try:
			with catalog.open("rb") as catalog_file:
				info = gettext.GNUTranslations(catalog_file).info()
			name = info.get("language-team", "").split("<", 1)[0].strip()
		except (OSError, EOFError):
			log.exception(f"Failed to open catalog {code}")
			name = ""
		languages.append((code, name or code))
	return languages


def init(localedir: str | None = None, language: str | None = None) -> None:
	"""Initialize Python and native gettext using the configured language."""
	global _translation, _catalogs, _localedir

	if localedir is None:
		localedir = get_locale_path()
	if language is None:
		language = _get_configured_language()
	_localedir = localedir
	if language:
		# GNU gettext, including the native implementation used by GtkBuilder,
		# consults LANGUAGE before choosing a catalog.
		os.environ["LANGUAGE"] = language
	try:
		locale.setlocale(locale.LC_ALL, "")
	except locale.Error:
		logging.getLogger(__name__).warning("Cannot activate the requested system locale")
	locale.bindtextdomain(DOMAIN, localedir)  # Native gettext used by GTK.
	locale.textdomain(DOMAIN)
	languages = [language] if language else None
	_translation = gettext.translation(DOMAIN, localedir=localedir, languages=languages, fallback=True)
	_catalogs = gettext.find(DOMAIN, localedir=localedir, languages=languages, all=True)
	builtins._ = _
	# Logging isn't setup yet, so it won't be visible, we log elsewhere later too
	log_selection()


def _(message: str) -> str:
	return _translation.gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
	return _translation.ngettext(singular, plural, count)
