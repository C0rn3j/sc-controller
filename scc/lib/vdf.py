"""VDF file reader.

Copyright (C) 2017 Kozec

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License version 2 as published by
the Free Software Foundation

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""
import vdf


def parse_vdf(file):
	return vdf.parse(file, mapper=vdf.VDFDict, merge_duplicate_keys=False)


def ensure_list(value):
	"""If value is list, returns same value.

	Otherwise, returns [ value ]
	"""
	return value if type(value) == list else [ value ]


if __name__ == "__main__":
	print(parse_vdf(open('test.vdf', "r")))
