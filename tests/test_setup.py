import pkgutil

import toml

import scc


class TestSetup:
	"""Test if SCC should be installable."""

	def test_packages(self):
		"""Test if every known Action is documented in docs/actions.md."""
		try:
			import gi
			gi.require_version('Gtk', '3.0')
			gi.require_version('GdkX11', '3.0')
			gi.require_version('Rsvg', '2.0')
		except ImportError:
			pass

		# Load the packages from pyproject.toml
		pyproject = toml.load("pyproject.toml")
		packages = pyproject["tool"]["setuptools"]["packages"]

		for importer, modname, ispkg in pkgutil.walk_packages(path=scc.__path__, prefix="scc.", onerror=lambda x: None):
			if ispkg:
				assert modname in packages, f"Package '{modname}' is not being installed by setup.py"
