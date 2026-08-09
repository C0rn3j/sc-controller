from unittest.mock import patch

from scc.osd.menu_generators import GameListMenuGenerator


class App:
	def __init__(self, name: str, categories: str = "Game;") -> None:
		self.name = name
		self.categories = categories

	def get_categories(self) -> str:
		return self.categories

	def get_display_name(self) -> str:
		return self.name

	def get_icon(self):
		return None


def test_games_are_sorted_case_insensitively() -> None:
	GameListMenuGenerator._games = None
	apps = [App("zeta"), App("Alpha"), App("beta"), App("Not a game", "Utility;")]
	with patch("scc.osd.menu_generators.Gio.AppInfo.get_all", return_value=apps):
		items = GameListMenuGenerator().generate(None)

	assert [item.label for item in items] == ["Alpha", "beta", "zeta"]
	assert [item.id for item in items] == ["0", "1", "2"]
	GameListMenuGenerator._games = None
