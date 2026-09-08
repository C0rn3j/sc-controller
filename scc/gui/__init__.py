from gi.repository import GLib

from scc.constants import SCButtons

BUTTON_ORDER = (
	SCButtons.A,
	SCButtons.B,
	SCButtons.X,
	SCButtons.Y,
	SCButtons.BACK,
	SCButtons.C,
	SCButtons.START,
	SCButtons.LB,
	SCButtons.RB,
	SCButtons.LT,
	SCButtons.RT,
	SCButtons.LSTICKPRESS,
	SCButtons.LPAD,
	SCButtons.RPAD,
	SCButtons.RGRIP,
	SCButtons.LGRIP,
)

def log_writer(log_level, fields, n_fields, user_data):
	message = GLib.log_writer_format_fields(
		log_level,
		fields,
		False,
	)

	# https://gitlab.gnome.org/GNOME/gtk/-/work_items/4446
	if "(slider) reported min width -2, but sizes must be >= 0" in message \
	or "(slider) reported min height -2, but sizes must be >= 0" in message:
		return GLib.LogWriterOutput.HANDLED

	return GLib.log_writer_default(
		log_level,
		fields,
		user_data,
	)


GLib.log_set_writer_func(log_writer, None)
