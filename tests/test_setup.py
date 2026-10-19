import pkgutil
import tomllib

import scc


class TestSetup:
	"""Test if SCC should be installable."""

	def test_packages(self):
		"""Check that every discovered SCC package is listed in pyproject.toml"""
		# Load the packages from pyproject.toml
		with open("pyproject.toml", "rb") as file:
			pyproject = tomllib.load(file)
		packages = pyproject["tool"]["setuptools"]["packages"]

		for importer, modname, ispkg in pkgutil.walk_packages(path=scc.__path__, prefix="scc.", onerror=lambda x: None):
			if ispkg:
				assert modname in packages, f"Package '{modname}' is missing from pyproject.toml"
