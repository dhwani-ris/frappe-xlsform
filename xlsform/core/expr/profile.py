"""The JavaScript profile every emitted ``eval:`` string must fit (REQUIREMENTS.md 6.2, 6.4).

Emitted code runs in two engines: real JavaScript in Frappe Desk and Web Forms, and the
mForm SDK's interpreter (``frappe-mobile-sdk/lib/src/utils/js_expression.dart``). This module
is a small tokenizer and parser for the part of the SDK's documented subset that is also
plain, unambiguous JavaScript, and nothing more:

- literals: numbers written with digits and one optional ``.`` (no exponent, no leading
  zero), double-quoted strings whose only escapes are ``\\\\`` and ``\\"``, ``true``,
  ``false``, ``null``, ``undefined``, and array literals;
- the identifiers ``doc`` and ``parent``, and parameters of an arrow function;
- member access ``a.b`` (not ``a[b]``), and method calls from the SDK's whitelist;
- the global calls ``cint``, ``flt``, ``cstr``, ``in_list`` and ``Boolean``;
- single-expression arrow functions with one parameter, only as the argument of
  ``some``/``every``/``filter``/``map``/``find``;
- unary ``! - +``; binary ``=== !== == != < <= > >= && || + - * / %``; ``?:``; brackets.

Everything else (statements, ``;``, assignment, ``new``, template literals, regex
literals, comments, ``++``/``--``, exponents, other identifiers such as ``window``, a
second ``eval:``) is rejected. The compiler treats a rejected string as an emitter bug: the
formula is reported as not Live and the string is never shipped.
"""

import re

EVAL_MARKER = "eval:"
MAX_NESTING = 120

GLOBAL_CALLS = {"cint", "flt", "cstr", "in_list", "Boolean"}
LIST_METHODS = {"includes", "indexOf", "some", "every", "filter", "map", "join", "find"}
STRING_METHODS = {
	"includes",
	"indexOf",
	"trim",
	"toLowerCase",
	"toUpperCase",
	"startsWith",
	"endsWith",
	"split",
}
ARROW_METHODS = {"some", "every", "filter", "map", "find"}
LITERAL_NAMES = {"true", "false", "null", "undefined"}
ROOTS = {"doc", "parent"}
FORBIDDEN_PROPERTIES = {"constructor", "prototype", "__proto__", "__defineGetter__", "__lookupGetter__"}
RESERVED = {
	*LITERAL_NAMES,
	*ROOTS,
	*GLOBAL_CALLS,
	"this",
	"new",
	"typeof",
	"void",
	"delete",
	"in",
	"instanceof",
	"function",
	"return",
	"var",
	"let",
	"const",
	"eval",
	"arguments",
	"window",
	"globalThis",
	"frappe",
	"yield",
	"await",
	"async",
	"class",
	"super",
	"import",
	"export",
	"with",
	"debugger",
}

PRECEDENCE = {
	"||": 1,
	"&&": 2,
	"===": 3,
	"!==": 3,
	"==": 3,
	"!=": 3,
	"<": 4,
	">": 4,
	"<=": 4,
	">=": 4,
	"+": 5,
	"-": 5,
	"*": 6,
	"/": 6,
	"%": 6,
}
OPERATORS = sorted(
	[*PRECEDENCE, "=>", "!", "?", ":", ".", ",", "(", ")", "[", "]"],
	key=len,
	reverse=True,
)
NUMBER_RE = re.compile(r"(?:0|[1-9]\d*)(?:\.\d+)?|\.\d+")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class OutsideProfile(Exception):
	"""The string isn't in the emitted-JavaScript profile."""


def check(code: str) -> None:
	"""Raise :class:`OutsideProfile` unless ``code`` is one expression in the profile."""
	if EVAL_MARKER in code:
		raise OutsideProfile("a second eval: marker")
	_Parser(_tokenize(code)).parse()


def is_valid(code: str) -> bool:
	try:
		check(code)
	except OutsideProfile:
		return False
	return True


def _tokenize(src: str) -> list[tuple[str, str]]:
	tokens: list[tuple[str, str]] = []
	i, n = 0, len(src)
	while i < n:
		ch = src[i]
		if ch == " ":
			i += 1
			continue
		if ch == '"':
			i, text = _string(src, i)
			tokens.append(("str", text))
			continue
		if ch.isdigit() or (ch == "." and i + 1 < n and src[i + 1].isdigit()):
			m = NUMBER_RE.match(src, i)
			end = m.end() if m else i
			if not m or (end < n and (src[end].isalnum() or src[end] in "._")):
				raise OutsideProfile(f"a number at {i} that isn't plain decimal")
			tokens.append(("num", m.group(0)))
			i = end
			continue
		m = IDENT_RE.match(src, i)
		if m:
			tokens.append(("ident", m.group(0)))
			i = m.end()
			continue
		for op in OPERATORS:
			if src.startswith(op, i):
				if op in "+-" and src.startswith(op * 2, i):
					raise OutsideProfile("++ or --")
				tokens.append(("op", op))
				i += len(op)
				break
		else:
			raise OutsideProfile(f"the character {ch!r} at {i}")
	tokens.append(("end", ""))
	return tokens


def _string(src: str, i: int) -> tuple[int, str]:
	out = []
	i += 1
	while i < len(src):
		ch = src[i]
		if ch == "\\":
			nxt = src[i + 1 : i + 2]
			if nxt not in ('"', "\\"):
				raise OutsideProfile('an escape other than \\\\ or \\"')
			out.append(nxt)
			i += 2
			continue
		if ch == '"':
			return i + 1, "".join(out)
		if ord(ch) < 32 or ch in "  \x7f":
			raise OutsideProfile("a control character in a string")
		out.append(ch)
		i += 1
	raise OutsideProfile("an unterminated string")


class _Parser:
	def __init__(self, tokens: list[tuple[str, str]]):
		self.tokens = tokens
		self.i = 0
		self.depth = 0
		self.bound: list[str] = []

	def peek(self, offset: int = 0) -> tuple[str, str]:
		return self.tokens[min(self.i + offset, len(self.tokens) - 1)]

	def is_op(self, value: str, offset: int = 0) -> bool:
		return self.peek(offset) == ("op", value)

	def expect(self, value: str) -> None:
		if not self.is_op(value):
			raise OutsideProfile(f"expected {value}")
		self.i += 1

	def parse(self) -> None:
		self.expression()
		if self.peek()[0] != "end":
			raise OutsideProfile(f"unexpected {self.peek()[1]!r}")

	def expression(self) -> None:
		self.depth += 1
		if self.depth > MAX_NESTING:
			raise OutsideProfile("nested too deeply")
		try:
			self.binary(0)
			if self.is_op("?"):
				self.i += 1
				self.expression()
				self.expect(":")
				self.expression()
		finally:
			self.depth -= 1

	def binary(self, min_prec: int) -> None:
		self.unary()
		while True:
			kind, value = self.peek()
			prec = PRECEDENCE.get(value) if kind == "op" else None
			if prec is None or prec < min_prec:
				return
			self.i += 1
			self.binary(prec + 1)

	def unary(self) -> None:
		count = 0
		while self.peek()[0] == "op" and self.peek()[1] in ("!", "-", "+"):
			self.i += 1
			count += 1
			if count > MAX_NESTING:
				raise OutsideProfile("nested too deeply")
		self.postfix()

	def postfix(self) -> None:
		self.primary()
		while True:
			if self.is_op("."):
				self.i += 1
				kind, name = self.peek()
				if kind != "ident" or name in FORBIDDEN_PROPERTIES:
					raise OutsideProfile("a property that isn't a plain name")
				self.i += 1
				if self.is_op("("):
					self.method(name)
				continue
			if self.is_op("[") or self.is_op("("):
				raise OutsideProfile("computed access or a call of an expression")
			return

	def method(self, name: str) -> None:
		if name not in LIST_METHODS | STRING_METHODS:
			raise OutsideProfile(f"the method {name}")
		self.expect("(")
		if name in ARROW_METHODS:
			self.arrow()
			self.expect(")")
			return
		self.arguments()

	def arguments(self) -> None:
		if self.is_op(")"):
			self.i += 1
			return
		while True:
			self.expression()
			if self.is_op(","):
				self.i += 1
				continue
			self.expect(")")
			return

	def arrow(self) -> None:
		kind, param = self.peek()
		if kind != "ident" or param in RESERVED or not self.is_op("=>", 1):
			raise OutsideProfile("an arrow function other than x => expression")
		self.i += 2
		self.bound.append(param)
		try:
			self.expression()
		finally:
			self.bound.pop()

	def primary(self) -> None:
		kind, value = self.peek()
		self.i += 1
		if kind in ("num", "str"):
			return
		if kind == "ident":
			if value in LITERAL_NAMES or value in ROOTS or value in self.bound:
				if self.is_op("=>"):
					raise OutsideProfile("an arrow function outside a method call")
				return
			if value in GLOBAL_CALLS and self.is_op("("):
				self.i += 1
				self.arguments()
				return
			raise OutsideProfile(f"the identifier {value}")
		if (kind, value) == ("op", "("):
			self.expression()
			self.expect(")")
			return
		if (kind, value) == ("op", "["):
			if self.is_op("]"):
				self.i += 1
				return
			while True:
				self.expression()
				if self.is_op(","):
					self.i += 1
					continue
				self.expect("]")
				return
		raise OutsideProfile(f"unexpected {value!r}")
