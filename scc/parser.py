"""SC Controller - ActionParser.

Parses action(s) expressed as string or in dict loaded from json file into
one or more Action instances.
"""
from __future__ import annotations

import sys
import token as TokenType
from enum import EnumType
from tokenize import TokenError, generate_tokens
from typing import NamedTuple

from scc.actions import Action, MultiAction, NoAction, RangeOP
from scc.constants import PARSER_CONSTANTS, STICK, HapticPos, SCButtons
from scc.macros import Macro
from scc.tools import nameof
from scc.uinput import Axes, Keys, Rels


class ParseError(Exception):
	pass


def build_action_constants() -> dict:
	"""Generate dicts for ActionParser.CONSTS."""
	rv = {
		"Keys": Keys,
		"Axes": Axes,
		"Rels": Rels,
		"HapticPos": HapticPos,
		"None": NoAction(),
		"True": True,
		"False": False,
	}
	for c in PARSER_CONSTANTS:
		rv[c] = c
	for tpl in (Keys, Axes, Rels, SCButtons, HapticPos):
		for x in tpl:
			rv[x.name] = x
	for b in ("A", "B", "X", "Y", "START", "SELECT"):
		name = f"BTN_{b}"
		rv[name] = getattr(Keys, name)
	return rv


class ActionParser(object):
	"""Parse action expressed as string into Action instances.

	Usage:
		ap = ActionParser(string)
		action = ap.parse()
		if action is None:
			error = ap.get_error()
			# do something with error
	"""

	class Token(NamedTuple):
		type: int
		value: str

	CONSTS = build_action_constants()


	def __init__(self, string:str = ""):
		self.restart(string)


	def from_json_data(self, data: dict, key: str | None = None):
		"""Convert dict stored in profile file into action.

		May throw ParseError.
		"""
		if key is not None:
			# Don't fail if called for non-existent key, return NoAction instead.
			# Using this is shorter than calling 'if button in data["buttons"]: ...' everywhere
			if key in data:
				return self.from_json_data(data[key], None)
			return NoAction()

		a = self.restart(data["action"]).parse() or NoAction() if "action" in data else NoAction()
		decoders = set()
		for data_key in data:
			if data_key in Action.PKEYS:
				decoders.add(Action.PKEYS[data_key])

		if decoders:
			for cls in sorted(decoders, key=lambda a : a.PROFILE_KEY_PRIORITY ):
				a = cls.decode(data, a, self, 0) # Profile version is not yet used anywhere
		return a


	def restart(self, s: str | bytes) -> ActionParser:
		"""Restart parsing with a new string.

		Returns self for chaining.
		"""
		if type(s) is bytes:
			s = s.decode("utf-8")

		try:
			self.tokens = [
				ActionParser.Token(token_type, string)
				for token_type, string, *_
				in generate_tokens( iter([s]).__next__ )
				if token_type != TokenType.ENDMARKER
			]
		except TokenError:
			self.tokens = None
		self.index = 0
		return self


	def _next_token(self) -> Token:
		if self.tokens is None:
			sys.exit("This shouldn't happen, self.tokens is none")
		rv = self.tokens[self.index]
		self.index += 1
		return rv


	def _peek_token(self) -> Token:
		"""As _next_token, but without increasing counter."""
		if self.tokens is None:
			sys.exit("This shouldn't happen, self.tokens is none")
		return self.tokens[self.index]


	def _tokens_left(self) -> bool:
		"""Return True if there are any tokens left."""
		if self.tokens is None:
			sys.exit("This shouldn't happen, self.tokens is none")
		return self.index < len(self.tokens)


	def _parse_parameter(self):
		"""Parse a single parameter."""
		t = self._next_token()
		while t.type in (TokenType.NL, TokenType.NEWLINE) or t.value == "\n":
			if not self._tokens_left():
				raise ParseError("Expected parameter at end of string")
			t = self._next_token()

		if t.type == TokenType.NAME:
			# Constant or action used as parameter
			if self._tokens_left() and self._peek_token().type == TokenType.OP and self._peek_token().value == "(":
				# Action used as parameter
				self.index -= 1 # go step back and reparse as action
				parameter = self._parse_action()
			elif self._tokens_left() and t.value in Action.ALL and type(Action.ALL[t.value]) is dict and self._peek_token().value == ".":
				# SOMETHING.Action used as parameter
				self.index -= 1 # go step back and reparse as action
				parameter = self._parse_action()
			else:
				# Constant
				if t.value not in ActionParser.CONSTS:
					raise ParseError("Expected parameter, got '%s' which is not defined" % (t.value,))
				parameter = ActionParser.CONSTS[t.value]

			# Check for dots
			while self._tokens_left() and self._peek_token().type == TokenType.OP and self._peek_token().value == '.':
				self._next_token()
				if not self._tokens_left():
					raise ParseError("Expected NAME after '.'")

				t = self._next_token()
				if not hasattr(parameter, t.value):
					raise ParseError("%s has no attribute '%s'" % (parameter, t.value,))
				parameter = getattr(parameter, t.value)

			# Check for ranges (<, >, <=, >=)
			if self._tokens_left() and self._peek_token().type == TokenType.OP:
				if self._peek_token().value in RangeOP.OPS:
					op = self._next_token().value
					# TODO: Maybe other axes
					if parameter not in (STICK, SCButtons.LT, SCButtons.RT, SCButtons.X, SCButtons.Y):
						raise ParseError("'%s' is not trigger nor axis" % (nameof(parameter), ))
					if not self._tokens_left():
						raise ParseError("Excepted number after '%s'" % (op, ))
					try:
						number = float(self._next_token().value)
					except ValueError:
						raise ParseError("Excepted number after '%s'" % (op, ))
					parameter = RangeOP(parameter, op, number)

			return parameter

		if t.type == TokenType.OP and t.value == "-":
			if not self._tokens_left() or self._peek_token().type != TokenType.NUMBER:
				raise ParseError("Expected number after '-'")
			return - self._parse_number()

		if t.type == TokenType.NUMBER:
			self.index -= 1
			return self._parse_number()

		if t.type == TokenType.STRING:
			return t.value[1:-1]

		raise ParseError("Expected parameter, got '%s'" % (t.value,))


	def _parse_number(self) -> float | int:
		t = self._next_token()
		if t.type != TokenType.NUMBER:
			raise ParseError("Expected number, got '%s'" % (t.value,))
		if "." in t.value or "e" in t.value.lower():
			return float(t.value)
		if t.value.lower().startswith("0x"):
			return int(t.value, 16)
		if t.value.lower().startswith("0b"):
			return int(t.value, 2)
		return int(t.value)


	def _parse_parameters(self) -> list:
		"""Parse a parameter list."""
		# Check and skip over '('
		t = self._next_token()
		if t.type != TokenType.OP or t.value != "(":
			raise ParseError("Expected '(' of parameter list, got '%s'" % (t.value,))

		parameters = []
		while self._tokens_left():
			# Check for ')' that would end parameter list
			t = self._peek_token()
			if t.type == TokenType.OP and t.value == ")":
				self._next_token()
				return parameters

			# Parse one parameter
			parameters.append(self._parse_parameter())
			# Check if next token is either ')' or ','
			t = self._peek_token()
			while t.type in (TokenType.NL, TokenType.NEWLINE) or t.value == "\n":
				self._next_token()
				if not self._tokens_left():
					raise ParseError("Expected ',' or end of parameter list after parameter '%s'" % (parameters[-1],))
				t = self._peek_token()
			if t.type == TokenType.OP and t.value == ")":
				pass
			elif t.type == TokenType.OP and t.value == ",":
				self._next_token()
			else:
				raise ParseError("Expected ',' or end of parameter list after parameter '%s'" % (parameters[-1],))


		# Code shouldn't reach here, unless there is not closing ')' in parameter list
		raise ParseError("Unmatched parenthesis")


	def _create_action(self, cls, *pars):
		try:
			return cls(*pars)
		except ValueError as e:
			raise ParseError(str(e))
		except TypeError as e:
			print(e, file=sys.stderr)
			raise ParseError("Invalid number of parameters for '%s'" % (cls.COMMAND))


	def _parse_action(self, frm: dict = Action.ALL):
		"""Parse one action, that is one of: something(params) | something() | something."""
		# Check if next token is TokenType.NAME and grab action name from it
		t = self._next_token()
		if t.type != TokenType.NAME:
			raise ParseError("Expected action name, got '%s'" % (t.value,))
		if t.value not in frm:
			raise ParseError("Unknown action '%s'" % (t.value,))
		action_name = t.value
		action_class = frm[action_name]
		# Check if there are any tokens left - if not, return action without parameters
		if not self._tokens_left():
			return self._create_action(action_class)

		# Check if token after action name is parenthesis and if yes, parse parameters from it
		t = self._peek_token()
		parameters = []
		if t.type == TokenType.OP and t.value == ".":
			# ACTION dict can have nested dicts; SOMETHING.action
			if type(action_class) is dict:
				self._next_token()
				return self._parse_action(action_class)
			raise ParseError("Unexpected '.' after '%s'" % (action_name,))
		if t.type == TokenType.OP and t.value == "(":
			parameters = self._parse_parameters()
			if not self._tokens_left():
				return self._create_action(action_class, *parameters)
			t = self._peek_token()

		# ... or, if it is one of ';', 'and' or 'or' and if yes, parse next action
		if t.type == TokenType.NAME and t.value == "and":
			# Two (or more) actions joined by 'and'
			self._next_token()
			if not self._tokens_left():
				raise ParseError("Expected action after 'and'")
			action1 = self._create_action(action_class, *parameters)
			action2 = self._parse_action()
			return MultiAction(action1, action2)

		if t.type in (TokenType.NL, TokenType.NEWLINE) or t.value == "\n":
			# Newline can be used to join actions instead of 'and'
			self._next_token()
			if not self._tokens_left():
				# Newline at end of string is not error
				return self._create_action(action_class, *parameters)
			t = self._peek_token()
			if t.type == TokenType.OP and t.value in (")", ","):
				# ')' starts next line
				return self._create_action(action_class, *parameters)
			action1 = self._create_action(action_class, *parameters)
			action2 = self._parse_action()
			return MultiAction(action1, action2)

		if t.type == TokenType.OP and t.value == ";":
			# Two (or more) actions joined by ';'
			self._next_token()
			while self._tokens_left() and self._peek_token().type in (TokenType.NL, TokenType.NEWLINE):
				self._next_token()
			if not self._tokens_left():
				# Having ';' at end of string is not actually error
				return self._create_action(action_class, *parameters)
			action1 = self._create_action(action_class, *parameters)
			action2 = self._parse_action()
			return Macro(action1, action2)

		return self._create_action(action_class, *parameters)


	def parse(self):
		"""Return parsed action.

		Throws ParseError if action cannot be parsed.
		"""
		if self.tokens is None:
			raise ParseError("Syntax error")
		a = self._parse_action()
		if self._tokens_left():
			raise ParseError("Unexpected '%s'" % (self._next_token().value, ))
		return a


class TalkingActionParser(ActionParser):
	"""ActionParser that returns None when parsing fails instead of trowing exception and outputs message to stderr."""

	def restart(self, string: str):
		self.string = string
		return ActionParser.restart(self, string)


	def parse(self):
		"""Return parsed action or None if action cannot be parsed."""
		try:
			return ActionParser.parse(self)
		except ParseError as e:
			print(f"Warning: Failed to parse '{self.string}':", e, file=sys.stderr)
