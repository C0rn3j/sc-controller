"""Where scc.uinput gets its input-event constants from.

The lookup has three candidates and used to end in an unguarded `else`, so a
machine with neither kernel headers nor the bundled copy got FileNotFoundError
on /usr/include/linux/input.h -- a path it had never been told to care about,
raised from inside an import. That is precisely the state a build sandbox is
in, and it cost a release round trip to diagnose from the far end.
"""
import os

import pytest

uinput = pytest.importorskip("scc.uinput")

SYSTEM = os.path.join("/usr/include", "linux/input-event-codes.h")
BUNDLED = os.path.join(os.path.dirname(uinput.__file__), "input-event-codes.h")
LEGACY = os.path.join("/usr/include", "linux/input.h")


def only(*present):
	"""An os.path.exists that admits to nothing but `present`."""
	return lambda path: path in present


def test_the_system_header_wins():
	assert uinput._find_event_codes_header(only(SYSTEM, BUNDLED, LEGACY)) == (
		"/usr/include", "linux/input-event-codes.h")


def test_the_bundled_copy_is_used_when_the_system_has_none():
	"""An installed package carries its own copy exactly so it does not need
	the host to have kernel headers; SteamOS ships none.
	"""
	directory, header = uinput._find_event_codes_header(only(BUNDLED))
	assert os.path.join(directory, header) == BUNDLED


def test_pre_3_14_headers_still_work():
	"""input-event-codes.h was split out of input.h in kernel 3.14."""
	assert uinput._find_event_codes_header(only(LEGACY)) == (
		"/usr/include", "linux/input.h")


def test_finding_nothing_says_so_instead_of_erroring_on_a_stray_path():
	with pytest.raises(ImportError) as e:
		uinput._find_event_codes_header(only())
	message = str(e.value)
	assert "kernel headers" in message, "no hint at the fix: %r" % message
	for path in (SYSTEM, BUNDLED, LEGACY):
		assert path in message, "did not say it looked in %s" % path


def test_this_machine_resolves_one_of_them():
	"""Not a tautology: it asserts the real lookup succeeds wherever the suite
	runs, which is the thing that broke in the Nix sandbox.
	"""
	directory, header = uinput._find_event_codes_header()
	assert os.path.exists(os.path.join(directory, header))
