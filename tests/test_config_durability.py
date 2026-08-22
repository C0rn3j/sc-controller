"""Configuration must survive a bad save and a bad parse.

Two faults compounded here. save() wrote in place, so anything that killed the
process mid-write left truncated JSON; and reload() answered any parse failure
by calling create(), which overwrites the file with defaults. Together they
turned one interrupted write into "every setting the user ever chose is gone",
with no copy kept. It happened twice on the maintainer's machine before anyone
worked out why.
"""
import json
import os

import pytest

from scc.config import Config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
	"""A Config rooted in a temp dir, so nothing here touches ~/.config/scc."""
	monkeypatch.setattr("scc.config.get_config_path", lambda: str(tmp_path))
	c = Config()
	c.filename = os.path.join(str(tmp_path), "config.json")
	return c


def test_a_saved_config_reads_back(cfg):
	cfg.set("recent_max", 7)
	cfg.save()
	fresh = Config()
	fresh.filename = cfg.filename
	fresh.load()
	assert fresh["recent_max"] == 7


def test_save_leaves_no_temp_files_behind(cfg):
	cfg.save()
	leftovers = [f for f in os.listdir(os.path.dirname(cfg.filename)) if ".tmp." in f]
	assert leftovers == [], "temp files accumulate in the config directory: %r" % leftovers


def test_the_file_is_never_seen_half_written(cfg, monkeypatch):
	"""The window that caused this: a reader arriving mid-save must see either
	the old contents or the new ones, never a truncated file.
	"""
	cfg.set("recent_max", 1)
	cfg.save()
	seen = []

	real_replace = os.replace

	def watched_replace(src, dst):
		# whatever a reader would find at the moment before the swap
		with open(dst) as f:
			seen.append(f.read())
		return real_replace(src, dst)

	monkeypatch.setattr(os, "replace", watched_replace)
	cfg.set("recent_max", 2)
	cfg.save()

	assert seen, "save() did not go through os.replace; it is not atomic"
	assert json.loads(seen[0])["recent_max"] == 1, "the old file was modified in place"


def test_an_unreadable_config_is_kept_not_deleted(cfg):
	"""The part that actually lost data."""
	with open(cfg.filename, "w") as f:
		f.write('{"recent_max": 7, "gui": {')      # truncated, as an interrupted write leaves it
	cfg.reload()

	backup = cfg.filename + ".broken.1"
	assert os.path.exists(backup), "the unreadable config was discarded"
	with open(backup) as f:
		assert f.read() == '{"recent_max": 7, "gui": {'
	assert os.path.exists(cfg.filename), "no usable config was created"
	json.loads(open(cfg.filename).read())          # defaults, and valid


def test_a_second_failure_does_not_overwrite_the_first_backup(cfg):
	"""The first backup holds the real settings; a later, emptier failure must
	not clobber it.
	"""
	with open(cfg.filename, "w") as f:
		f.write("the original settings")
	cfg.reload()
	with open(cfg.filename, "w") as f:
		f.write("garbage from a later run")
	cfg.reload()

	with open(cfg.filename + ".broken.1") as f:
		assert f.read() == "the original settings"
	assert os.path.exists(cfg.filename + ".broken.2")


def test_a_missing_config_is_just_a_first_run(cfg):
	"""No file is not an error and must not leave a .broken behind.

	(Config.__init__ already wrote one, so remove it to get back to the
	genuine first-run state.)
	"""
	os.unlink(cfg.filename)
	cfg.reload()
	assert os.path.exists(cfg.filename)
	assert not os.path.exists(cfg.filename + ".broken.1")
