"""Server-side evaluator for parsed XLSForm formulas (REQUIREMENTS.md section 6.3).

Follows XPath 1.0 / JavaRosa semantics so a form behaves as it does in ODK:

- an unanswered question is ``""``; answered integer/decimal questions are numbers;
- ``=``/``!=`` compare as booleans if either side is boolean, else as numbers if either
  side is a number, else as strings; ``< <= > >=`` always compare numbers;
- ``""`` and non-numeric text become NaN; every comparison with NaN is false except ``!=``;
- a node-set (a question inside a repeat, seen from outside it) compares existentially.
"""

import datetime
import math
import re
import uuid as uuid_lib
from collections.abc import Callable
from dataclasses import dataclass, field

EPOCH = datetime.date(1970, 1, 1)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?")


class NodeSet(list):
	"""Values of one question across all rows of a repeat (or the rows themselves)."""


@dataclass
class FnSpec:
	min_args: int
	max_args: int | None  # None = unlimited
	live: bool
	example: str


FUNCTIONS: dict[str, FnSpec] = {
	"if": FnSpec(3, 3, True, "if(${age} > 17, 'adult', 'child')"),
	"not": FnSpec(1, 1, True, "not(selected(${services}, 'health'))"),
	"true": FnSpec(0, 0, True, "true()"),
	"false": FnSpec(0, 0, True, "false()"),
	"boolean": FnSpec(1, 1, True, "boolean(${name})"),
	"coalesce": FnSpec(2, 2, True, "coalesce(${phone}, ${alt_phone})"),
	"selected": FnSpec(2, 2, True, "selected(${services}, 'health')"),
	"count-selected": FnSpec(1, 1, True, "count-selected(${services})"),
	"selected-at": FnSpec(2, 2, False, "selected-at(${services}, 0)"),
	"jr:choice-name": FnSpec(2, 2, False, "jr:choice-name(${district}, '${district}')"),
	"concat": FnSpec(1, None, True, "concat(${first_name}, ' ', ${last_name})"),
	"substr": FnSpec(2, 3, False, "substr(${phone}, 0, 3)"),
	"string-length": FnSpec(0, 1, True, "string-length(${name})"),
	"contains": FnSpec(2, 2, True, "contains(${name}, 'kumar')"),
	"starts-with": FnSpec(2, 2, True, "starts-with(${phone}, '9')"),
	"ends-with": FnSpec(2, 2, True, "ends-with(${email}, '.org')"),
	"normalize-space": FnSpec(0, 1, False, "normalize-space(${name})"),
	"regex": FnSpec(2, 2, False, "regex(., '^[0-9]{10}$')"),
	"string": FnSpec(0, 1, True, "string(${age})"),
	"int": FnSpec(1, 1, True, "int(${income} div 12)"),
	"number": FnSpec(0, 1, True, "number(${amount})"),
	"round": FnSpec(1, 2, False, "round(${score}, 2)"),
	"abs": FnSpec(1, 1, False, "abs(${difference})"),
	"pow": FnSpec(2, 2, False, "pow(${side}, 2)"),
	"floor": FnSpec(1, 1, False, "floor(${amount})"),
	"ceiling": FnSpec(1, 1, False, "ceiling(${amount})"),
	"min": FnSpec(1, None, False, "min(${a}, ${b})"),
	"max": FnSpec(1, None, False, "max(${a}, ${b})"),
	"today": FnSpec(0, 0, False, "today()"),
	"now": FnSpec(0, 0, False, "now()"),
	"date": FnSpec(1, 1, False, "date('2026-01-01')"),
	"decimal-date-time": FnSpec(1, 1, False, "decimal-date-time(${visit_time})"),
	"format-date": FnSpec(2, 2, False, "format-date(${dob}, '%d/%m/%Y')"),
	"format-date-time": FnSpec(2, 2, False, "format-date-time(${visit}, '%d/%m/%Y %H:%M')"),
	"count": FnSpec(1, 1, True, "count(${member})"),
	"sum": FnSpec(1, 1, False, "sum(${member_income})"),
	"position": FnSpec(1, 1, False, "position(..)"),
	"once": FnSpec(1, 1, False, "once(uuid())"),
	"uuid": FnSpec(0, 1, False, "uuid()"),
}

# Named so the error can say "isn't supported yet" rather than "unknown".
REJECTED_FUNCTIONS = {
	"pulldata",
	"indexed-repeat",
	"instance",
	"search",
	"last-saved",
	"area",
	"distance",
	"digest",
	"randomize",
	"jr:itext",
	"boolean-from-string",
	"checklist",
	"weighted-checklist",
	"version",
	"property",
	"base64-decode",
	"exp",
	"exp10",
	"log",
	"log10",
	"sqrt",
	"sin",
	"cos",
	"tan",
	"asin",
	"acos",
	"atan",
	"atan2",
	"pi",
	"random",
	"translate",
	"join",
	"sort",
	"geofence",
	"substring-before",
	"substring-after",
	"lower-case",
	"upper-case",
}

NUMERIC_TYPES = {"integer", "decimal", "range"}


class EvalError(Exception):
	pass


@dataclass
class Context:
	"""Answers visible to a formula.

	``data`` holds top-level answers by path and repeat rows by repeat path:
	``{"/age": 30.0, "/member": [{"/member/age": 5.0}, ...]}``. ``repeat_of`` maps every
	question path inside a repeat to its repeat path. ``row`` is the current row index
	when the formula belongs to a question inside ``scope_repeat``.
	"""

	data: dict
	repeat_of: dict[str, str] = field(default_factory=dict)
	repeats: set[str] = field(default_factory=set)
	scope_repeat: str | None = None
	row: int | None = None
	self_path: str | None = None
	columns: dict[str, str] | None = None  # choice row for choice_filter
	choice_labels: dict[str, dict[str, str]] = field(default_factory=dict)  # path -> {name: label}
	today: Callable[[], datetime.date] = datetime.date.today
	now: Callable[[], datetime.datetime] = datetime.datetime.now

	def rows(self, repeat: str) -> list[dict]:
		return self.data.get(repeat) or []

	def lookup(self, path: str):
		if path in self.repeats:
			# the repeat itself: one node per row
			return NodeSet(self.rows(path))
		repeat = self.repeat_of.get(path)
		if repeat is None:
			return _answer(self.data.get(path))
		if repeat == self.scope_repeat and self.row is not None:
			rows = self.rows(repeat)
			return _answer(rows[self.row].get(path)) if self.row < len(rows) else ""
		return NodeSet(_answer(r.get(path)) for r in self.rows(repeat))


def _answer(value):
	if value is None:
		return ""
	if isinstance(value, bool):
		return "1" if value else "0"
	if isinstance(value, int):
		return float(value)
	if isinstance(value, datetime.datetime):
		return value.isoformat()
	if isinstance(value, datetime.date):
		return value.isoformat()
	return value


# ── conversions ────────────────────────────────────────────────────────────────


def to_number(v) -> float:
	if isinstance(v, NodeSet):
		return to_number(v[0]) if v else math.nan
	if isinstance(v, bool):
		return 1.0 if v else 0.0
	if isinstance(v, int | float):
		return float(v)
	if isinstance(v, datetime.datetime):
		return _days(v)
	if isinstance(v, datetime.date):
		return float((v - EPOCH).days)
	if isinstance(v, str):
		s = v.strip()
		if not s:
			return math.nan
		if DATE_RE.match(s):
			try:
				return float((datetime.date.fromisoformat(s) - EPOCH).days)
			except ValueError:
				return math.nan
		if DATETIME_RE.match(s):
			try:
				return _days(datetime.datetime.fromisoformat(s.replace(" ", "T")))
			except ValueError:
				return math.nan
		try:
			return float(s)
		except ValueError:
			return math.nan
	if isinstance(v, dict):
		return math.nan
	return math.nan


def _days(dt: datetime.datetime) -> float:
	naive = dt.replace(tzinfo=None)
	delta = naive - datetime.datetime(1970, 1, 1)
	return delta.total_seconds() / 86400


def to_string(v) -> str:
	if isinstance(v, NodeSet):
		return to_string(v[0]) if v else ""
	if isinstance(v, bool):
		return "true" if v else "false"
	if isinstance(v, float):
		return format_number(v)
	if isinstance(v, int):
		return str(v)
	if isinstance(v, datetime.datetime):
		return v.isoformat()
	if isinstance(v, datetime.date):
		return v.isoformat()
	if isinstance(v, dict):
		return ""
	return "" if v is None else str(v)


def format_number(v: float) -> str:
	if math.isnan(v):
		return "NaN"
	if math.isinf(v):
		return "Infinity" if v > 0 else "-Infinity"
	if v == int(v) and abs(v) < 1e15:
		return str(int(v))
	return repr(v)


def to_bool(v) -> bool:
	if isinstance(v, NodeSet):
		return len(v) > 0
	if isinstance(v, bool):
		return v
	if isinstance(v, int | float):
		return not (v == 0 or math.isnan(v))
	if isinstance(v, datetime.date):
		return True
	if isinstance(v, str):
		return v != ""
	return bool(v)


def _is_number(v) -> bool:
	return isinstance(v, int | float) and not isinstance(v, bool)


def _is_date(v) -> bool:
	return isinstance(v, datetime.date)


def equals(a, b) -> bool:
	if isinstance(a, NodeSet):
		return any(equals(x, b) for x in a)
	if isinstance(b, NodeSet):
		return any(equals(a, x) for x in b)
	if isinstance(a, bool) or isinstance(b, bool):
		return to_bool(a) == to_bool(b)
	if _is_number(a) or _is_number(b) or _is_date(a) or _is_date(b):
		x, y = to_number(a), to_number(b)
		return x == y  # NaN == anything is False
	return to_string(a) == to_string(b)


def compare(op: str, a, b) -> bool:
	if isinstance(a, NodeSet):
		return any(compare(op, x, b) for x in a)
	if isinstance(b, NodeSet):
		return any(compare(op, a, x) for x in b)
	x, y = to_number(a), to_number(b)
	if math.isnan(x) or math.isnan(y):
		return False
	return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]


# ── evaluation ─────────────────────────────────────────────────────────────────


def evaluate(node: dict, ctx: Context):
	if "lit" in node:
		return node["lit"]
	if "ref" in node:
		if node["ref"] is None:
			raise EvalError(f"unresolved reference ${{{node.get('name')}}}")
		return ctx.lookup(node["ref"])
	if node.get("self"):
		return ctx.lookup(ctx.self_path) if ctx.self_path else ""
	if node.get("parent"):
		return ""
	if "col" in node:
		if ctx.columns is None:
			raise EvalError(f"column {node['col']} outside a choice filter")
		return ctx.columns.get(node["col"], "")
	if "op" in node:
		return _op(node["op"], node["args"], ctx)
	if "fn" in node:
		return _call(node["fn"], node["args"], ctx)
	raise EvalError(f"unknown node {node}")


def _op(op: str, args: list, ctx: Context):
	if op == "and":
		return to_bool(evaluate(args[0], ctx)) and to_bool(evaluate(args[1], ctx))
	if op == "or":
		return to_bool(evaluate(args[0], ctx)) or to_bool(evaluate(args[1], ctx))
	if op == "neg":
		return -to_number(evaluate(args[0], ctx))
	a = evaluate(args[0], ctx)
	b = evaluate(args[1], ctx)
	if op == "=":
		return equals(a, b)
	if op == "!=":
		if isinstance(a, NodeSet) or isinstance(b, NodeSet):
			left = a if isinstance(a, NodeSet) else [a]
			right = b if isinstance(b, NodeSet) else [b]
			return any(not equals(x, y) for x in left for y in right)
		return not equals(a, b)
	if op in ("<", "<=", ">", ">="):
		return compare(op, a, b)
	x, y = to_number(a), to_number(b)
	if op == "+":
		return x + y
	if op == "-":
		# date - date gives days; date - number gives a number of days too
		return x - y
	if op == "*":
		return x * y
	if op == "div":
		if y == 0:
			if math.isnan(x) or x == 0:
				return math.nan
			return math.inf if x > 0 else -math.inf
		return x / y
	if op == "mod":
		if y == 0 or math.isnan(x) or math.isnan(y) or math.isinf(x):
			return math.nan
		return math.fmod(x, y)
	raise EvalError(f"unknown operator {op}")


def _num_args(args, ctx) -> list[float]:
	values = []
	for a in args:
		v = evaluate(a, ctx)
		if isinstance(v, NodeSet):
			values.extend(to_number(x) for x in v)
		else:
			values.append(to_number(v))
	return values


def _round_half_away(x: float, digits: int = 0) -> float:
	if math.isnan(x) or math.isinf(x):
		return x
	factor = 10**digits
	scaled = abs(x) * factor
	rounded = math.floor(scaled + 0.5 + 1e-9) / factor
	return math.copysign(rounded, x) if rounded else 0.0


def _to_date(v):
	if isinstance(v, datetime.datetime):
		return v
	if isinstance(v, datetime.date):
		return v
	if isinstance(v, str):
		s = v.strip()
		if DATE_RE.match(s):
			return datetime.date.fromisoformat(s)
		if DATETIME_RE.match(s):
			return datetime.datetime.fromisoformat(s.replace(" ", "T"))
	n = to_number(v)
	if math.isnan(n):
		return None
	if n == int(n):
		return EPOCH + datetime.timedelta(days=int(n))
	return datetime.datetime(1970, 1, 1) + datetime.timedelta(days=n)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _format_date(value, fmt: str) -> str:
	d = _to_date(value)
	if d is None:
		return ""
	is_dt = isinstance(d, datetime.datetime)
	out = []
	i = 0
	while i < len(fmt):
		ch = fmt[i]
		if ch == "%" and i + 1 < len(fmt):
			code = fmt[i + 1]
			i += 2
			out.append(
				{
					"Y": f"{d.year:04d}",
					"y": f"{d.year % 100:02d}",
					"m": f"{d.month:02d}",
					"n": str(d.month),
					"b": MONTHS[d.month - 1],
					"d": f"{d.day:02d}",
					"e": str(d.day),
					"a": DAYS[d.weekday()],
					"H": f"{d.hour:02d}" if is_dt else "00",
					"h": str(d.hour) if is_dt else "0",
					"M": f"{d.minute:02d}" if is_dt else "00",
					"S": f"{d.second:02d}" if is_dt else "00",
					"3": f"{d.microsecond // 1000:03d}" if is_dt else "000",
				}.get(code, "%" + code)
			)
			continue
		out.append(ch)
		i += 1
	return "".join(out)


def _split(value) -> list[str]:
	return to_string(value).split()


def _call(fn: str, args: list, ctx: Context):
	def arg(i):
		return evaluate(args[i], ctx)

	if fn == "if":
		return arg(1) if to_bool(arg(0)) else arg(2)
	if fn == "not":
		return not to_bool(arg(0))
	if fn == "true":
		return True
	if fn == "false":
		return False
	if fn == "boolean":
		return to_bool(arg(0))
	if fn == "coalesce":
		first = to_string(arg(0))
		return first if first != "" else arg(1)
	if fn == "selected":
		return to_string(arg(1)).strip() in _split(arg(0))
	if fn == "count-selected":
		return float(len(_split(arg(0))))
	if fn == "selected-at":
		items = _split(arg(0))
		idx = to_number(arg(1))
		if math.isnan(idx) or idx < 0 or int(idx) >= len(items):
			return ""
		return items[int(idx)]
	if fn == "jr:choice-name":
		value = to_string(arg(0))
		target = to_string(arg(1)).strip()
		if target.startswith("${") and target.endswith("}"):
			target = target[2:-1]
		for path, labels in ctx.choice_labels.items():
			if path.rsplit("/", 1)[-1] == target:
				return labels.get(value, "")
		return ""
	if fn == "concat":
		parts = []
		for a in args:
			v = evaluate(a, ctx)
			if isinstance(v, NodeSet):
				parts.extend(to_string(x) for x in v)
			else:
				parts.append(to_string(v))
		return "".join(parts)
	if fn == "substr":
		s = to_string(arg(0))
		start = to_number(arg(1))
		start = 0 if math.isnan(start) else max(0, int(start))
		if len(args) == 3:
			end = to_number(arg(2))
			end = len(s) if math.isnan(end) else int(end)
			return s[start:end] if end > start else ""
		return s[start:]
	if fn == "string-length":
		return float(len(to_string(arg(0) if args else evaluate({"self": True}, ctx))))
	if fn == "contains":
		return to_string(arg(1)) in to_string(arg(0))
	if fn == "starts-with":
		return to_string(arg(0)).startswith(to_string(arg(1)))
	if fn == "ends-with":
		return to_string(arg(0)).endswith(to_string(arg(1)))
	if fn == "normalize-space":
		return " ".join(to_string(arg(0) if args else evaluate({"self": True}, ctx)).split())
	if fn == "regex":
		value = to_string(arg(0))[:10000]
		try:
			return re.search(to_string(arg(1)), value) is not None
		except re.error:
			return False
	if fn == "string":
		return to_string(arg(0) if args else evaluate({"self": True}, ctx))
	if fn == "int":
		x = to_number(arg(0))
		if math.isnan(x) or math.isinf(x):
			return x
		return float(math.trunc(x))
	if fn == "number":
		return to_number(arg(0) if args else evaluate({"self": True}, ctx))
	if fn == "round":
		digits = 0
		if len(args) == 2:
			d = to_number(arg(1))
			digits = 0 if math.isnan(d) else int(d)
		return _round_half_away(to_number(arg(0)), digits)
	if fn == "abs":
		return abs(to_number(arg(0)))
	if fn == "pow":
		try:
			return math.pow(to_number(arg(0)), to_number(arg(1)))
		except (OverflowError, ValueError):
			return math.nan
	if fn == "floor":
		x = to_number(arg(0))
		return x if math.isnan(x) or math.isinf(x) else float(math.floor(x))
	if fn == "ceiling":
		x = to_number(arg(0))
		return x if math.isnan(x) or math.isinf(x) else float(math.ceil(x))
	if fn in ("min", "max"):
		values = _num_args(args, ctx)
		if not values or any(math.isnan(v) for v in values):
			return math.nan
		return min(values) if fn == "min" else max(values)
	if fn == "today":
		return ctx.today()
	if fn == "now":
		return ctx.now()
	if fn == "date":
		d = _to_date(arg(0))
		return "" if d is None else d
	if fn == "decimal-date-time":
		return to_number(arg(0))
	if fn in ("format-date", "format-date-time"):
		return _format_date(arg(0), to_string(arg(1)))
	if fn == "count":
		v = arg(0)
		if isinstance(v, NodeSet):
			return float(len(v))
		return 1.0  # one node (e.g. a question in the current repeat row), answered or not
	if fn == "sum":
		v = arg(0)
		items = v if isinstance(v, NodeSet) else [v]
		return float(math.fsum(to_number(x) for x in items)) if items else 0.0
	if fn == "position":
		return float(ctx.row + 1) if ctx.row is not None else 1.0
	if fn == "once":
		current = ctx.lookup(ctx.self_path) if ctx.self_path else ""
		if to_string(current) != "":
			return current
		return arg(0)
	if fn == "uuid":
		if args:
			length = to_number(arg(0))
			n = 32 if math.isnan(length) else max(1, int(length))
			raw = ""
			while len(raw) < n:
				raw += uuid_lib.uuid4().hex
			return raw[:n]
		return str(uuid_lib.uuid4())
	raise EvalError(f"unsupported function {fn}")
