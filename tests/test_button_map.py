"""What an unmapped HID input bit maps to.

The decoder turns each entry into `1 << button_map[i]`, so every value in
0..BUTTON_COUNT-1 names a real button. The "maps to nothing" sentinel was
BUTTON_COUNT - 1 -- bit 31, which is RSTICKPRESS -- so on a JSON-configured
controller every input bit the config did not name pressed the right stick.

It only became fixable once the C guard rejected 32 rather than 33: before
that, an out-of-range sentinel would have been shifted into a uint32_t by 32,
which is undefined behaviour rather than a no-op.
"""
import pytest

try:
	# OSError, not ImportError, when libhiddrv is unbuilt.
	from scc.drivers import hiddrv
except (ImportError, OSError) as e:
	pytest.skip("hiddrv unavailable: %s" % (e,), allow_module_level=True)

from scc.constants import SCButtons


def test_the_sentinel_is_not_a_real_button():
	"""The whole bug in one line: it has to be outside the valid range."""
	assert hiddrv.BUTTON_UNMAPPED >= hiddrv.BUTTON_COUNT, (
		"%r names bit %d, which is a button"
		% (hiddrv.BUTTON_UNMAPPED, hiddrv.BUTTON_UNMAPPED))


def test_bit_31_is_rstickpress_and_so_cannot_be_the_sentinel():
	"""Pins why BUTTON_COUNT - 1 was the wrong choice, so that reverting to it
	fails here rather than on someone's controller.
	"""
	assert int(SCButtons.RSTICKPRESS).bit_length() - 1 == hiddrv.BUTTON_COUNT - 1
	assert hiddrv.BUTTON_UNMAPPED != hiddrv.BUTTON_COUNT - 1


def test_an_empty_config_maps_nothing_to_a_button():
	config = {"buttons": {}}
	m = hiddrv.HIDController._build_button_map(hiddrv.HIDController, config)
	assert set(m) == {hiddrv.BUTTON_UNMAPPED}


def test_named_buttons_survive_and_the_rest_stay_unmapped():
	first = hiddrv.FIRST_BUTTON
	config = {"buttons": {str(first): "A", str(first + 1): "RSTICKPRESS"}}
	m = hiddrv.HIDController._build_button_map(hiddrv.HIDController, config)

	assert m[0] == int(SCButtons.A).bit_length() - 1
	assert m[1] == int(SCButtons.RSTICKPRESS).bit_length() - 1
	assert set(m[2:]) == {hiddrv.BUTTON_UNMAPPED}, (
		"unnamed bits map to a real button again")


def test_rstickpress_is_reachable_only_when_asked_for():
	"""The regression this guards: with the old sentinel, a config naming no
	buttons at all still produced a map full of RSTICKPRESS's bit.
	"""
	rstick_bit = int(SCButtons.RSTICKPRESS).bit_length() - 1
	m = hiddrv.HIDController._build_button_map(hiddrv.HIDController, {"buttons": {}})
	assert rstick_bit not in set(m)


def test_the_sentinel_fits_the_c_field():
	"""button_map is a uint8 array; anything wider is silently truncated into
	a valid bit position.
	"""
	assert 0 <= hiddrv.BUTTON_UNMAPPED <= 255


def test_an_unknown_mask_is_reported_as_unmapped():
	assert hiddrv.button_to_bit(0) == hiddrv.BUTTON_UNMAPPED
