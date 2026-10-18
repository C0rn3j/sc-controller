"""SC Controller - About dialog."""

import os

from scc.gui.editor import Editor
from scc.version import __version__


class AboutDialog(Editor):
	"""Standard looking about dialog."""

	GLADE = "about.ui"

	def __init__(self, app) -> None:
		self.app = app
		self.setup_widgets()

	def setup_widgets(self) -> None:
		"""Setup widgets and get and set app version in the About."""
		Editor.setup_widgets(self)
		self.builder.get_object("image1").set_filename(
			os.path.join(self.app.imagepath, "sc-controller-small.svg"),
		)

		# Display version in UI
		self.builder.get_object("lblVersion").set_label("v" + __version__)

	def show(self, modal_for) -> None:
		if modal_for:
			self.window.set_transient_for(modal_for)
			self.window.set_modal(True)
		self.window.set_visible(True)

	def on_dialog_response(self, *a) -> None:
		self.close()
