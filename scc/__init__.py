"""SC-Controller.

Copyright (C) 2018 Kozec

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

import os
import subprocess

# AppImageBuilder relies on its exec hooks to resolve relative shebang and ELF
# interpreter paths. Python 3.13+ uses posix_spawn() in more situations, which
# bypasses that compatibility path.
if os.environ.get("APPDIR") and hasattr(subprocess, "_USE_POSIX_SPAWN"):
	subprocess._USE_POSIX_SPAWN = False
