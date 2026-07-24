"""SC-Controller - Import / Export Dialog"""
from __future__ import annotations

import json
import logging
import tarfile
import traceback
from typing import TYPE_CHECKING

from scc.gui.editor import ComboSetter, Editor
from scc.tools import _, find_profile, profile_is_default, profile_is_override

from .export import Export
from .import_sccprofile import ImportSccprofile
from .import_vdf import ImportVdf

if TYPE_CHECKING:
	from typing import Literal

	from gi.repository import GObject

log = logging.getLogger("IE.Dialog")


class Dialog(Editor, ComboSetter, Export, ImportVdf, ImportSccprofile):
	GLADE = "import_export.glade"

	def __init__(self, app) -> None:
		self.app = app
		self._back = []
		self._recursing: bool = False
		self._next_callback = None
		self.setup_widgets()
		Export.__init__(self)
		ImportVdf.__init__(self)
		ImportSccprofile.__init__(self)

	@staticmethod
	def determine_type(filename: str) -> Literal["sccprofile", "vdffz", "sccprofile.tar.gz", "vdf"] | None:
		"""Detects and returns type of passed file, if it can be imported.

		Returns one of 'sccprofile', 'sccprofile.tar.gz', 'vdf', 'vdffz' or None if type is not supported.
		"""
		try:
			with open(filename, "rb") as file:
				f = file.read(1024)
		except Exception:
			# File not readable
			log.error(traceback.format_exc())
			return None
		try:
			if f.decode("utf-8").strip(" \t\r\n").startswith("{"):
				# Looks like json
				data = json.loads(open(filename).read())
				if "buttons" in data and "gyro" in data:
					return "sccprofile"
				if "GameName" in data and "FileName" in data:
					return "vdffz"
		except Exception:
			# Definitelly not json
			pass

		if f[0:2] == b"\x1f\x8b":
			# gzip, hopefully tar.gz
			try:
				with tarfile.open(filename, "r:gz") as tar:
					names = [x.name for x in tar]
				any_profile = any([x.endswith(".sccprofile") for x in names])
				if any_profile and "profile-name" in names:
					return "sccprofile.tar.gz"
			except Exception:
				# Not a tarball
				pass

		# Rest is decided by extension
		if filename.endswith(".sccprofile.tar.gz"):
			return "sccprofile.tar.gz"
		if filename.endswith(".vdf"):
			return "vdf"
		# Fallbacks if above fails
		if filename.endswith(".sccprofile"):
			return "sccprofile"
		if filename.endswith(".vdffz"):
			return "vdffz"
		return None

	@staticmethod
	def check_name(name: str) -> bool:
		if len(name.strip()) <= 0:
			return False
		if "/" in name:
			return False
		if find_profile(name):
			# Profile already exists
			if profile_is_default(name) and not profile_is_override(name):
				# Existing profile is default and has no override yet
				return True
			return False
		return True

	def import_file(self, filename: str, filetype: str | None = None) -> None:
		"""Attempts to import passed file.

		Switches to apropriate page automatically, or, if file cannot be
		imported, does nothing.
		"""
		filetype = filetype or Dialog.determine_type(filename)
		if filetype == "sccprofile":
			self.import_scc(filename=filename)
		elif filetype == "sccprofile.tar.gz":
			self.import_scc_tar(filename=filename)
		elif filetype in ("vdf", "vdffz"):
			self.import_vdf(filename=filename)

	def next_page(self, page: GObject.Object | None) -> None:
		stDialog = self.builder.get_object("stDialog")
		btBack = self.builder.get_object("btBack")
		self._back.append(stDialog.get_visible_child())
		stDialog.set_visible_child(page)
		btBack.set_visible(True)
		self._page_selected(page)

	def _page_selected(self, page: GObject.Object | None) -> None:
		stDialog = self.builder.get_object("stDialog")
		hbDialog = self.builder.get_object("hbDialog")
		hbDialog.set_title(stDialog.child_get_property(page, "title"))
		hname = f"on_{page.get_name()}_activated"
		if hasattr(self, hname):
			getattr(self, hname)()

	def enable_next(self, enabled: bool = True, callback=None) -> GObject.Object | None:
		"""Makes 'Next' button visible and assigns callback that will be called when button is clicked.

		'Next' button is automatically hidden before callback is called.

		Returns 'Next' button widget.
		"""
		assert not enabled or callback
		btNext = self.builder.get_object("btNext")
		btNext.set_visible(enabled)
		btNext.set_use_stock(False)
		btNext.set_sensitive(True)
		btNext.set_label(_("Next"))
		self._next_callback = callback
		return btNext

	def on_btNext_clicked(self, *a) -> None:
		cb = self._next_callback
		self.enable_next(enabled=False)
		cb()

	def on_btBack_clicked(self, *a) -> None:
		btBack = self.builder.get_object("btBack")
		stDialog = self.builder.get_object("stDialog")
		btSaveAs = self.builder.get_object("btSaveAs")
		btNext = self.builder.get_object("btNext")
		page, self._back = self._back[-1], self._back[:-1]
		stDialog.set_visible_child(page)
		btNext.set_visible(False)
		btSaveAs.set_visible(False)
		btBack.set_visible(len(self._back) > 0)
		self._page_selected(page)

	def on_btExport_clicked(self, *a) -> None:
		grSelectProfile = self.builder.get_object("grSelectProfile")
		self.next_page(grSelectProfile)

	def on_btImportVdf_clicked(self, *a) -> None:
		grVdfImport = self.builder.get_object("grVdfImport")
		self.next_page(grVdfImport)
