"""Stage 3: types, choice lists, formulas, references, cycles, Live-ability and settings.

Unlike stages 1–2, every check here runs even when others fail, so the designer sees all
problems in one round. The parsed and resolved formulas are kept in :class:`Analysis` and
reused by the compiler, so nothing is parsed twice.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

from xlsform.core.expr import emit_js, regex_safety
from xlsform.core.expr.evaluate import FUNCTIONS, REJECTED_FUNCTIONS
from xlsform.core.expr.parser import CurlyQuoteError, ExprSyntaxError, parse, walk
from xlsform.core.form import (
	ALL_KNOWN_TYPES,
	GROUP,
	META_IGNORED_TYPES,
	NO_LABEL_OK,
	QUESTION,
	REPEAT,
	SELECT_TYPES,
	SUPPORTED_TYPES,
	UNSUPPORTED_TYPES,
	Choice,
	ChoiceList,
	Form,
	Node,
)
from xlsform.core.i18n import N_, tr
from xlsform.core.issues import Issue, issue
from xlsform.core.reader import Cell, Row
from xlsform.core.structure import CHOICE_COLUMN_RE, choice_column_issue, is_extra_choice_column
from xlsform.core.suggest import closest, slug

FORM_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
CHOICE_NAME_BAD = re.compile(r"[\s<>%\"#*?\\/]")

EXPR_COLUMNS = (
	"relevant",
	"constraint",
	"calculation",
	"required",
	"read_only",
	"repeat_count",
	"choice_filter",
)
LIVE_COLUMNS = ("relevant", "required", "read_only")
STATIC_TRUE = {"yes", "true", "true()", "1"}
STATIC_FALSE = {"no", "false", "false()", "0", ""}

ACCEPTED_APPEARANCES = {
	"minimal",
	"field-list",
	"multiline",
	"horizontal",
	"horizontal-compact",
	"likert",
	"quick",
	"numbers",
	"no-calendar",
	"signature",
	"compact",
	"label",
	"list-nolabel",
	"list",
	"autocomplete",
	"search",
	"thousands-sep",
	"vertical",
	"table-list",
	"w1",
	"w2",
	"w3",
	"w4",
	"w5",
	"w6",
	"w7",
	"w8",
	"w9",
	"w10",
	"month-year",
	"year",
	"new",
}
KNOWN_SETTINGS = {"form_title", "form_id", "version", "default_language", "instance_name"}
IGNORED_SETTINGS = {
	"submission_url",
	"style",
	"allow_choice_duplicates",
	"namespaces",
	"clean_text_values",
	"omit_instanceid",
	"auto_send",
	"auto_delete",
	"client_editable",
	"name",
	"__row__",
}
AGGREGATES = {"count", "sum", "min", "max", "concat"}


@dataclass
class Options:
	max_choices_per_list: int = 20000
	max_expression_length: int = 2000
	published_version: str | None = None
	files: dict[str, bytes] = field(default_factory=dict)
	allow_web: bool = True


@dataclass
class Analysis:
	"""Resolved formulas, keyed by question path then column."""

	asts: dict[str, dict[str, dict]] = field(default_factory=dict)
	static: dict[str, dict[str, bool]] = field(default_factory=dict)
	defaults: dict[str, str] = field(default_factory=dict)
	filters: dict[str, list[tuple[str, dict]]] = field(default_factory=dict)
	calc_order: list[str] = field(default_factory=list)
	live_calcs: set[str] = field(default_factory=set)
	ranges: dict[str, dict[str, float]] = field(default_factory=dict)
	instance_name: list[dict] | None = None


def check(form: Form, opts: Options) -> tuple[Analysis, list[Issue]]:
	issues: list[Issue] = []
	analysis = Analysis()
	_load_csv_lists(form, opts, issues)
	issues += _check_types(form)
	issues += _check_lists(form, opts)
	issues += _check_repeats(form)
	issues += _check_labels(form)
	issues += _check_appearance_parameters(form, analysis)
	issues += _check_settings(form, opts, analysis)
	_parse_all(form, opts, analysis, issues)
	_check_cycles(form, analysis, issues)
	_check_live(form, analysis, issues)
	_check_filters(form, opts, analysis, issues)
	if opts.allow_web:
		for node in _questions(form):
			if node.base_type in ("geopoint", "geotrace", "geoshape"):
				issues.append(
					issue("W-WEB-FIELD", name=node.name, type=node.base_type, **_where(node, "type"))
				)
	return analysis, issues


def _where(node: Node, column: str) -> dict:
	return dict(sheet="survey", row=node.row_number, column=column, col_index=node.col(column))


def _questions(form: Form) -> list[Node]:
	return [n for n in form.nodes() if n.kind == QUESTION]


def _check_types(form: Form) -> list[Issue]:
	issues = []
	for node in [*_questions(form), *(n for n in form.nodes() if n.base_type == "begin_loop")]:
		base = node.base_type
		if base in SUPPORTED_TYPES:
			continue
		where = _where(node, "type")
		if base in META_IGNORED_TYPES:
			issues.append(issue("W-META-IGNORED", type=base, **where))
		elif base in UNSUPPORTED_TYPES:
			base = {"begin_loop": "loop", "select_one_external": "select_one_external"}.get(base, base)
			alternative = tr(N_(", or use select_multiple")) if base == "rank" else ""
			issues.append(issue("E-TYPE-UNSUPPORTED", type=base, alternative=alternative, **where))
		else:
			guess = closest(node.type.raw.replace(" ", "_"), ALL_KNOWN_TYPES)
			hint = (
				tr(N_("Did you mean {guess}?"), guess=guess)
				if guess
				else tr(N_("See the list of question types in the docs."))
			)
			issues.append(issue("E-TYPE-UNKNOWN", type=node.type.raw, hint=hint, **where))
	return issues


def _load_csv_lists(form: Form, opts: Options, issues: list[Issue]) -> None:
	for node in _questions(form):
		if not node.base_type.endswith("_from_file"):
			continue
		file_name = node.type.file_name
		if file_name in form.lists:
			continue
		content = opts.files.get(file_name)
		if content is None:
			issues.append(issue("E-FILE-CSV-MISSING", file=file_name or "?", **_where(node, "type")))
			continue
		lst = ChoiceList(file_name, row=0, from_file=file_name)
		text = content.decode("utf-8-sig", errors="replace")
		reader = csv.DictReader(io.StringIO(text))
		bad_columns = [
			raw
			for raw in reader.fieldnames or []
			if is_extra_choice_column((raw or "").strip().lower())
			and not CHOICE_COLUMN_RE.match((raw or "").strip().lower())
		]
		if bad_columns:
			issues += [choice_column_issue(raw, sheet=file_name) for raw in bad_columns]
			continue
		for line_no, record in enumerate(reader, start=2):
			record = {(k or "").strip().lower(): (v or "").strip() for k, v in record.items()}
			name = record.get("name", "")
			if not name:
				continue
			labels = {form.default_language: record.get("label") or name}
			for key, value in record.items():
				if key.startswith("label::") and value:
					labels[key.split("::", 1)[1]] = value
			extra = {
				k: v
				for k, v in record.items()
				if k not in ("name", "label") and not k.startswith("label::") and v
			}
			row = Row(line_no, {"name": Cell(name, 1)})
			lst.choices.append(Choice(name, labels, extra, row))
		form.lists[file_name] = lst
		form.choice_columns |= {k for c in lst.choices for k in c.extra}


def _list_name(node: Node) -> str:
	return node.type.file_name if node.base_type.endswith("_from_file") else node.type.list_name


def _check_lists(form: Form, opts: Options) -> list[Issue]:
	issues = []
	used: set[str] = set()
	for node in _questions(form):
		if node.base_type not in SELECT_TYPES:
			continue
		name = _list_name(node)
		if node.base_type.endswith("_from_file"):
			if name in form.lists:
				used.add(name)
			continue
		if name in form.lists:
			used.add(name)
			continue
		guess = closest(name, form.lists) if name else None
		if guess:
			hint = tr(N_('Add it to the choices sheet, or fix the spelling (found: "{guess}").'), guess=guess)
		else:
			hint = tr(
				N_("Add it to the choices sheet, or fix the list name after {type}."), type=node.base_type
			)
		issues.append(issue("E-LIST-MISSING", list=name, hint=hint, **_where(node, "type")))
	for name in sorted(used):
		lst = form.lists[name]
		sheet = None if lst.from_file else "choices"
		if not lst.choices:
			issues.append(issue("E-LIST-EMPTY", list=name, sheet=sheet, row=lst.row or None))
			continue
		if len(lst.choices) > opts.max_choices_per_list:
			issues.append(
				issue(
					"E-LIST-TOO-LARGE",
					list=name,
					count=len(lst.choices),
					limit=opts.max_choices_per_list,
					sheet=sheet,
					row=lst.row or None,
				)
			)
		seen: dict[str, list[int]] = {}
		for choice in lst.choices:
			col = choice.row.col("name")
			where = dict(sheet=sheet, row=choice.row.number, column="name", col_index=col)
			if not choice.name:
				issues.append(
					issue(
						"E-CHOICE-NAME",
						choice="",
						list=name,
						reason=tr(N_("is empty")),
						fixed="choice_1",
						**where,
					)
				)
				continue
			if CHOICE_NAME_BAD.search(choice.name) or len(choice.name) > 140:
				reason = (
					tr(N_("contains a space"))
					if any(ch.isspace() for ch in choice.name)
					else tr(N_('is too long or contains one of < > % " # * ? \\ /'))
				)
				issues.append(
					issue(
						"E-CHOICE-NAME",
						choice=choice.name,
						list=name,
						reason=reason,
						fixed=slug(choice.name)[:140],
						**where,
					)
				)
				continue
			seen.setdefault(choice_key(choice.name), []).append(choice)
		for same in seen.values():
			if len(same) > 1:
				spellings = list(dict.fromkeys(c.name for c in same))
				issues.append(
					issue(
						"E-CHOICE-DUPLICATE",
						choices=" / ".join(f'"{s}"' for s in spellings),
						list=name,
						rows=" and ".join(str(c.row.number) for c in same),
						sheet=sheet,
						row=same[1].row.number,
						column="name",
						col_index=same[1].row.col("name"),
					)
				)
	return issues


def choice_key(name: str) -> str:
	"""How MariaDB's default collation (utf8mb4_unicode_ci, PAD SPACE) compares choice names.

	Choice names are the primary key of the list DocType, so names equal under it collide.
	"""
	decomposed = unicodedata.normalize("NFKD", name.rstrip(" "))
	return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _check_repeats(form: Form) -> list[Issue]:
	issues = []
	for node in form.nodes():
		if node.kind != REPEAT:
			continue
		outer = node.enclosing_repeat
		if outer is not None:
			issues.append(
				issue(
					"E-REPEAT-NESTED",
					inner=node.name,
					inner_row=node.row_number,
					outer=outer.name,
					outer_row=outer.row_number,
					**_where(node, "type"),
				)
			)
		if not any(c.kind == QUESTION for c in node.walk()):
			issues.append(issue("E-REPEAT-EMPTY", name=node.name, **_where(node, "type")))
	return issues


def _check_labels(form: Form) -> list[Issue]:
	issues = []
	for node in _questions(form):
		if node.base_type in NO_LABEL_OK or node.base_type not in SUPPORTED_TYPES:
			continue
		if not node.localized("label", form.default_language):
			issues.append(issue("I-NO-LABEL", name=node.name, **_where(node, "label")))
	return issues


def _check_appearance_parameters(form: Form, analysis: Analysis) -> list[Issue]:
	issues = []
	for node in form.nodes():
		for word in node.cell("appearance").split():
			if word.lower() not in ACCEPTED_APPEARANCES:
				issues.append(issue("W-APPEARANCE", appearance=word, **_where(node, "appearance")))
		params = node.cell("parameters")
		if not params:
			continue
		parsed: dict[str, float] = {}
		for part in re.split(r"[\s;,]+", params.strip()):
			if not part:
				continue
			key, _, value = part.partition("=")
			key = key.strip().lower()
			value = value.strip()
			if node.base_type == "range" and key in ("start", "end", "step"):
				try:
					parsed[key] = float(value)
				except ValueError:
					issues.append(
						issue("E-PARAMETER-INVALID", parameter=key, value=value, **_where(node, "parameters"))
					)
			else:
				issues.append(issue("W-PARAMETER", parameter=key, **_where(node, "parameters")))
		if node.base_type == "range":
			analysis.ranges[node.path] = {"start": 1.0, "end": 10.0, "step": 1.0} | parsed
	for node in _questions(form):
		if node.base_type == "range" and node.path not in analysis.ranges:
			analysis.ranges[node.path] = {"start": 1.0, "end": 10.0, "step": 1.0}
	return issues


def _check_settings(form: Form, opts: Options, analysis: Analysis) -> list[Issue]:
	issues = []
	row = form.settings_cols.get("__row__")

	def where(key):
		return dict(sheet="settings", row=row, column=key, col_index=form.settings_cols.get(key))

	form_id = form.settings.get("form_id", "")
	if not FORM_ID_RE.match(form_id):
		fixed = normalize_form_id(form_id)
		if fixed:
			form.settings["form_id"] = fixed
			issues.append(issue("W-FORM-ID", value=form_id, fixed=fixed, **where("form_id")))
		else:
			issues.append(
				issue(
					"E-SETTING-INVALID",
					setting="form_id",
					value=form_id,
					reason=tr(N_("it has no letters or numbers to build a form ID from")),
					hint=tr(N_("Use lower-case letters, numbers and _, e.g. household_survey.")),
					**where("form_id"),
				)
			)
	if form.settings.get("public_key"):
		issues.append(issue("E-SETTING-ENCRYPTED", **where("public_key")))
	for key in form.settings:
		if key in KNOWN_SETTINGS or key == "public_key" or key == "__row__":
			continue
		issues.append(issue("W-SETTING-IGNORED", setting=key, **where(key)))

	version = form.version
	if version and not VERSION_RE.match(version):
		issues.append(
			issue(
				"E-SETTING-INVALID",
				setting="version",
				value=version,
				reason=tr(N_("it becomes part of the version's document name")),
				hint=tr(
					N_(
						"Use up to 40 letters, numbers, dots, dashes and _, starting with a letter or number, e.g. 2026110301."
					)
				),
				**where("version"),
			)
		)
	elif version and opts.published_version:
		cmp = compare_versions(version, opts.published_version)
		if cmp == 0:
			issues.append(issue("E-VERSION-PUBLISHED", version=version, **where("version")))
		elif cmp < 0:
			issues.append(
				issue(
					"E-VERSION-ORDER", version=version, published=opts.published_version, **where("version")
				)
			)

	instance_name = form.settings.get("instance_name")
	if instance_name and len(instance_name) > opts.max_expression_length:
		issues.append(
			issue(
				"E-EXPR-TOO-LONG",
				length=len(instance_name),
				limit=opts.max_expression_length,
				**where("instance_name"),
			)
		)
	elif instance_name:
		analysis.instance_name = _instance_name_parts(instance_name, form)
		if analysis.instance_name is None:
			issues.append(issue("W-INSTANCE-NAME", **where("instance_name")))
	return issues


def normalize_form_id(raw: str) -> str | None:
	"""``Flat test`` -> ``flat_test``; None when nothing usable is left."""
	if FORM_ID_RE.match(raw or ""):
		return raw
	if not any(ch.isalnum() for ch in raw or ""):
		return None
	fixed = slug(raw)[:41].strip("_")
	if fixed[0].isdigit() or fixed.startswith("q_"):
		fixed = ("f_" + fixed.removeprefix("q_"))[:41]
	if len(fixed) < 3:
		fixed = f"{fixed}_form"
	return fixed if FORM_ID_RE.match(fixed) else None


def _instance_name_parts(text: str, form: Form) -> list[dict] | None:
	try:
		ast = parse(text)
	except ExprSyntaxError:
		return None
	parts = ast["args"] if ast.get("fn") == "concat" else [ast]
	names = form.by_name()
	out = []
	for p in parts:
		if "lit" in p and isinstance(p["lit"], str):
			out.append({"lit": p["lit"]})
		elif "ref" in p and p["name"] in names and names[p["name"]].enclosing_repeat is None:
			node = names[p["name"]]
			if node.kind != QUESTION:
				return None
			out.append({"ref": node.path})
		else:
			return None
	return out


def version_key(value: str) -> tuple:
	parts = re.findall(r"\d+|[^\d]+", value.strip())
	return tuple(
		(0, int(p), "") if p.isdigit() else (1, 0, p.lower()) for p in parts if p not in ("-", ".", "_", " ")
	)


def compare_versions(a: str, b: str) -> int:
	ka, kb = version_key(a), version_key(b)
	return (ka > kb) - (ka < kb)


def _parse_all(form: Form, opts: Options, analysis: Analysis, issues: list[Issue]) -> None:
	names = form.by_name()
	for node in form.nodes():
		for column in EXPR_COLUMNS:
			text = node.cell(column)
			if not text:
				continue
			if column in ("required", "read_only") and text.strip().lower() in STATIC_TRUE | STATIC_FALSE:
				analysis.static.setdefault(node.path, {})[column] = text.strip().lower() in STATIC_TRUE
				continue
			where = _where(node, column)
			if len(text) > opts.max_expression_length:
				issues.append(
					issue("E-EXPR-TOO-LONG", length=len(text), limit=opts.max_expression_length, **where)
				)
				continue
			try:
				ast = parse(text, allow_columns=(column == "choice_filter"))
			except CurlyQuoteError:
				issues.append(issue("E-EXPR-QUOTE", **where))
				continue
			except ExprSyntaxError as exc:
				issues.append(issue("E-EXPR-SYNTAX", reason=exc.reason, expr=text, **where))
				continue
			if _resolve(ast, node, column, names, issues, where) and _check_regex(ast, issues, where):
				analysis.asts.setdefault(node.path, {})[column] = ast
		_parse_default(node, analysis, issues)


def _parse_default(node: Node, analysis: Analysis, issues: list[Issue]) -> None:
	text = node.cell("default")
	if not text:
		return
	stripped = text.strip()
	if "${" in stripped or re.match(r"^[A-Za-z][A-Za-z0-9:\-]*\s*\(", stripped):
		low = stripped.replace(" ", "").lower()
		if low == "today()":
			analysis.defaults[node.path] = "Today"
		elif low == "now()":
			analysis.defaults[node.path] = "now"
		else:
			issues.append(issue("E-DEFAULT-DYNAMIC", value=stripped, **_where(node, "default")))
		return
	analysis.defaults[node.path] = text


def _resolve(
	ast: dict, node: Node, column: str, names: dict[str, Node], issues: list[Issue], where: dict
) -> bool:
	ok = True
	scope_repeat = node.enclosing_repeat

	def visit(n: dict, aggregate: bool) -> None:
		nonlocal ok
		if "fn" in n:
			fn = n["fn"]
			if fn in REJECTED_FUNCTIONS or fn not in FUNCTIONS:
				issues.append(issue("E-FN-UNSUPPORTED", fn=fn, **where))
				ok = False
			else:
				spec = FUNCTIONS[fn]
				got = len(n["args"])
				if got < spec.min_args or (spec.max_args is not None and got > spec.max_args):
					expected = _arity_text(spec.min_args, spec.max_args)
					issues.append(
						issue("E-FN-ARGS", fn=fn, expected=expected, got=got, example=spec.example, **where)
					)
					ok = False
			for a in n["args"]:
				visit(a, aggregate or fn in AGGREGATES)
			return
		if "ref" in n:
			target = names.get(n["name"])
			if target is None:
				guess = closest(n["name"], names)
				hint = (
					tr(N_("Did you mean ${{{guess}}}?"), guess=guess)
					if guess
					else tr(N_("Check the spelling of the question name."))
				)
				issues.append(issue("E-REF-UNKNOWN", name=n["name"], hint=hint, **where))
				ok = False
				return
			if target is node and column in ("constraint",):
				issues.append(issue("E-REF-SELF", name=node.name, **where))
				ok = False
				return
			n["ref"] = target.path
			target_repeat = target if target.kind == REPEAT else target.enclosing_repeat
			if target_repeat is not None and target_repeat is not scope_repeat and not aggregate:
				issues.append(issue("E-REF-REPEAT", name=n["name"], repeat=target_repeat.name, **where))
				ok = False
			return
		for a in n.get("args", ()):
			visit(a, aggregate)

	visit(ast, False)
	return ok


def _check_regex(ast: dict, issues: list[Issue], where: dict) -> bool:
	"""Every regex() pattern is fixed text in the safe set (see expr/regex_safety.py)."""
	ok = True
	for n in walk(ast):
		if n.get("fn") != "regex" or len(n["args"]) != 2:
			continue
		pattern = n["args"][1]
		if "lit" in pattern and isinstance(pattern["lit"], str):
			reason = regex_safety.unsafe_reason(pattern["lit"])
		else:
			reason = regex_safety.REASON_DYNAMIC
		if reason is not None:
			issues.append(
				issue(
					"E-REGEX-UNSAFE",
					reason=tr(reason, limit=regex_safety.MAX_PATTERN_LENGTH),
					input_limit=regex_safety.MAX_INPUT_LENGTH,
					**where,
				)
			)
			ok = False
	return ok


def _arity_text(lo: int, hi: int | None) -> str:
	if hi is None:
		return tr(N_("at least {n} values"), n=lo)
	if lo == hi:
		return tr(N_("{n} values"), n=lo) if lo != 1 else tr(N_("1 value"))
	return tr(N_("{lo} to {hi} values"), lo=lo, hi=hi)


def _deps(ast: dict) -> set[str]:
	return {n["ref"] for n in walk(ast) if n.get("ref")}


def _check_cycles(form: Form, analysis: Analysis, issues: list[Issue]) -> None:
	graph: dict[str, set[str]] = {}
	for path, cols in analysis.asts.items():
		deps = set()
		for column in ("calculation", "relevant"):
			if column in cols:
				deps |= _deps(cols[column])
		deps.discard(path)
		graph[path] = deps
	order: list[str] = []
	state: dict[str, int] = {}
	reported: set[frozenset] = set()
	by_path = form.by_path()

	def report(cycle: list[str]) -> None:
		key = frozenset(cycle)
		if key in reported:
			return
		reported.add(key)
		node = by_path[cycle[0]]
		column = "calculation" if "calculation" in analysis.asts.get(cycle[0], {}) else "relevant"
		issues.append(
			issue(
				"E-CALC-CYCLE",
				cycle=" → ".join(c.rsplit("/", 1)[-1] for c in cycle),
				**_where(node, column),
			)
		)

	for start in sorted(graph):
		if state.get(start) is not None:
			continue
		state[start] = 1
		stack = [start]
		pending = [iter(sorted(graph.get(start, ())))]
		while pending:
			d = next(pending[-1], None)
			if d is None:
				done = stack.pop()
				pending.pop()
				state[done] = 2
				order.append(done)
			elif state.get(d) == 1:
				report([*stack[stack.index(d) :], d])
			elif state.get(d) is None:
				state[d] = 1
				stack.append(d)
				pending.append(iter(sorted(graph.get(d, ()))))
	calcs = {p for p, cols in analysis.asts.items() if "calculation" in cols}
	analysis.calc_order = [p for p in order if p in calcs]


def make_scope(form: Form, analysis: Analysis, node: Node, fieldname=None) -> emit_js.Scope:
	by_path = form.by_path()

	def type_of(path: str) -> str:
		n = by_path[path]
		return n.kind if n.kind in (GROUP, REPEAT) else n.base_type

	def repeat_of(path: str) -> str | None:
		r = by_path[path].enclosing_repeat
		return r.path if r else None

	def calc_ast(path: str) -> dict | None:
		return analysis.asts.get(path, {}).get("calculation")

	own_repeat = node.enclosing_repeat
	return emit_js.Scope(
		fieldname=fieldname or (lambda path: path.rsplit("/", 1)[-1]),
		type_of=type_of,
		repeat_of=repeat_of,
		calc_ast=calc_ast,
		scope_repeat=own_repeat.path if own_repeat else None,
	)


def _check_live(form: Form, analysis: Analysis, issues: list[Issue]) -> None:
	by_path = form.by_path()
	for path, cols in analysis.asts.items():
		node = by_path[path]
		for column in LIVE_COLUMNS:
			if column not in cols:
				continue
			try:
				emit_js.emit(cols[column], make_scope(form, analysis, node))
			except emit_js.NotLive as exc:
				issues.append(_not_live_issue(exc, _where(node, column)))
	for path, cols in analysis.asts.items():
		if "calculation" in cols:
			try:
				emit_js.emit_value(cols["calculation"], make_scope(form, analysis, by_path[path]))
				analysis.live_calcs.add(path)
			except emit_js.NotLive:
				pass


def _not_live_issue(exc: emit_js.NotLive, where: dict) -> Issue:
	if isinstance(exc, emit_js.TooComplex):
		return issue("E-EXPR-TOO-COMPLEX", limit=emit_js.MAX_JS_LENGTH, **where)
	if exc.calc:
		return issue("E-CALC-NOT-LIVE", name=exc.calc, **where)
	return issue("E-EXPR-NOT-LIVE", what=exc.what, **where)


def _check_filters(form: Form, opts: Options, analysis: Analysis, issues: list[Issue]) -> None:
	by_path = form.by_path()
	for path, cols in analysis.asts.items():
		if "choice_filter" not in cols:
			continue
		node = by_path[path]
		where = _where(node, "choice_filter")
		if node.base_type not in SUPPORTED_TYPES:
			continue
		if node.base_type not in ("select_one", "select_one_from_file"):
			issues.append(issue("E-FILTER-MULTI", **where))
			continue
		list_name = _list_name(node)
		lst = form.lists.get(list_name)
		terms = _filter_terms(cols["choice_filter"])
		if terms is None:
			issues.append(
				issue(
					"E-FILTER-UNSUPPORTED",
					reason=tr(
						N_("only conditions of the form column = ${{question}} joined by and can be used")
					),
					**where,
				)
			)
			continue
		bad = False
		available = {k for c in lst.choices for k in c.extra} | {"name"} if lst else set()
		for column, value in terms:
			if lst is not None and column not in available and column not in form.choice_columns:
				issues.append(issue("E-FILTER-COLUMN", choice_column=column, list=list_name, **where))
				bad = True
				continue
			try:
				emit_js.filter_value(value, make_scope(form, analysis, node))
			except emit_js.NotLive as exc:
				issues.append(_not_live_issue(exc, where))
				bad = True
		if not bad:
			analysis.filters[path] = terms
			if opts.allow_web:
				issues.append(issue("W-WEB-FILTER", name=node.name, list=list_name, **where))


def _filter_terms(ast: dict) -> list[tuple[str, dict]] | None:
	"""Split ``a = ${x} and b = 'y'`` into ``[("a", ref x), ("b", lit y)]``."""
	if ast.get("op") == "and":
		left = _filter_terms(ast["args"][0])
		right = _filter_terms(ast["args"][1])
		if left is None or right is None:
			return None
		return left + right
	if ast.get("op") == "=":
		a, b = ast["args"]
		if "col" in a and "col" not in b and not any("col" in n for n in walk(b)):
			return [(a["col"], b)]
		if "col" in b and "col" not in a and not any("col" in n for n in walk(a)):
			return [(b["col"], a)]
	return None
