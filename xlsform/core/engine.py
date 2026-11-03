"""Server-side rules for one record (REQUIREMENTS.md section 8, "Server").

Frappe-free so it is unit-tested directly and shared with the conformance suite. Given a
version's ``compiled_meta`` and a document as a dict, :func:`run`:

1. recomputes calculations in dependency order,
2. works out which questions are relevant (own ``relevant`` ANDed with every enclosing
   group and repeat) and clears answers to non-relevant ones, as ODK does,
3. checks required answers, constraints, ranges, ``repeat_count`` and choice filters.

It returns the field updates to apply and every failure, by question label, so the user
gets one message listing all problems.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from xlsform.core.expr.evaluate import EvalError, evaluate, to_bool, to_number, to_string
from xlsform.core.values import MULTI, MetaIndex

NO_ANSWER_TYPES = {"note", "calculate", "start", "end", "today", "username"}


@dataclass
class Failure:
	path: str
	label: str
	message: str
	row: int | None = None  # 0-based row inside a repeat
	repeat_label: str | None = None
	kind: str = "constraint"  # required / constraint / range / repeat_count / choice


@dataclass
class Outcome:
	parent_updates: dict = field(default_factory=dict)  # fieldname -> value
	row_updates: dict = field(default_factory=dict)  # (table fieldname, row index) -> {fieldname: value}
	failures: list[Failure] = field(default_factory=list)
	relevant: dict = field(default_factory=dict)  # (path, row) -> bool


ChoiceLookup = Callable[[str, str], dict | None]


def run(
	meta: dict,
	doc: dict,
	*,
	choice_lookup: ChoiceLookup | None = None,
	today=None,
	now=None,
	language: str | None = None,
) -> Outcome:
	return _Engine(meta, doc, choice_lookup, today, now, language).run()


def calculated_data(meta: dict, doc: dict, *, today=None, now=None) -> dict:
	"""Answers with calculations filled in, as every other formula on the server sees them."""
	engine = _Engine(meta, doc, None, today, now, None)
	engine.calculate()
	return engine.data


class _Engine:
	def __init__(self, meta, doc, choice_lookup, today, now, language):
		self.meta = meta
		self.index = MetaIndex(meta)
		self.doc = doc
		self.data = self.index.data(doc)
		self.choice_lookup = choice_lookup
		self.kw = {}
		if today:
			self.kw["today"] = today
		if now:
			self.kw["now"] = now
		self.exprs = meta.get("expressions", {})
		self.static = meta.get("static", {})
		self.labels = meta.get("labels", {})
		self.messages = meta.get("messages", {})
		self.lang = language or meta.get("default_language")
		self.out = Outcome()

	# ── helpers ─────────────────────────────────────────────────────────────

	def label(self, path: str) -> str:
		labels = self.labels.get(path) or {}
		return (
			labels.get(self.lang)
			or labels.get(self.meta.get("default_language"))
			or next(iter(labels.values()), path.rsplit("/", 1)[-1])
		)

	def message(self, path: str, kind: str) -> str | None:
		msgs = (self.messages.get(path) or {}).get(kind) or {}
		return (
			msgs.get(self.lang)
			or msgs.get(self.meta.get("default_language"))
			or next(iter(msgs.values()), None)
		)

	def ctx(self, path: str | None, row: int | None, scope_repeat: str | None):
		return self.index.context(self.data, scope_repeat=scope_repeat, row=row, self_path=path, **self.kw)

	def eval(self, ast, path, row, scope_repeat):
		try:
			return evaluate(ast, self.ctx(path, row, scope_repeat))
		except (
			EvalError,
			ZeroDivisionError,
			OverflowError,
			ValueError,
			IndexError,
			TypeError,
			RecursionError,
		):
			return ""

	def value(self, path: str, row: int | None):
		repeat = self.index.repeat_of.get(path)
		if repeat is None:
			return self.data.get(path, "")
		rows = self.data.get(repeat) or []
		return rows[row].get(path, "") if row is not None and row < len(rows) else ""

	def set_value(self, path: str, row: int | None, value, stored) -> None:
		f = self.index.by_path[path]
		repeat = self.index.repeat_of.get(path)
		if repeat is None:
			self.data[path] = value
			self.out.parent_updates[f["fieldname"]] = stored
		else:
			self.data[repeat][row][path] = value
			table = self.index.by_path[repeat]["fieldname"]
			self.out.row_updates.setdefault((table, row), {})[f["fieldname"]] = stored

	def rows_of(self, path: str) -> list[int | None]:
		repeat = self.index.repeat_of.get(path)
		if repeat is None:
			return [None]
		return list(range(len(self.data.get(repeat) or [])))

	# ── steps ───────────────────────────────────────────────────────────────

	def run(self) -> Outcome:
		self.calculate()
		self.relevance_and_clear()
		self.calculate()
		self.relevance_and_clear()
		self.check()
		return self.out

	def calculate(self) -> None:
		for path in self.meta.get("calc_order", []):
			if path not in self.index.by_path:
				continue
			ast = self.exprs.get(path, {}).get("calculation")
			if not ast:
				continue
			scope = self.index.repeat_of.get(path)
			for row in self.rows_of(path):
				value = self.eval(ast, path, row, scope)
				text = to_string(value)
				stored = "" if text in ("NaN", "Infinity", "-Infinity") else text
				self.set_value(path, row, text, stored)

	def is_relevant(self, path: str, row: int | None) -> bool:
		key = (path, row)
		if key in self.out.relevant:
			return self.out.relevant[key]
		f = self.index.by_path.get(path)
		result = True
		if f is not None:
			parent = f.get("parent_path") or ""
			if parent:
				parent_is_repeat = parent in self.index.repeats
				result = self.is_relevant(parent, None if parent_is_repeat else row)
			ast = self.exprs.get(path, {}).get("relevant")
			if result and ast:
				# a repeat's own relevant is evaluated in the scope around it, which is also what
				# repeat_of gives for the repeat's path (repeats aren't nested in v1)
				scope = self.index.repeat_of.get(path)
				result = to_bool(self.eval(ast, None, row if scope else None, scope))
		self.out.relevant[key] = result
		return result

	def relevance_and_clear(self) -> None:
		self.out.relevant = {}
		for f in self.index.fields:
			path = f["path"]
			kind = f.get("kind", "question")
			if kind == "repeat":
				if not self.is_relevant(path, None) and self.data.get(path):
					self.data[path] = []
					self.out.parent_updates[f["fieldname"]] = []
				continue
			if kind != "question" or f["type"] == "note":
				continue
			for row in self.rows_of(path):
				if not self.is_relevant(path, row) and self.value(path, row) not in ("", None):
					self.set_value(path, row, "", self.blank(f))

	@staticmethod
	def blank(f: dict):
		if f["type"] in MULTI:
			return []
		if f["type"] == "acknowledge":
			return 0
		if f["fieldtype"] in ("Int", "Float"):
			return None
		return None

	def check(self) -> None:
		for f in self.index.fields:
			path = f["path"]
			kind = f.get("kind", "question")
			if kind == "repeat":
				self.check_repeat_count(f)
				continue
			if kind != "question" or f["type"] in NO_ANSWER_TYPES:
				continue
			scope = self.index.repeat_of.get(path)
			for row in self.rows_of(path):
				if not self.is_relevant(path, row):
					continue
				value = self.value(path, row)
				if self.required(path, row, scope) and _blank(value, f):
					self.fail(path, row, self.message(path, "required") or None, "required")
					continue
				if _blank(value, f):
					continue
				self.check_range(f, path, row, value)
				ast = self.exprs.get(path, {}).get("constraint")
				if ast and not to_bool(self.eval(ast, path, row, scope)):
					self.fail(path, row, self.message(path, "constraint"), "constraint")
				self.check_filter(f, path, row, value, scope)

	def required(self, path, row, scope) -> bool:
		static = self.static.get(path, {})
		if static.get("required"):
			return True
		ast = self.exprs.get(path, {}).get("required")
		return bool(ast) and to_bool(self.eval(ast, path, row, scope))

	def check_range(self, f, path, row, value) -> None:
		r = self.meta.get("ranges", {}).get(path)
		if not r:
			return
		x = to_number(value)
		lo, hi, step = min(r["start"], r["end"]), max(r["start"], r["end"]), abs(r.get("step") or 1)
		ok = not math.isnan(x) and lo <= x <= hi
		if ok and step:
			steps = (x - r["start"]) / step
			ok = abs(steps - round(steps)) < 1e-9
		if not ok:
			self.fail(path, row, None, "range", detail=(lo, hi, step))

	def check_filter(self, f, path, row, value, scope) -> None:
		terms = self.meta.get("filters", {}).get(path)
		if not terms or self.choice_lookup is None:
			return
		record = self.choice_lookup(f.get("list", ""), to_string(value))
		if record is None:
			self.fail(path, row, None, "choice")
			return
		for column, ast in terms:
			expected = to_string(self.eval(ast, path, row, scope))
			actual = to_string(value) if column == "name" else to_string(record.get(column, ""))
			if actual != expected:
				self.fail(path, row, None, "choice")
				return

	def check_repeat_count(self, f) -> None:
		path = f["path"]
		ast = self.exprs.get(path, {}).get("repeat_count")
		if not ast or not self.is_relevant(path, None):
			return
		expected = to_number(self.eval(ast, None, None, self.index.repeat_of.get(path)))
		if math.isnan(expected):
			return
		actual = len(self.data.get(path) or [])
		if math.isinf(expected):
			self.fail(path, None, None, "repeat_count")
			return
		if actual != int(expected):
			self.fail(path, None, None, "repeat_count", detail=(int(expected), actual))

	def fail(self, path, row, message, kind, detail=None) -> None:
		from xlsform.core.i18n import N_, tr

		label = self.label(path)
		if not message:
			if kind == "required":
				message = tr(N_("{label} is required."), label=label)
			elif kind == "range":
				lo, hi, step = detail
				message = tr(
					N_("{label} must be between {lo} and {hi} in steps of {step}."),
					label=label,
					lo=to_string(float(lo)),
					hi=to_string(float(hi)),
					step=to_string(float(step)),
				)
			elif kind == "choice":
				message = tr(N_("{label}: this choice isn't allowed with the other answers."), label=label)
			elif kind == "repeat_count" and detail is None:
				message = tr(
					N_("{label}: the number of rows can't be worked out from the answers."), label=label
				)
			elif kind == "repeat_count":
				message = tr(
					N_("{label} needs {expected} rows but has {actual}."),
					label=label,
					expected=detail[0],
					actual=detail[1],
				)
			else:
				message = tr(N_("{label}: this answer isn't valid."), label=label)
		repeat = self.index.repeat_of.get(path)
		self.out.failures.append(
			Failure(
				path=path,
				label=label,
				message=message,
				row=row,
				repeat_label=self.label(repeat) if repeat else None,
				kind=kind,
			)
		)


def _blank(value, f: dict) -> bool:
	if f["type"] == "acknowledge":
		return value != "OK"
	return value is None or to_string(value).strip() == ""
