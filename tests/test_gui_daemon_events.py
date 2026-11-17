"""A continuous daemon event stream must yield to GUI rendering."""

from types import SimpleNamespace

from gi.repository import Gio, GLib

from scc.gui.daemon_manager import DaemonManager


def test_daemon_stream_yields_to_redraw_and_preserves_partial_lines():
	stream = Gio.MemoryInputStream.new_from_data(
		b"test-event\n" * 2000, None,
	)
	context = GLib.MainContext.default()
	events = []
	state = SimpleNamespace(
		connection=SimpleNamespace(get_input_stream=lambda: stream),
		buffer=b"",
		emit=lambda signal, line: events.append(line),
	)
	state._read_data = lambda: DaemonManager._read_data(state)
	state._on_read_data = lambda source, result: DaemonManager._on_read_data(state, source, result)
	state._on_daemon_died = lambda: setattr(state, "connection", None)
	rendered_after = []
	redraw = GLib.idle_add(
		lambda: rendered_after.append(len(events)) or False,
		priority=120,
	)
	try:
		state._read_data()
		for _ in range(1000):
			if state.connection is None:
				break
			context.iteration(False)
		assert state.connection is None
		assert rendered_after == [0]
		assert events == ["test-event"] * 2000
		assert state.buffer == b""
	finally:
		if not rendered_after:
			GLib.source_remove(redraw)
		stream.close(None)
