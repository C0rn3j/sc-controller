"""Build version, with a fallback for unbuilt source archives."""

try:
	from scc._version import __version__
except ModuleNotFoundError as error:
	if error.name != "scc._version":
		raise
	__version__ = "0.0.0+unknown"
