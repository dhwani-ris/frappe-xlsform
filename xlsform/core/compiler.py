"""Compile a validated form into a plan of DocTypes, choice records and translations.

``compile_form`` is pure: it reads only its arguments (no database), so every rule in
REQUIREMENTS.md section 5 is unit-tested without a site. ``xlsform.runtime.apply`` turns
the plan into real DocTypes.

Plan shape::

    {"doctypes": [<DocType dict>, ...],          # lists, picks, repeats, then the parent
     "choices": {<list doctype>: [<record>, ...]},
     "translations": [{"language", "source_text", "translated_text", "context"}],
     "compiled_meta": {...},                      # REQUIREMENTS.md section 4.3
     "web_form": {...},
     "issues": [Issue, ...]}                      # stage 4 limits
"""

import html
import re
from dataclasses import dataclass, field

from xlsform.core.expr import emit_js, profile
from xlsform.core.expr.parser import AST_VERSION, strip_positions
from xlsform.core.form import GROUP, QUESTION, REPEAT, SELECT_TYPES, SUPPORTED_TYPES, Form, Node
from xlsform.core.issues import Issue, issue
from xlsform.core.meaning import Analysis, make_scope
from xlsform.core.naming import MAX_FIELDNAME, child_label, doctype_name, parent_label, sanitize

META_VERSION = 2
MODULE = "XLSForm Data"
CHOICES_MODULE = "XLSForm Choices"
RESERVED_PARENT_FIELDS = ("xf_form", "xf_version", "xf_channel")
LABEL_MAX = 140
LINK_LENGTH = 63
TAB_THRESHOLD = 3

FIELDTYPES = {
	"text": "Small Text",
	"integer": "Int",
	"decimal": "Float",
	"note": "HTML",
	"acknowledge": "Check",
	"date": "Date",
	"time": "Time",
	"datetime": "Datetime",
	"geopoint": "Geolocation",
	"geotrace": "Geolocation",
	"geoshape": "Geolocation",
	"image": "Attach Image",
	"audio": "Attach",
	"video": "Attach",
	"file": "Attach",
	"barcode": "Data",
	"calculate": "Small Text",
	"hidden": "Small Text",
	"start": "Datetime",
	"end": "Datetime",
	"today": "Date",
	"username": "Data",
	"select_one": "Link",
	"select_one_from_file": "Link",
	"select_multiple": "Table MultiSelect",
	"select_multiple_from_file": "Table MultiSelect",
}

ROW_BYTES = {
	"Small Text": 12,
	"Text": 12,
	"Attach": 12,
	"Attach Image": 12,
	"Geolocation": 12,
	"Int": 4,
	"Check": 4,
	"Float": 9,
	"Date": 3,
	"Time": 6,
	"Datetime": 8,
}
NO_COLUMN = {"HTML", "Section Break", "Tab Break", "Column Break", "Table", "Table MultiSelect"}
FIXED_ROW_BYTES = 3500
SHORT_TEXT_HEIGHT = "4.5rem"

WEB_FIELDTYPES = {"Table MultiSelect": "Table", "Tab Break": "Page Break", "Geolocation": None}
WEB_UNSUPPORTED_TYPES = {"geopoint", "geotrace", "geoshape"}


@dataclass
class CompileSettings:
	prefix: str = "XF"
	row_budget_bytes: int = 60000
	max_questions: int = 400
	site_language: str = "en"
	taken_doctypes: set[str] = field(default_factory=set)
	reserved_fieldnames: set[str] = field(default_factory=set)


def compile_form(
	form: Form, analysis: Analysis, previous_meta: dict | None, settings: CompileSettings
) -> dict:
	return _Compiler(form, analysis, previous_meta or {}, settings).run()


class _Compiler:
	def __init__(self, form: Form, analysis: Analysis, prev: dict, settings: CompileSettings):
		self.form = form
		self.a = analysis
		self.prev = prev
		self.s = settings
		self.by_path = form.by_path()
		self.prev_fields = {f["path"]: f for f in prev.get("fields", [])}
		self.version = form.version
		self.fields_meta: list[dict] = []
		self.taken_fieldnames: dict[str, set[str]] = {}
		self.translations: list[dict] = []
		self.issues: list[Issue] = []
		self.lang = form.default_language

	def run(self) -> dict:
		self._name_doctypes()
		lists = self._build_lists()
		picks = self._build_picks()
		self._carry_retired()
		self._assign_fieldnames()
		repeat_doctypes = []
		for repeat in [n for n in self.form.nodes() if n.kind == REPEAT]:
			dt = self.repeats[repeat.path]
			repeat_doctypes.append(
				self._doctype(dt, istable=True, fields=self._fields(repeat.children, repeat_scope=repeat))
			)
		parent_fields = self._parent_reserved() + self._fields(
			self.form.root.children, repeat_scope=None, top=True
		)
		parent = self._doctype(self.parent_dt, istable=False, fields=parent_fields)
		parent.update(
			{
				"autoname": self._autoname(),
				"naming_rule": "Expression",
				"track_changes": 1,
				"title_field": "",
				"allow_import": 1,
			}
		)
		self._append_retired_docfields([*repeat_doctypes, parent])
		self._check_limits([*repeat_doctypes, parent])

		meta = {
			"metaVersion": META_VERSION,
			"astVersion": AST_VERSION,
			"form_id": self.form.form_id,
			"version": self.version,
			"default_language": self.lang,
			"languages": self.form.languages,
			"doctypes": {
				"parent": self.parent_dt,
				"repeats": dict(self.repeats),
				"lists": dict(self.lists),
				"picks": dict(self.picks),
			},
			"fields": self.fields_meta,
			"expressions": {
				path: {col: strip_positions(ast) for col, ast in cols.items()}
				for path, cols in self.a.asts.items()
			},
			"static": self.a.static,
			"filters": {
				path: [[col, strip_positions(ast)] for col, ast in terms]
				for path, terms in self.a.filters.items()
			},
			"ranges": self.a.ranges,
			"calc_order": self.a.calc_order,
			"labels": {
				n.path: n.localized("label", self.lang)
				for n in self.form.nodes()
				if n.localized("label", self.lang)
			},
			"messages": {
				n.path: {
					k: v
					for k, v in (
						("constraint", n.localized("constraint_message", self.lang)),
						("required", n.localized("required_message", self.lang)),
					)
					if v
				}
				for n in self.form.nodes()
				if n.localized("constraint_message", self.lang) or n.localized("required_message", self.lang)
			},
			"choice_labels": {
				name: {c.name: c.labels for c in lst.choices}
				for name, lst in self.form.lists.items()
				if name in self.lists
			},
		}
		return {
			"doctypes": [*lists, *picks, *repeat_doctypes, parent],
			"choices": self.choice_records,
			"translations": self.translations,
			"compiled_meta": meta,
			"web_form": self._web_form(parent),
			"issues": self.issues,
		}

	def _name_doctypes(self) -> None:
		prev_dt = self.prev.get("doctypes", {})
		taken = set(self.s.taken_doctypes)
		form_id = self.form.form_id
		self.parent_dt = prev_dt.get("parent") or doctype_name(
			self.s.prefix, parent_label(self.form.title, form_id), taken
		)
		taken.add(self.parent_dt)
		self.repeats: dict[str, str] = {}
		for path, name in prev_dt.get("repeats", {}).items():
			self.repeats[path] = name
			taken.add(name)
		for node in self.form.nodes():
			if node.kind == REPEAT and node.path not in self.repeats:
				self.repeats[node.path] = doctype_name(self.s.prefix, child_label(form_id, node.name), taken)
		self.lists: dict[str, str] = dict(prev_dt.get("lists", {}))
		self.picks: dict[str, str] = dict(prev_dt.get("picks", {}))
		taken |= set(self.lists.values()) | set(self.picks.values())
		for node in self.form.nodes():
			if node.kind != QUESTION or node.base_type not in SELECT_TYPES:
				continue
			list_name = self._list_name(node)
			if list_name not in self.form.lists:
				continue
			if list_name not in self.lists:
				self.lists[list_name] = doctype_name(self.s.prefix, child_label(form_id, list_name), taken)
			if node.base_type.startswith("select_multiple") and list_name not in self.picks:
				self.picks[list_name] = doctype_name(
					self.s.prefix, child_label(form_id, list_name) + " pick", taken
				)

	@staticmethod
	def _list_name(node: Node) -> str:
		return node.type.file_name if node.base_type.endswith("_from_file") else node.type.list_name

	def _fieldname(self, doctype: str, node: Node) -> str:
		taken = self.taken_fieldnames.setdefault(doctype, set(RESERVED_PARENT_FIELDS))
		prev = self.prev_fields.get(node.path)
		if prev and prev.get("doctype") == doctype and not prev.get("retired_in"):
			if not self._compatible(prev, node):
				name = f"{node.name}_v{_version_slug(self.version)}"
				return sanitize(name, node.path + "@" + self.version, taken, self.s.reserved_fieldnames)
			if prev["fieldname"] not in taken:
				taken.add(prev["fieldname"])
				return prev["fieldname"]
		return sanitize(node.name, node.path, taken, self.s.reserved_fieldnames)

	def _compatible(self, prev: dict, node: Node) -> bool:
		fieldtype = self._fieldtype(node)
		if prev.get("fieldtype") != fieldtype:
			return False
		if node.base_type in SELECT_TYPES and prev.get("list") != self._list_name(node):
			return False
		return True

	def _fieldtype(self, node: Node) -> str:
		return fieldtype_for(node, self.a.ranges)

	def _build_lists(self) -> list[dict]:
		self.choice_records: dict[str, list[dict]] = {}
		self.list_lengths: dict[str, int] = {}
		self.list_columns: dict[str, dict[str, str]] = {}
		prev_lists = {k: v for k, v in self.prev.get("list_columns", {}).items()}
		prev_lengths = self.prev.get("list_lengths", {})
		out = []
		for list_name, dt in self.lists.items():
			lst = self.form.lists.get(list_name)
			columns = dict(prev_lists.get(list_name, {}))
			taken = {"choice_name", "label", "xf_order", "xf_retired"} | set(columns.values())
			if lst:
				for col in sorted({k for c in lst.choices for k in c.extra}):
					if col not in columns:
						columns[col] = sanitize(col, f"{list_name}::{col}", taken, self.s.reserved_fieldnames)
			self.list_columns[list_name] = columns
			longest = max((len(c.name) for c in lst.choices), default=1) if lst else 1
			length = max(LINK_LENGTH, longest, prev_lengths.get(list_name, 0))
			self.list_lengths[list_name] = length
			fields = [
				{
					"fieldname": "choice_name",
					"label": "Choice Name",
					"fieldtype": "Data",
					"reqd": 1,
					"unique": 1,
					"in_list_view": 1,
					"length": length,
				},
				{
					"fieldname": "label",
					"label": "Label",
					"fieldtype": "Data",
					"in_list_view": 1,
					"length": LABEL_MAX,
					"in_standard_filter": 1,
				},
				{"fieldname": "xf_order", "label": "Order", "fieldtype": "Int"},
				{
					"fieldname": "xf_retired",
					"label": "Retired",
					"fieldtype": "Check",
					"in_standard_filter": 1,
				},
			] + [
				{
					"fieldname": fn,
					"label": _plain(col)[:LABEL_MAX],
					"fieldtype": "Data",
					"in_standard_filter": 1,
				}
				for col, fn in columns.items()
			]
			out.append(
				{
					"name": dt,
					"istable": 0,
					"autoname": "field:choice_name",
					"naming_rule": "By fieldname",
					"title_field": "label",
					"show_title_field_in_link": 1,
					"translated_doctype": 1,
					"search_fields": "label",
					"sort_field": "xf_order",
					"sort_order": "ASC",
					"fields": fields,
					"module": CHOICES_MODULE,
					"xf_kind": "list",
				}
			)
			records = []
			current = set()
			if lst:
				for order, c in enumerate(lst.choices, start=1):
					label = c.labels.get(self.lang) or next(iter(c.labels.values()), "") or c.name
					record = {
						"choice_name": c.name,
						"label": _plain(label)[:LABEL_MAX],
						"xf_order": order,
						"xf_retired": 0,
					}
					for col, value in c.extra.items():
						record[columns[col]] = value
					records.append(record)
					current.add(c.name)
					for language, text in c.labels.items():
						if language != self.lang and text:
							self._translate(language, record["label"], _plain(text)[:LABEL_MAX], context=None)
			self.choice_records[dt] = records
		return out

	def _build_picks(self) -> list[dict]:
		out = []
		for list_name, dt in self.picks.items():
			out.append(
				{
					"name": dt,
					"istable": 1,
					"fields": [
						{
							"fieldname": "choice",
							"label": "Choice",
							"fieldtype": "Link",
							"options": self.lists[list_name],
							"reqd": 1,
							"in_list_view": 1,
							"length": self.list_lengths.get(list_name, LINK_LENGTH),
						},
					],
					"module": MODULE,
					"xf_kind": "pick",
				}
			)
		return out

	def _parent_reserved(self) -> list[dict]:
		return [
			{
				"fieldname": "xf_form",
				"label": "Form",
				"fieldtype": "Link",
				"options": "XLSForm",
				"read_only": 1,
				"hidden": 1,
				"set_only_once": 1,
				"length": 64,
			},
			{
				"fieldname": "xf_version",
				"label": "Form Version",
				"fieldtype": "Link",
				"options": "XLSForm Version",
				"read_only": 1,
				"hidden": 1,
				"set_only_once": 1,
				"search_index": 1,
				"length": 120,
			},
			{
				"fieldname": "xf_channel",
				"label": "Channel",
				"fieldtype": "Select",
				"options": "\nDesk\nWeb\nmForm\nAPI",
				"read_only": 1,
				"hidden": 1,
				"length": 10,
			},
		]

	def _fields(self, nodes: list[Node], repeat_scope: Node | None, top: bool = False) -> list[dict]:
		doctype = self.repeats[repeat_scope.path] if repeat_scope else self.parent_dt
		use_tabs = top and sum(1 for n in nodes if n.kind == GROUP) > TAB_THRESHOLD
		out: list[dict] = []
		self._emit_nodes(nodes, doctype, repeat_scope, out, use_tabs, inherited=[], section_prefix="")
		return out

	def _emit_nodes(self, nodes, doctype, repeat_scope, out, use_tabs, inherited, section_prefix) -> None:
		after_group = False
		for node in nodes:
			if node.kind == QUESTION and node.base_type not in SUPPORTED_TYPES:
				continue
			if node.kind == GROUP:
				own = self._relevant_js(node)
				conditions = [*inherited, *([own] if own else [])]
				label = _plain(self._label(node)) or node.name
				full = f"{section_prefix} › {label}" if section_prefix else label
				is_tab = use_tabs and not inherited and not section_prefix
				brk = {
					"fieldname": self.fieldnames[node.path],
					"label": full[:LABEL_MAX],
					"fieldtype": "Tab Break" if is_tab else "Section Break",
				}
				if conditions:
					self._set_live(brk, "depends_on", _eval_and(conditions), node, "relevant")
				out.append(brk)
				self._record_field(node, doctype, brk)
				self._translate_label(node, brk, doctype)
				self._emit_nodes(node.children, doctype, repeat_scope, out, False, conditions, full)
				after_group = True
				continue
			if after_group:
				spacer = {
					"fieldname": self._spacer_name(doctype),
					"fieldtype": "Tab Break" if use_tabs else "Section Break",
					"label": (_plain(self.form.title)[:LABEL_MAX] if use_tabs else (section_prefix or "")),
				}
				if inherited:
					self._set_live(spacer, "depends_on", _eval_and(inherited), None, "relevant")
				out.append(spacer)
				after_group = False
			if node.kind == REPEAT:
				out.append(self._table_field(node, doctype, inherited))
				continue
			out.append(self._question_field(node, doctype, inherited))

	def _break_name(self, doctype: str, node: Node) -> str:
		taken = self.taken_fieldnames.setdefault(doctype, set(RESERVED_PARENT_FIELDS))
		prev = self.prev_fields.get(node.path)
		if prev and prev.get("doctype") == doctype and prev["fieldname"] not in taken:
			taken.add(prev["fieldname"])
			return prev["fieldname"]
		base = "xf_s_" + (
			re.sub(r"[^a-z0-9_]", "", node.name.lower().replace("-", "_").replace(".", "_")) or "group"
		)
		base = base[:MAX_FIELDNAME]
		name, n = base, 2
		while name in taken:
			name = f"{base[: MAX_FIELDNAME - len(str(n)) - 1]}_{n}"
			n += 1
		taken.add(name)
		return name

	def _spacer_name(self, doctype: str) -> str:
		taken = self.taken_fieldnames.setdefault(doctype, set(RESERVED_PARENT_FIELDS))
		n = 1
		while f"xf_sb_{n}" in taken:
			n += 1
		taken.add(f"xf_sb_{n}")
		return f"xf_sb_{n}"

	def _label(self, node: Node) -> str:
		labels = node.localized("label", self.lang)
		return labels.get(self.lang) or next(iter(labels.values()), "")

	def _relevant_js(self, node: Node) -> str | None:
		ast = self.a.asts.get(node.path, {}).get("relevant")
		if not ast:
			return None
		return emit_js.emit(ast, self._scope(node))

	def _scope(self, node: Node) -> emit_js.Scope:
		return make_scope(self.form, self.a, node, fieldname=self._fieldname_of)

	def _assign_fieldnames(self) -> None:
		"""Pass 1: name every field, so a formula can refer to a question defined later."""
		self.fieldnames: dict[str, str] = {}
		for node in self.form.nodes():
			if node.kind == QUESTION and node.base_type not in SUPPORTED_TYPES:
				continue
			repeat = node.enclosing_repeat
			doctype = self.repeats[repeat.path] if repeat else self.parent_dt
			if node.kind == GROUP:
				self.fieldnames[node.path] = self._break_name(doctype, node)
			else:
				self.fieldnames[node.path] = self._fieldname(doctype, node)

	def _fieldname_of(self, path: str) -> str:
		return self.fieldnames[path]

	def _table_field(self, node: Node, doctype: str, inherited: list[str]) -> dict:
		fieldname = self.fieldnames[node.path]
		own = self._relevant_js(node)
		conditions = [*inherited, *([own] if own else [])]
		field = {
			"fieldname": fieldname,
			"label": (_plain(self._label(node)) or node.name)[:LABEL_MAX],
			"fieldtype": "Table",
			"options": self.repeats[node.path],
		}
		if conditions:
			self._set_live(field, "depends_on", _eval_and(conditions), node, "relevant")
		self._record_field(node, doctype, field)
		self._translate_label(node, field, doctype)
		return field

	def _question_field(self, node: Node, doctype: str, inherited: list[str]) -> dict:
		fieldname = self.fieldnames[node.path]
		fieldtype = self._fieldtype(node)
		label_text = _plain(self._label(node))
		field: dict = {"fieldname": fieldname, "fieldtype": fieldtype}
		label = label_text or node.name
		description_parts = []
		if len(label) > LABEL_MAX:
			description_parts.append(label)
			label = _truncate(label, LABEL_MAX)
		field["label"] = label
		hint = node.localized("hint", self.lang)
		if hint.get(self.lang):
			description_parts.append(_plain(hint[self.lang]))
		if description_parts:
			field["description"] = "\n".join(description_parts)

		qtype = node.base_type
		if qtype == "note":
			field["options"] = _note_html(self._label(node))
			field.pop("label", None) if not label_text else None
		if qtype in ("select_one", "select_one_from_file"):
			list_name = self._list_name(node)
			field["options"] = self.lists[list_name]
			field["length"] = self.list_lengths[list_name]
			filters = [[self.lists[list_name], "xf_retired", "=", 0]]
			for col, value_ast in self.a.filters.get(node.path, []):
				column = "choice_name" if col == "name" else self.list_columns[list_name].get(col, col)
				filters.append([self.lists[list_name], column, "=", self._filter_value(value_ast, node)])
			field["link_filters"] = _json(filters)
			field["in_standard_filter"] = 1
		if qtype in ("select_multiple", "select_multiple_from_file"):
			field["options"] = self.picks[self._list_name(node)]
		if qtype == "barcode":
			field["length"] = 140
		if qtype == "text" and "multiline" not in node.cell("appearance").split():
			field["max_height"] = SHORT_TEXT_HEIGHT
		if qtype in ("calculate", "start", "end", "today", "username"):
			field["read_only"] = 1
		if qtype in ("start", "end", "today", "username"):
			field["hidden"] = 1
		if qtype == "calculate" and not label_text:
			field["hidden"] = 1
		if qtype == "hidden":
			field["hidden"] = 1
		if qtype in ("integer", "decimal", "range"):
			r = self.a.ranges.get(node.path)
			if r and r.get("start", 0) >= 0 and r.get("end", 0) >= 0:
				field["non_negative"] = 1

		own = self._relevant_js(node)
		conditions = [*inherited, *([own] if own else [])]
		if conditions:
			self._set_live(field, "depends_on", _eval_and(conditions), node, "relevant")

		static = self.a.static.get(node.path, {})
		required_ast = self.a.asts.get(node.path, {}).get("required")
		if qtype not in (
			"acknowledge",
			"note",
			"calculate",
			"hidden",
			*("start", "end", "today", "username"),
		):
			if static.get("required") and not conditions:
				field["reqd"] = 1
			elif static.get("required"):
				self._set_live(field, "mandatory_depends_on", _eval_and(conditions), node, "required")
			elif required_ast:
				self._set_live(
					field,
					"mandatory_depends_on",
					_eval_and([*conditions, emit_js.emit(required_ast, self._scope(node))]),
					node,
					"required",
				)
		read_only_ast = self.a.asts.get(node.path, {}).get("read_only")
		if static.get("read_only"):
			field["read_only"] = 1
		elif read_only_ast:
			self._set_live(
				field,
				"read_only_depends_on",
				"eval:" + emit_js.emit(read_only_ast, self._scope(node)),
				node,
				"read_only",
			)

		default = self.a.defaults.get(node.path)
		if default is not None and qtype not in ("select_multiple", "select_multiple_from_file", "note"):
			if qtype == "acknowledge":
				field["default"] = "1" if default.strip().upper() == "OK" else "0"
			else:
				field["default"] = default

		if qtype not in ("note", "hidden", "calculate") and fieldtype not in ("Table MultiSelect",):
			field["in_list_view"] = 0
		self._record_field(node, doctype, field)
		self._translate_label(node, field, doctype)
		return field

	def _set_live(self, field: dict, key: str, value: str, node: Node | None, column: str) -> None:
		"""Ship an ``eval:`` property only when it is in the JavaScript profile.

		Each part was checked when emitted; this catches what joining parts can add (nesting).
		"""
		if profile.is_valid(value.removeprefix("eval:")):
			field[key] = value
			return
		where = {}
		if node is not None and node.row:
			where = dict(sheet="survey", row=node.row_number, column=column, col_index=node.col(column))
		self.issues.append(issue("E-EXPR-TOO-COMPLEX", limit=emit_js.MAX_JS_LENGTH, **where))

	def _filter_value(self, ast: dict, node: Node) -> str:
		return emit_js.filter_value(ast, self._scope(node))

	def _record_field(self, node: Node, doctype: str, field: dict) -> None:
		entry = {
			"path": node.path,
			"name": node.name,
			"kind": node.kind,
			"type": node.base_type if node.kind == QUESTION else node.kind,
			"fieldname": field["fieldname"],
			"doctype": doctype,
			"fieldtype": field["fieldtype"],
			"introduced_in": (self.prev_fields.get(node.path) or {}).get("introduced_in", self.version)
			if (self.prev_fields.get(node.path) or {}).get("fieldname") == field["fieldname"]
			else self.version,
			"retired_in": None,
		}
		if node.kind == QUESTION and node.base_type in SELECT_TYPES:
			entry["list"] = self._list_name(node)
		parent = node.parent
		entry["parent_path"] = parent.path if parent and parent.path else ""
		self.fields_meta.append(entry)

	def _carry_retired(self) -> None:
		"""Questions in the previous version but not this one keep their column, hidden."""
		self.retired = []
		current_paths = set(self.by_path)
		for path, prev in self.prev_fields.items():
			if prev.get("retired_in") or path not in current_paths:
				entry = dict(prev)
				entry["retired_in"] = prev.get("retired_in") or self.version
				self.retired.append(entry)
				self.taken_fieldnames.setdefault(prev["doctype"], set(RESERVED_PARENT_FIELDS)).add(
					prev["fieldname"]
				)
		for path, prev in self.prev_fields.items():
			if path in current_paths and not prev.get("retired_in"):
				node = self.by_path[path]
				if node.kind == QUESTION and not self._compatible(prev, node):
					entry = dict(prev)
					entry["retired_in"] = self.version
					entry["path"] = f"{path}@{prev['fieldname']}"
					self.retired.append(entry)
					self.taken_fieldnames.setdefault(prev["doctype"], set(RESERVED_PARENT_FIELDS)).add(
						prev["fieldname"]
					)

	def _append_retired_docfields(self, doctypes: list[dict]) -> None:
		"""Keep retired questions as hidden columns. Their list, pick and repeat DocTypes carry over
		from the previous meta, so a retired column keeps pointing at the same DocType."""
		by_name = {d["name"]: d for d in doctypes}
		for entry in self.retired:
			dt = by_name.get(entry["doctype"])
			if dt is None or entry["fieldtype"] in ("Section Break", "Tab Break", "Column Break"):
				self.fields_meta.append(entry)
				continue
			field = {
				"fieldname": entry["fieldname"],
				"label": entry.get("label") or entry["name"],
				"fieldtype": entry["fieldtype"],
				"hidden": 1,
				"read_only": 1,
			}
			if entry["fieldtype"] == "Link":
				field["options"] = self.lists[entry["list"]]
				field["length"] = self.list_lengths[entry["list"]]
			elif entry["fieldtype"] == "Table MultiSelect":
				field["options"] = self.picks[entry["list"]]
			elif entry["fieldtype"] == "Table":
				field["options"] = self.repeats[entry["path"].split("@")[0]]
			dt["fields"].append(field)
			self.fields_meta.append(entry)

	def _doctype(self, name: str, istable: bool, fields: list[dict]) -> dict:
		return {
			"name": name,
			"istable": 1 if istable else 0,
			"fields": fields,
			"module": MODULE,
			"xf_kind": "child" if istable else "parent",
		}

	def _autoname(self) -> str:
		parts = self.a.instance_name
		if parts:
			pieces = []
			for p in parts:
				if "lit" in p:
					text = re.sub(r"[{}]", "", p["lit"])
					pieces.append(text)
				else:
					entry = next((f for f in self.fields_meta if f["path"] == p["ref"]), None)
					if entry is None:
						return self._default_autoname()
					pieces.append("{" + entry["fieldname"] + "}")
			return "format:" + "".join(pieces) + "-{#####}"
		return self._default_autoname()

	def _default_autoname(self) -> str:
		return "format:" + self.form.form_id.upper() + "-{#####}"

	def _translate(self, language: str, source: str, translated: str, context: str | None) -> None:
		if source and translated and source != translated:
			self.translations.append(
				{
					"language": language,
					"source_text": source,
					"translated_text": translated,
					"context": context,
				}
			)

	def _translate_label(self, node: Node, field: dict, doctype: str) -> None:
		labels = node.localized("label", self.lang)
		hints = node.localized("hint", self.lang)
		source_label = field.get("label")
		source_hint = _plain(hints.get(self.lang, "")) if hints.get(self.lang) else None
		for language, text in labels.items():
			if language != self.lang and source_label:
				self._translate(language, source_label, _truncate(_plain(text), LABEL_MAX), context=doctype)
		for language, text in hints.items():
			if language != self.lang and source_hint and field.get("description") == source_hint:
				self._translate(language, source_hint, _plain(text), context=doctype)
		if node.base_type == "note" and field.get("options"):
			for language, text in labels.items():
				if language != self.lang:
					self._translate(language, field["options"], _note_html(text), context=doctype)

	def _check_limits(self, doctypes: list[dict]) -> None:
		count = question_count(self.form)
		if count > self.s.max_questions:
			self.issues.append(issue("E-LIMIT-QUESTIONS", count=count, limit=self.s.max_questions))
		for dt in doctypes:
			total = row_bytes(dt["fields"])
			if total > self.s.row_budget_bytes:
				self.issues.append(issue("E-ROW-BUDGET", bytes=total, limit=self.s.row_budget_bytes))

	def _web_form(self, parent: dict) -> dict:
		fields = []
		for f in parent["fields"]:
			if f["fieldname"] in RESERVED_PARENT_FIELDS or f.get("hidden"):
				continue
			fieldtype = WEB_FIELDTYPES.get(f["fieldtype"], f["fieldtype"])
			if fieldtype is None:
				continue
			wf = {
				k: f[k]
				for k in (
					"fieldname",
					"label",
					"options",
					"reqd",
					"depends_on",
					"mandatory_depends_on",
					"read_only",
					"read_only_depends_on",
					"description",
					"default",
				)
				if k in f and f[k] not in (None, "")
			}
			wf["fieldtype"] = fieldtype
			fields.append(wf)
		short = [f["fieldname"] for f in parent["fields"] if f.get("max_height") and not f.get("hidden")]
		css = (
			", ".join(f'.web-form textarea[data-fieldname="{fn}"]' for fn in short)
			+ f" {{ height: {SHORT_TEXT_HEIGHT}; min-height: {SHORT_TEXT_HEIGHT}; }}"
			if short
			else ""
		)
		return {
			"title": _plain(self.form.title)[:LABEL_MAX],
			"route": "xf/" + self.form.form_id.replace("_", "-"),
			"doc_type": self.parent_dt,
			"fields": fields,
			"custom_css": css,
		}


def question_count(form: Form) -> int:
	"""Questions that become fields, as counted for E-LIMIT-QUESTIONS."""
	return sum(1 for n in form.nodes() if n.kind == QUESTION and n.base_type in SUPPORTED_TYPES)


def fieldtype_for(node: Node, ranges: dict) -> str:
	if node.kind == REPEAT:
		return "Table"
	if node.kind == GROUP:
		return "Section Break"
	if node.base_type == "range":
		r = ranges.get(node.path, {})
		ints = all(float(v).is_integer() for v in r.values())
		return "Int" if ints else "Float"
	return FIELDTYPES.get(node.base_type, "Small Text")


def row_bytes(fields: list[dict]) -> int:
	total = FIXED_ROW_BYTES
	for f in fields:
		ft = f["fieldtype"]
		if ft in NO_COLUMN:
			continue
		if ft in ("Data", "Link", "Select"):
			total += 4 * int(f.get("length") or 140) + 2
		else:
			total += ROW_BYTES.get(ft, 12)
	return total


def _eval_and(conditions: list[str]) -> str:
	if len(conditions) == 1:
		return "eval:" + conditions[0]
	return "eval:(" + " && ".join(conditions) + ")"


def _json(value) -> str:
	import json

	return json.dumps(value, ensure_ascii=False)


def _version_slug(version: str) -> str:
	return re.sub(r"[^a-z0-9]", "", (version or "new").lower()) or "new"


MD_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
MD_ITALIC = re.compile(r"(?<![*_])[*_](?![*_\s])(.+?)(?<![*_\s])[*_](?![*_])")
TAGS = re.compile(r"<[^>]*>")


def _plain(text: str) -> str:
	"""Label text without markdown markers or HTML tags (Frappe escapes nothing for us)."""
	if not text:
		return ""
	text = TAGS.sub("", text)
	text = MD_BOLD.sub(lambda m: m.group(1) or m.group(2), text)
	text = MD_ITALIC.sub(lambda m: m.group(1), text)
	text = html.unescape(text)
	return html.escape(" ".join(text.split()), quote=False)


def _note_html(text: str) -> str:
	"""Safe HTML for a note: escape everything, then allow **bold**, *italic* and line breaks."""
	if not text:
		return ""
	safe = html.escape(TAGS.sub("", html.unescape(text)), quote=True)
	safe = MD_BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", safe)
	safe = MD_ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", safe)
	return "<p>" + safe.replace("\n", "<br>") + "</p>"


def _truncate(text: str, limit: int) -> str:
	if len(text) <= limit:
		return text
	cut = text[: limit - 1]
	if " " in cut[limit // 2 :]:
		cut = cut[: cut.rindex(" ")]
	return cut.rstrip() + "…"
