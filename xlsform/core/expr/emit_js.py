"""Compile Live formulas into Frappe ``eval:`` JavaScript (REQUIREMENTS.md section 6.2).

The output must run identically in two engines: real JavaScript (Frappe Desk and Web
Forms, via ``frappe.utils.eval`` with ``doc`` and ``parent`` in scope) and the mForm SDK's
restricted interpreter (``frappe-mobile-sdk/lib/src/utils/js_expression.dart``). So only
this grammar is emitted: literals, ``doc.x`` / ``parent.x``, ``! && || ?:``,
``=== !== < <= > >= + - * / %``, ``.length``, ``.includes``, ``.startsWith``,
``.endsWith``, ``.some``, ``.map``, ``.join``, ``.split``, ``.filter``, single-expression
arrow functions, and the Frappe globals ``cint``, ``flt``, ``cstr``.

Security: user text reaches the output only as string literals, escaped here; fieldnames
come from the compiler's sanitiser (``[a-z0-9_]``). Nothing else from the workbook is
copied into code.

ODK semantics are kept by tracking a static *kind* for every sub-expression:

- ``bool`` — a JavaScript boolean;
- ``num`` — a number, valid only while its ``guards`` hold (a blank answer is NaN in ODK
  but ``flt("")`` is 0 in Frappe, so blank operands are guarded explicitly);
- ``numref`` — an integer/decimal answer: a number, or blank;
- ``str`` — anything else (text, choice names, dates as ISO strings).
"""

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from xlsform.core.expr.evaluate import format_number

NUMERIC_TYPES = {"integer", "decimal", "range"}
DATE_TYPES = {"date", "datetime", "time", "start", "end", "today"}
EVAL_MARKER = "eval:"
MAX_JS_LENGTH = 4000
MAX_EMIT_DEPTH = 200
MAX_INLINE_DEPTH = 20
FORBIDDEN_LITERAL_CHARS = {"\n", "\r", " ", " ", "\t", "\x00"}


class NotLive(Exception):
	"""The formula uses something that can't be evaluated while the form is filled."""

	def __init__(self, what: str, calc: str | None = None):
		super().__init__(what)
		self.what = what
		self.calc = calc  # set when the culprit is a server-only calculate question


class TooComplex(NotLive):
	"""Written out with every calculation it uses, the formula is too long or too deep to ship."""

	def __init__(self):
		super().__init__("this formula")


@dataclass
class Budget:
	"""Shared by a formula and the calculations inlined into it, so expansion stops early."""

	depth: int = 0


@dataclass
class Scope:
	"""Facts about the form that the emitter needs, supplied by the compiler."""

	fieldname: Callable[[str], str]  # path -> Frappe fieldname
	type_of: Callable[[str], str]  # path -> XLSForm base type ("repeat" / "group" for containers)
	repeat_of: Callable[[str], str | None]  # path -> enclosing repeat path
	calc_ast: Callable[[str], dict | None] = lambda path: None  # calculate path -> resolved AST
	scope_repeat: str | None = None  # repeat that owns the formula (rows evaluate with doc = row)
	inlining: tuple[str, ...] = field(default_factory=tuple)
	budget: Budget = field(default_factory=Budget)


@dataclass
class Js:
	code: str
	kind: str  # bool / num / numref / str
	guards: tuple[str, ...] = ()
	literal: bool = False  # a string literal: already a string, never blank-guarded
	text: str | None = None  # the literal's own text, when literal
	date: bool = False  # a date/time answer: ODK compares these as dates, Frappe's flt can't


def emit(ast: dict, scope: Scope) -> str:
	"""Return a boolean JavaScript expression (for depends_on-style properties)."""
	return _checked(_as_bool(_emit(ast, scope)))


def _checked(code: str) -> str:
	if len(code) > MAX_JS_LENGTH:
		raise TooComplex()
	return code


def emit_value(ast: dict, scope: Scope) -> Js:
	return _emit(ast, scope)


def js_string(text: str) -> str:
	"""A JavaScript string literal for ``text``.

	Text containing ``eval:`` is split into ``("ev" + "al:...")`` so the marker never appears
	in emitted code: Frappe's link.js evaluates ``value.split("eval:")[1]`` of a link filter.
	"""
	if any(ch in text for ch in FORBIDDEN_LITERAL_CHARS) or any(ord(ch) < 32 for ch in text):
		raise NotLive("text with line breaks or control characters")
	if EVAL_MARKER in text:
		head, *rest = text.split(EVAL_MARKER)
		pieces = [_quote(head)] if head else []
		for part in rest:
			pieces += ['"ev"', _quote("al:" + part)]
		return "(" + " + ".join(pieces) + ")"
	return _quote(text)


def _quote(text: str) -> str:
	return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def filter_value(ast: dict, scope: "Scope") -> str:
	"""A link_filters value: always ``eval:`` code, so no designer text is ever read as code."""
	if "lit" in ast and isinstance(ast["lit"], float):
		return format_number(ast["lit"])
	return EVAL_MARKER + _checked(_as_str(_emit(ast, scope)))


def _num_literal(value: float) -> str:
	text = format_number(value)
	if text in ("NaN", "Infinity", "-Infinity"):
		raise NotLive("this number")
	return f"({text})" if value < 0 else text


# ── conversions ────────────────────────────────────────────────────────────────


def _as_bool(e: Js) -> str:
	if e.kind == "bool":
		return e.code
	if e.kind == "num":
		comparison = f"({e.code} !== 0)"
		return _guarded(e.guards, comparison)
	return f"!!({e.code})"


def _as_str(e: Js) -> str:
	if e.literal:
		return e.code
	if e.kind == "bool":
		return f'({e.code} ? "true" : "false")'
	return f"cstr({e.code})"


def _as_num(e: Js) -> tuple[str, tuple[str, ...]]:
	"""Numeric code plus the guards under which it is a real number (not ODK's NaN)."""
	if e.kind == "num":
		return e.code, e.guards
	if e.kind == "bool":
		return f"({e.code} ? 1 : 0)", ()
	if e.literal:
		text = e.text or ""
		try:
			value = float(text) if text.strip() else math.nan
		except ValueError:
			value = math.nan
		if math.isnan(value):
			return "0", ("false",)
		return _num_literal(value), ()
	if e.kind == "numref":
		return f"flt({e.code})", (f'cstr({e.code}) !== ""',)
	# Text: flt("red") is 0 in Frappe but NaN in ODK. Loose == between the number and the
	# original text is true only when the whole text is a number ("5", " 5", "5.0").
	return f"flt({e.code})", (f'cstr({e.code}) !== ""', f"flt({e.code}) == cstr({e.code})")


def _guarded(guards: tuple[str, ...], expr: str) -> str:
	unique = tuple(dict.fromkeys(guards))
	if not unique:
		return expr
	return "(" + " && ".join((*unique, expr)) + ")"


# ── emission ───────────────────────────────────────────────────────────────────


def _emit(node: dict, scope: Scope) -> Js:
	budget = scope.budget
	budget.depth += 1
	try:
		if budget.depth > MAX_EMIT_DEPTH:
			raise TooComplex()
		js = _emit_node(node, scope)
	finally:
		budget.depth -= 1
	if len(js.code) + sum(len(g) for g in js.guards) > MAX_JS_LENGTH:
		raise TooComplex()
	return js


def _emit_node(node: dict, scope: Scope) -> Js:
	if "lit" in node:
		value = node["lit"]
		if isinstance(value, float):
			return Js(_num_literal(value), "num")
		return Js(js_string(value), "str", literal=True, text=value)
	if "ref" in node:
		return _ref(node["ref"], scope)
	if node.get("self"):
		raise NotLive('"." (this answer)')
	if node.get("parent"):
		raise NotLive('".."')
	if "col" in node:
		raise NotLive(f'"{node["col"]}"')
	if "op" in node:
		return _op(node["op"], node["args"], scope)
	if "fn" in node:
		return _fn(node["fn"], node["args"], scope)
	raise NotLive("this formula")


def _owner(path: str, scope: Scope) -> str:
	"""``doc`` or ``parent``: where the field lives relative to the formula's row."""
	target_repeat = scope.repeat_of(path)
	if target_repeat is None:
		return "parent" if scope.scope_repeat else "doc"
	if target_repeat == scope.scope_repeat:
		return "doc"
	raise NotLive(f"${{{path.rsplit('/', 1)[-1]}}} (inside another repeat)")


def _ref(path: str, scope: Scope) -> Js:
	qtype = scope.type_of(path)
	name = path.rsplit("/", 1)[-1]
	if qtype in ("repeat", "group"):
		raise NotLive(f"${{{name}}} on its own")
	if qtype == "calculate":
		inner = scope.calc_ast(path)
		if inner is None or path in scope.inlining:
			raise NotLive(f"${{{name}}}", calc=name)
		if len(scope.inlining) >= MAX_INLINE_DEPTH:
			raise TooComplex()
		sub = Scope(**{**scope.__dict__, "inlining": (*scope.inlining, path)})
		try:
			return _emit(inner, sub)
		except TooComplex:
			raise
		except NotLive as exc:
			raise NotLive(exc.what, calc=name) from exc
	owner = _owner(path, scope)
	field = f"{owner}.{scope.fieldname(path)}"
	if qtype in NUMERIC_TYPES:
		return Js(field, "numref")
	if qtype in ("select_multiple", "select_multiple_from_file"):
		return Js(f'({field} || []).map(r => r.choice).join(" ")', "str")
	if qtype == "acknowledge":
		return Js(f'({field} ? "OK" : "")', "str")
	return Js(field, "str", date=qtype in DATE_TYPES)


def _multi_rows(node: dict, scope: Scope) -> str | None:
	"""``(doc.f || [])`` when ``node`` is a direct reference to a select_multiple question."""
	if "ref" not in node:
		return None
	if scope.type_of(node["ref"]) not in ("select_multiple", "select_multiple_from_file"):
		return None
	return f"({_owner(node['ref'], scope)}.{scope.fieldname(node['ref'])} || [])"


def _op(op: str, args: list, scope: Scope) -> Js:
	if op in ("and", "or"):
		joiner = " && " if op == "and" else " || "
		return Js("(" + joiner.join(_as_bool(_emit(a, scope)) for a in args) + ")", "bool")
	if op == "neg":
		code, guards = _as_num(_emit(args[0], scope))
		return Js(f"(-{code})", "num", guards)
	a = _emit(args[0], scope)
	b = _emit(args[1], scope)
	if (a.date or b.date or _date_literal(a) or _date_literal(b)) and op not in ("=", "!="):
		raise NotLive("date comparisons and date arithmetic")
	if op in ("+", "-", "*", "div", "mod"):
		ca, ga = _as_num(a)
		cb, gb = _as_num(b)
		symbol = {"div": "/", "mod": "%"}.get(op, op)
		return Js(f"({ca} {symbol} {cb})", "num", ga + gb)
	if op in ("<", "<=", ">", ">="):
		ca, ga = _as_num(a)
		cb, gb = _as_num(b)
		return Js(_guarded(ga + gb, f"{ca} {op} {cb}"), "bool")
	if op in ("=", "!="):
		eq = _equals(a, b)
		return Js(eq if op == "=" else f"!{eq}", "bool")
	raise NotLive(f'the "{op}" operator')


def _equals(a: Js, b: Js) -> str:
	kinds = {a.kind, b.kind}
	if "bool" in kinds:
		return f"({_as_bool(a)} === {_as_bool(b)})"
	if "num" in kinds:
		ca, ga = _as_num(a)
		cb, gb = _as_num(b)
		return _guarded(ga + gb, f"{ca} === {cb}")
	if kinds == {"numref"}:
		sa, sb = _as_str(a), _as_str(b)
		return f'(({sa} === "" || {sb} === "") ? ({sa} === {sb}) : (flt({a.code}) === flt({b.code})))'
	if kinds == {"numref", "str"}:
		n, s = (a, b) if a.kind == "numref" else (b, a)
		sn, ss = _as_str(n), _as_str(s)
		cs, gs = _as_num(s)
		return f'({sn} === "" ? ({ss} === "") : {_guarded(gs, f"flt({n.code}) === {cs}")})'
	return f"({_as_str(a)} === {_as_str(b)})"


def _date_literal(e: Js) -> bool:
	return e.literal and bool(re.match(r"^\d{4}-\d{2}-\d{2}", e.text or ""))


def _check_arity(fn: str, args: list, n: int) -> None:
	if len(args) != n:
		raise NotLive(f"{fn}()")


def _fn(fn: str, args: list, scope: Scope) -> Js:
	if fn == "true":
		return Js("true", "bool")
	if fn == "false":
		return Js("false", "bool")
	if fn in ("not", "boolean"):
		inner = _as_bool(_emit(args[0], scope))
		return Js(f"(!{inner})" if fn == "not" else inner, "bool")
	if fn == "if":
		cond = _as_bool(_emit(args[0], scope))
		a, b = _emit(args[1], scope), _emit(args[2], scope)
		if a.kind == b.kind == "bool":
			return Js(f"({cond} ? {a.code} : {b.code})", "bool")
		if a.kind == b.kind == "num":
			guards = ()
			if a.guards or b.guards:
				guards = (f"({cond} ? {_guarded(a.guards, 'true')} : {_guarded(b.guards, 'true')})",)
			return Js(f"({cond} ? {a.code} : {b.code})", "num", guards)
		numeric = {"num", "numref"}
		if (a.kind in numeric and b.kind in numeric | {"str"}) or (
			b.kind in numeric and a.kind in numeric | {"str"}
		):
			return Js(f"({cond} ? {_raw(a)} : {_raw(b)})", "numref" if {a.kind, b.kind} & numeric else "str")
		return Js(f"({cond} ? {_as_str(a)} : {_as_str(b)})", "str")
	if fn == "coalesce":
		a, b = _emit(args[0], scope), _emit(args[1], scope)
		kind = "numref" if {a.kind, b.kind} <= {"num", "numref"} else "str"
		return Js(f'({_as_str(a)} !== "" ? {_raw(a)} : {_raw(b)})', kind)
	if fn == "selected":
		value = _as_str(_emit(args[1], scope))
		rows = _multi_rows(args[0], scope)
		if rows:
			return Js(f"{rows}.some(r => r.choice === {value})", "bool")
		return Js(f'{_as_str(_emit(args[0], scope))}.split(" ").includes({value})', "bool")
	if fn == "count-selected":
		rows = _multi_rows(args[0], scope)
		if rows:
			return Js(f"{rows}.length", "num")
		return Js(f'{_as_str(_emit(args[0], scope))}.split(" ").filter(s => s !== "").length', "num")
	if fn == "concat":
		parts = [_as_str(_emit(a, scope)) for a in args]
		return Js("(" + " + ".join(parts) + ")", "str")
	if fn == "string-length":
		if not args:
			raise NotLive("string-length() without a value")
		return Js(f"{_as_str(_emit(args[0], scope))}.length", "num")
	if fn in ("contains", "starts-with", "ends-with"):
		method = {"contains": "includes", "starts-with": "startsWith", "ends-with": "endsWith"}[fn]
		a, b = _as_str(_emit(args[0], scope)), _as_str(_emit(args[1], scope))
		return Js(f"{a}.{method}({b})", "bool")
	if fn == "string":
		if not args:
			raise NotLive("string() without a value")
		return Js(_as_str(_emit(args[0], scope)), "str")
	if fn == "number":
		if not args:
			raise NotLive("number() without a value")
		code, guards = _as_num(_emit(args[0], scope))
		return Js(code, "num", guards)
	if fn == "int":
		code, guards = _as_num(_emit(args[0], scope))
		return Js(f"cint({code})", "num", guards)
	if fn == "count":
		return Js(f"{_count_rows(args[0], scope)}.length", "num")
	raise NotLive(f"{fn}()")


def _raw(e: Js) -> str:
	if e.kind == "bool":
		return _as_str(e)
	return e.code


def _count_rows(node: dict, scope: Scope) -> str:
	"""``(doc.member || [])`` for count(${member}) or count(${a_question_in_member})."""
	if "ref" not in node:
		raise NotLive("count() of something that isn't a repeat")
	path = node["ref"]
	repeat = path if scope.type_of(path) == "repeat" else scope.repeat_of(path)
	if repeat is None:
		raise NotLive("count() of a question outside a repeat")
	if repeat == scope.scope_repeat and scope.type_of(path) != "repeat":
		return "[1]"  # ODK resolves ${q} to the current row's node: always one node
	owner = "parent" if scope.scope_repeat else "doc"
	return f"({owner}.{scope.fieldname(repeat)} || [])"
