"""Native Bluetooth packet reassembly, without controller hardware."""
import ctypes
import os
from pathlib import Path
import shlex
import subprocess
import sysconfig

import pytest

from scc.constants import SCButtons
from scc.drivers.sc_by_bt import SCByBtC, SCByBtCPtr


@pytest.fixture(scope="module")
def decoder(tmp_path_factory):
	library = tmp_path_factory.mktemp("sc_by_bt") / "decoder.so"
	source = Path(__file__).resolve().parents[1] / "scc/drivers/sc_by_bt.c"
	subprocess.run([
		*shlex.split(sysconfig.get_config_var("CC")), "-shared", "-fPIC",
		"-I" + sysconfig.get_path("include"), str(source), "-o", str(library),
	], check=True, capture_output=True)
	lib = ctypes.CDLL(str(library))
	lib.read_input.argtypes = [SCByBtCPtr]
	lib.read_input.restype = ctypes.c_int
	return lib


@pytest.fixture
def receiver(decoder):
	r, w = os.pipe()
	state = SCByBtC(fileno=r)
	def send(header, payload=b"", report_id=3):
		assert len(payload) <= 18
		os.write(w, bytes([report_id, header]) + payload.ljust(18, b"\x00"))
		return decoder.read_input(ctypes.byref(state))
	try:
		yield state, send
	finally:
		os.close(r)
		os.close(w)


BUTTON_A = b"\x10\x00\x80\x00\x00"


def test_orphan_fragment_cannot_generate_phantom_buttons(receiver, capfd):
	state, send = receiver
	assert send(0x41, b"\x10\x00\xff\x7f\x00") == 0
	assert state.state.buttons == 0
	assert "out-of-sequence" in capfd.readouterr().err
	assert send(0x40, BUTTON_A) == 1
	assert state.state.buttons == SCButtons.A


@pytest.mark.parametrize("sequence", [(0, 2), (0, 1, 1), (0, 1, 3)])
def test_missing_or_duplicate_fragment_discards_message(receiver, sequence):
	state, send = receiver
	before = bytes(state.state)
	for number in sequence[:-1]:
		assert send(number) == 0
	assert send(sequence[-1] | 0x40, b"\xff" * 18) == 0
	assert state.long_packet == 0
	assert bytes(state.state) == before
	assert send(0x40, BUTTON_A) == 1
	assert state.state.buttons == SCButtons.A


def test_new_first_fragment_replaces_incomplete_message(receiver):
	state, send = receiver
	assert send(0, b"\x10\x00\xff\x7f\x00") == 0
	assert send(0x40, BUTTON_A) == 1
	assert state.state.buttons == SCButtons.A


def test_truncated_payload_does_not_change_state(receiver, capfd):
	state, send = receiver
	assert send(0x40, BUTTON_A) == 1
	before = bytes(state.state)
	# Buttons + gyro require 23 bytes; a single fragment only has 16.
	assert send(0x40, b"\x10\x18" + bytes(16)) == 0
	assert bytes(state.state) == before
	assert "truncated message" in capfd.readouterr().err


def test_valid_multifragment_message_and_button_release(receiver):
	state, send = receiver
	# Buttons, triggers, stick, pads and gyro. Right pad crosses a fragment boundary.
	payload = b"\xb0\x1b\x00\x00\x40" + bytes(10) + b"\x34\x12\x78\x56" + bytes(20)
	assert send(0, payload[:18]) == 0
	assert send(1, payload[18:36]) == 0
	assert send(0x42, payload[36:]) == 1
	assert state.state.buttons == SCButtons.LSTICKPRESS
	assert (state.state.rpad_x, state.state.rpad_y) == (0x1234, 0x5678)
	assert send(0x40, b"\x10\x00" + bytes(3)) == 1
	assert state.old_state.buttons == SCButtons.LSTICKPRESS
	assert state.state.buttons == 0


def test_oversized_sequence_preserves_controller_state(receiver, capfd):
	state, send = receiver
	for number in range(14):
		assert send(number) == 0
	before = bytes(state.state)
	assert send(0x4e, b"\xaa" * 18) == 0
	assert state.long_packet == 0
	assert bytes(state.state) == before
	assert "packet buffer overflow" in capfd.readouterr().err


def test_unexpected_report_id_is_ignored(receiver):
	state, send = receiver
	assert send(0x40, BUTTON_A, report_id=4) == 0
	assert state.state.buttons == 0
