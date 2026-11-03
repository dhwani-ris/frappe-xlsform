"""Tokeniser and Pratt parser for XLSForm formulas (REQUIREMENTS.md section 6).

Formulas are parsed once, here, into a JSON-serialisable AST:

- ``{"lit": "yes"}`` / ``{"lit": 5.0}`` — literals (numbers are floats)
- ``{"ref": "/grp/age", "name": "age"}`` — ``${age}``; ``ref`` is filled in by resolution
- ``{"self": True}`` — ``.`` (the current answer, in constraints)
- ``{"parent": True}`` — ``..`` (only inside ``position(..)``)
- ``{"col": "district"}`` — a bare choices-sheet column inside ``choice_filter``
- ``{"op": "and", "args": [...]}`` — operators: or and = != < <= > >= + - * div mod neg
- ``{"fn": "selected", "args": [...]}`` — function calls

User text is never executed: the AST is evaluated by :mod:`.evaluate` or translated by
:mod:`.emit_js`, both of which only understand the node shapes above.
"""

import re
from dataclasses import dataclass

AST_VERSION = 1

CURLY_QUOTES = "‘’“”‚‛„‟"
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*(?::[A-Za-z_][A-Za-z0-9_\-]*)?")
REF_RE = re.compile(r"\$\{([^}]*)\}")
COLUMN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*::[A-Za-z_][A-Za-z0-9_\- ()]*?(?=\s*(?:[=!<>)]|$))")
NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")
MAX_DEPTH = 100
DEPTH_REASON = f"it has more than {MAX_DEPTH} levels of brackets, functions or operators inside each other"


class ExprSyntaxError(Exception):
	def __init__(self, reason: str, position: int | None = None):
		super().__init__(reason)
		self.reason = reason
		self.position = position


class CurlyQuoteError(ExprSyntaxError):
	pass


@dataclass
class Token:
	kind: str
	value: str
	pos: int


OPERATORS = ("!=", "<=", ">=", "=", "<", ">", "+", "-", "*")


def tokenize(text: str) -> list[Token]:
	"""Split a formula into tokens. A curly quote outside a straight-quoted string was meant as a
	quote mark, which formulas do not accept, so it raises ``CurlyQuoteError``."""
	tokens: list[Token] = []
	i = 0
	n = len(text)
	while i < n:
		ch = text[i]
		if ch in CURLY_QUOTES:
			raise CurlyQuoteError("curly quotes", i + 1)
		if ch.isspace():
			i += 1
			continue
		if ch in "'\"":
			end = text.find(ch, i + 1)
			if end == -1:
				raise ExprSyntaxError(f"a quote opened at character {i + 1} is never closed", i + 1)
			tokens.append(Token("str", text[i + 1 : end], i))
			i = end + 1
			continue
		if ch == "$":
			m = REF_RE.match(text, i)
			if not m:
				raise ExprSyntaxError(f"${{ at character {i + 1} is never closed with }}", i + 1)
			name = m.group(1).strip()
			if not name:
				raise ExprSyntaxError(f"${{}} at character {i + 1} has no question name", i + 1)
			tokens.append(Token("ref", name, i))
			i = m.end()
			continue
		m = NUMBER_RE.match(text, i)
		if m and (ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit())):
			tokens.append(Token("num", m.group(0), i))
			i = m.end()
			continue
		if text.startswith("..", i):
			tokens.append(Token("parent", "..", i))
			i += 2
			continue
		if ch == ".":
			tokens.append(Token("self", ".", i))
			i += 1
			continue
		if ch == "(":
			tokens.append(Token("lparen", ch, i))
			i += 1
			continue
		if ch == ")":
			tokens.append(Token("rparen", ch, i))
			i += 1
			continue
		if ch == ",":
			tokens.append(Token("comma", ch, i))
			i += 1
			continue
		for op in OPERATORS:
			if text.startswith(op, i):
				tokens.append(Token("op", op, i))
				i += len(op)
				break
		else:
			m = COLUMN_RE.match(text, i) or NAME_RE.match(text, i)
			if m:
				tokens.append(Token("name", m.group(0), i))
				i = m.end()
				continue
			if ch == "/":
				raise ExprSyntaxError("paths like /data/question aren't supported; use ${question}", i + 1)
			if ch == "|":
				raise ExprSyntaxError("the | operator isn't supported", i + 1)
			raise ExprSyntaxError(f'the character "{ch}" at position {i + 1} isn\'t allowed', i + 1)
	tokens.append(Token("end", "", n))
	return tokens


BINARY = {
	"or": 10,
	"and": 20,
	"=": 30,
	"!=": 30,
	"<": 40,
	"<=": 40,
	">": 40,
	">=": 40,
	"+": 50,
	"-": 50,
	"*": 60,
	"div": 60,
	"mod": 60,
}
WORD_OPERATORS = {"and", "or", "div", "mod"}


class Parser:
	def __init__(self, text: str, allow_columns: bool = False):
		self.text = text
		self.tokens = tokenize(text)
		self.i = 0
		self.allow_columns = allow_columns
		self.depth = 0

	def peek(self) -> Token:
		return self.tokens[self.i]

	def next(self) -> Token:
		tok = self.tokens[self.i]
		self.i += 1
		return tok

	def parse(self) -> dict:
		if self.peek().kind == "end":
			raise ExprSyntaxError("the formula is empty", 1)
		node = self.expression(0)
		if depth(node) > MAX_DEPTH:
			raise ExprSyntaxError(DEPTH_REASON)
		tok = self.peek()
		if tok.kind != "end":
			if tok.kind == "rparen":
				raise ExprSyntaxError(
					f"a bracket closed at character {tok.pos + 1} was never opened", tok.pos + 1
				)
			raise ExprSyntaxError(f'unexpected "{tok.value}" at character {tok.pos + 1}', tok.pos + 1)
		return node

	def _binary_op(self, tok: Token) -> str | None:
		if tok.kind == "op" and tok.value in BINARY:
			return tok.value
		if tok.kind == "name" and tok.value in WORD_OPERATORS:
			return tok.value
		return None

	def _enter(self) -> None:
		self.depth += 1
		if self.depth > MAX_DEPTH:
			raise ExprSyntaxError(DEPTH_REASON)

	def expression(self, min_bp: int) -> dict:
		self._enter()
		try:
			return self._expression(min_bp)
		finally:
			self.depth -= 1

	def _expression(self, min_bp: int) -> dict:
		left = self.unary()
		while True:
			op = self._binary_op(self.peek())
			if op is None or BINARY[op] <= min_bp:
				break
			self.next()
			right = self.expression(BINARY[op])
			left = {"op": op, "args": [left, right]}
		return left

	def unary(self) -> dict:
		tok = self.peek()
		if tok.kind == "op" and tok.value == "-":
			self.next()
			self._enter()
			try:
				operand = self.unary()
			finally:
				self.depth -= 1
			if "lit" in operand and isinstance(operand["lit"], float):
				return {"lit": -operand["lit"]}
			return {"op": "neg", "args": [operand]}
		return self.primary()

	def primary(self) -> dict:
		tok = self.next()
		if tok.kind == "num":
			return {"lit": float(tok.value)}
		if tok.kind == "str":
			return {"lit": tok.value}
		if tok.kind == "ref":
			return {"ref": None, "name": tok.value, "pos": tok.pos}
		if tok.kind == "self":
			return {"self": True}
		if tok.kind == "parent":
			return {"parent": True}
		if tok.kind == "lparen":
			inner = self.expression(0)
			close = self.next()
			if close.kind != "rparen":
				raise ExprSyntaxError(
					f"a bracket opened at character {tok.pos + 1} is never closed", tok.pos + 1
				)
			return inner
		if tok.kind == "name":
			if self.peek().kind == "lparen":
				return self.call(tok)
			if tok.value in WORD_OPERATORS:
				raise ExprSyntaxError(
					f'"{tok.value}" at character {tok.pos + 1} is missing a value before it', tok.pos + 1
				)
			if self.allow_columns:
				return {"col": tok.value}
			raise ExprSyntaxError(
				f'"{tok.value}" at character {tok.pos + 1} isn\'t a question reference; write ${{{tok.value}}}, or put text in quotes',
				tok.pos + 1,
			)
		if tok.kind == "end":
			raise ExprSyntaxError("the formula ends too early", tok.pos + 1)
		if tok.kind == "rparen":
			raise ExprSyntaxError(
				f"a bracket closed at character {tok.pos + 1} was never opened", tok.pos + 1
			)
		raise ExprSyntaxError(f'unexpected "{tok.value}" at character {tok.pos + 1}', tok.pos + 1)

	def call(self, name_tok: Token) -> dict:
		open_tok = self.next()
		args = []
		if self.peek().kind == "rparen":
			self.next()
			return {"fn": name_tok.value, "args": args, "pos": name_tok.pos}
		while True:
			args.append(self.expression(0))
			tok = self.next()
			if tok.kind == "comma":
				continue
			if tok.kind == "rparen":
				break
			if tok.kind == "end":
				raise ExprSyntaxError(
					f"a bracket opened at character {open_tok.pos + 1} is never closed", open_tok.pos + 1
				)
			raise ExprSyntaxError(
				f'expected , or ) at character {tok.pos + 1} but found "{tok.value}"', tok.pos + 1
			)
		return {"fn": name_tok.value, "args": args, "pos": name_tok.pos}


def parse(text: str, allow_columns: bool = False) -> dict:
	return Parser(text, allow_columns=allow_columns).parse()


def depth(node: dict) -> int:
	"""Nesting depth of an AST, computed without recursion."""
	deepest = 0
	stack = [(node, 1)]
	while stack:
		current, level = stack.pop()
		deepest = max(deepest, level)
		stack.extend((arg, level + 1) for arg in current.get("args", ()))
	return deepest


def walk(node: dict):
	yield node
	for arg in node.get("args", ()):
		yield from walk(arg)


def refs(node: dict) -> list[dict]:
	return [n for n in walk(node) if "ref" in n]


def strip_positions(node: dict) -> dict:
	"""Copy of the AST without parser-only keys, as stored in compiled_meta."""
	out = {k: v for k, v in node.items() if k not in ("pos", "args")}
	if "args" in node:
		out["args"] = [strip_positions(a) for a in node["args"]]
	return out
