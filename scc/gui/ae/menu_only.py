#!/usr/bin/env python3
"""SC-Controller - Action Editor - Menu Only Component

Displays page that can edito only MenuAction
"""

import logging

from scc.actions import Action
from scc.gui.ae import AEComponent
from scc.gui.ae.menu_action import MenuActionCofC
from scc.special_actions import MenuAction, PositionModifier
from scc.tools import _

log = logging.getLogger("AE.SA")

__all__ = ["MenuOnlyComponent"]


class MenuOnlyComponent(AEComponent, MenuActionCofC):
	GLADE = "ae/menu_only.glade"
	NAME = "menu_only"
	CTXS = Action.AC_MENU
	PRIORITY = 0

	def __init__(self, app, editor):
		AEComponent.__init__(self, app, editor)
		MenuActionCofC.__init__(self)
		self._userdata_load_started = False
		self._recursing = False

	def shown(self):
		if not self._userdata_load_started:
			self._userdata_load_started = True
			self.load_menu_list()

	def set_action(self, mode, action):
		if isinstance(action, PositionModifier):
			action = action.action
		if isinstance(action, MenuAction):
			self._current_menu = action.menu_id

	def get_button_title(self):
		return _("Menu")

	def handles(self, mode, action):
		"""Not visible by default"""
		return False
