#!/usr/bin/env python3
import os
import sys


def try_run(cmd: str) -> None:
	if os.system(cmd) != 0:
		sys.exit(1)


def merge(file_from: str, file_to: str, from_: str, to: str) -> None:
	"""Merge lines from line containing 'from_' to line containing 'to' from f1 to f2."""
	lines1, inside = [], False
	with open(file_from) as file:
		for line in file:
			if from_ in line.strip("\r\n\t "):
				inside = True
			elif to in line.strip("\r\n\t "):
				inside = False
			if inside:
				lines1.append(line)

	lines2, inside = [], False
	with open(file_to) as file:
		for line in file:
			if from_ in line.strip("\r\n\t "):
				inside = True
				lines2 += lines1
			elif to in line.strip("\r\n\t "):
				inside = False
			elif not inside:
				lines2.append(line)

	open(file_to, "w").write("".join(lines2))


def main() -> None:
	"""Clone our wiki and merge actions.md into Custom-Action-Examples-and-Explanations.md."""
	if not os.path.exists("sc-controller.wiki/.git"):
		try_run("git clone 'https://github.com/C0rn3j/sc-controller.wiki.git'")

	os.chdir("sc-controller.wiki")
	try_run("git pull")
	try_run("git reset master")

	merge(
		"../docs/actions.md",
		"Custom-Action-Examples-and-Explanations.md",
		'# <a name="actions">',
		'# <a name="examples2">',
	)

	try_run('git commit -a -m "Updated wiki from docs"')


if __name__ == "__main__":
	main()
