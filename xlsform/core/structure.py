"""Stage 2: required sheets and columns, names, and begin/end matching (REQUIREMENTS.md section 7).

Builds the :class:`~xlsform.core.form.Form` tree. When this stage reports an error the
tree can't be trusted, so later stages are skipped (the report says so).
"""

import re

from xlsform.core.form import (
	DEFAULT_LANGUAGE,
	GROUP,
	QUESTION,
	REPEAT,
	Choice,
	ChoiceList,
	Form,
	Node,
	TypeInfo,
	language_name,
	parse_type,
)
from xlsform.core.i18n import N_, tr
from xlsform.core.issues import ERROR, Issue, issue
from xlsform.core.reader import Row, Sheet, Workbook
from xlsform.core.suggest import closest, slug

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")

SURVEY_COLUMNS = {
	"type",
	"name",
	"label",
	"hint",
	"required",
	"required_message",
	"relevant",
	"constraint",
	"constraint_message",
	"calculation",
	"default",
	"read_only",
	"choice_filter",
	"appearance",
	"repeat_count",
	"parameters",
}
LOCALIZED = {"label", "hint", "constraint_message", "required_message"}
IGNORED_PREFIXES = ("media::", "body::", "guidance_hint")
IGNORED_COLUMNS = {"guidance_hint", "autoplay", "intent", "note", "comments", "comment"}
UNSUPPORTED_PREFIXES = ("bind::", "instance::")
UNSUPPORTED_COLUMNS = {"trigger"}

CHOICE_COLUMNS = {"list_name", "name", "label"}


def build_form(wb: Workbook, filename: str = "") -> tuple[Form | None, list[Issue]]:
	issues: list[Issue] = []
	survey = wb.sheet("survey")
	if survey is None:
		return None, [issue("E-SHEET-MISSING", sheet_name="survey", sheet="survey", purpose="questions")]
	issues += _check_survey_columns(survey)
	if any(i.code == "E-COL-MISSING" for i in issues):
		return None, issues

	settings, settings_cols = _read_settings(wb.sheet("settings"))
	if not settings.get("form_id"):
		# pyxform's rule: no form_id means the file name. Keep it a valid form ID.
		default = slug(_stem(filename))[:41] or "form"
		settings["form_id"] = default if len(default) >= 3 else f"{default}_form"
	default_language = language_name(settings.get("default_language", "")) or DEFAULT_LANGUAGE

	choices_sheet = wb.sheet("choices")
	lists: dict[str, ChoiceList] = {}
	choice_columns: set[str] = set()
	if choices_sheet is not None:
		col_issues = _check_choice_columns(choices_sheet)
		issues += col_issues
		if not any(i.severity == ERROR for i in col_issues):
			lists, choice_columns = _read_choices(choices_sheet, default_language)

	root = Node(GROUP, "", TypeInfo("begin_group"), None)
	stack: list[Node] = [root]
	for row in survey.rows:
		raw_type = row.get("type")
		if not raw_type:
			if row.get("name"):
				issues.append(
					issue(
						"E-TYPE-UNKNOWN",
						sheet="survey",
						row=row.number,
						column="type",
						col_index=survey.column_index("type"),
						type="",
						hint=tr(
							N_("Add a question type for {name} in the type column."), name=row.get("name")
						),
					)
				)
			continue
		info = parse_type(raw_type)
		if info.base in ("end_group", "end_repeat"):
			_close(stack, info.base, row, survey, issues)
			continue
		name = row.get("name")
		kind = {"begin_group": GROUP, "begin_repeat": REPEAT}.get(info.base, QUESTION)
		node = Node(kind, name, info, row, parent=stack[-1])
		stack[-1].children.append(node)
		if kind != QUESTION:
			stack.append(node)
	for open_node in reversed(stack[1:]):
		kind = "repeat" if open_node.kind == REPEAT else "group"
		issues.append(
			issue(
				"E-GROUP-UNCLOSED",
				sheet="survey",
				row=open_node.row_number,
				column="type",
				col_index=survey.column_index("type"),
				kind=kind,
				name=open_node.name,
				end=f"end_{kind}",
			)
		)

	issues += _check_names(root, survey)

	languages = sorted(
		{default_language}
		| {
			language_name(key.split("::", 1)[1])
			for _c, _r, key in survey.headers
			if "::" in key and key.split("::", 1)[0] in LOCALIZED
		}
		| (
			{
				language_name(key.split("::", 1)[1])
				for _c, _r, key in choices_sheet.headers
				if key.startswith("label::")
			}
			if choices_sheet
			else set()
		)
	)
	form = Form(
		root=root,
		lists=lists,
		settings=settings,
		settings_cols=settings_cols,
		default_language=default_language,
		languages=languages,
		choice_columns=choice_columns,
	)
	return form, issues


def _stem(filename: str) -> str:
	name = (filename or "").rsplit("/", 1)[-1]
	return name.rsplit(".", 1)[0] if "." in name else name


def _check_survey_columns(sheet: Sheet) -> list[Issue]:
	issues = []
	for required in ("type", "name"):
		if not sheet.has_column(required):
			issues.append(issue("E-COL-MISSING", sheet="survey", row=1, sheet_name="survey", column=required))
	known = SURVEY_COLUMNS
	for col, raw, norm in sheet.headers:
		base = norm.split("::", 1)[0]
		if norm in known or (base in LOCALIZED and "::" in norm):
			continue
		where = dict(sheet="survey", row=1, column=raw, col_index=col)
		if norm in UNSUPPORTED_COLUMNS or norm.startswith(UNSUPPORTED_PREFIXES):
			issues.append(issue("E-COL-UNSUPPORTED", **where))
		elif norm in IGNORED_COLUMNS or norm.startswith(IGNORED_PREFIXES):
			issues.append(issue("W-COL-IGNORED", **where))
		else:
			guess = closest(norm, known)
			hint = (
				tr(N_('Did you mean "{guess}"?'), guess=guess)
				if guess
				else tr(N_("Remove the column if you don't need it."))
			)
			issues.append(issue("W-COL-UNKNOWN", hint=hint, **where))
	return issues


def _check_choice_columns(sheet: Sheet) -> list[Issue]:
	issues = []
	for required in ("list_name", "name"):
		if not sheet.has_column(required):
			issues.append(
				issue("E-COL-MISSING", sheet="choices", row=1, sheet_name="choices", column=required)
			)
	return issues


def _read_settings(sheet: Sheet | None) -> tuple[dict[str, str], dict[str, int]]:
	if sheet is None or not sheet.rows:
		return {}, {}
	row = sheet.rows[0]
	return (
		{k: c.value for k, c in row.cells.items()},
		{k: c.col for k, c in row.cells.items()} | {"__row__": row.number},
	)


def _read_choices(sheet: Sheet, default_language: str) -> tuple[dict[str, ChoiceList], set[str]]:
	lists: dict[str, ChoiceList] = {}
	extra_columns = {
		norm
		for _c, _r, norm in sheet.headers
		if norm not in CHOICE_COLUMNS and not norm.startswith(("label::", "media::"))
	}
	for row in sheet.rows:
		list_name = row.get("list_name")
		if not list_name:
			continue
		lst = lists.setdefault(list_name, ChoiceList(list_name, row=row.number))
		labels = {}
		for key, cell in row.cells.items():
			if key == "label":
				labels[default_language] = cell.value
			elif key.startswith("label::"):
				labels[language_name(key.split("::", 1)[1])] = cell.value
		extra = {k: row.get(k) for k in extra_columns if row.get(k)}
		lst.choices.append(Choice(row.get("name"), labels, extra, row))
	return lists, extra_columns


def _close(stack: list[Node], end_type: str, row: Row, sheet: Sheet, issues: list[Issue]) -> None:
	closing = "repeat" if end_type == "end_repeat" else "group"
	where = dict(sheet="survey", row=row.number, column="type", col_index=sheet.column_index("type"))
	if len(stack) == 1:
		issues.append(issue("E-GROUP-EXTRA-END", kind=closing, **where))
		return
	top = stack[-1]
	open_kind = "repeat" if top.kind == REPEAT else "group"
	if open_kind != closing:
		issues.append(
			issue(
				"E-GROUP-MISMATCH",
				closing=closing,
				open_kind=open_kind,
				open_row=top.row_number,
				expected=f"end_{open_kind}",
				closing_end=f"begin_{closing}",
				**where,
			)
		)
	top.end_row = row.number
	stack.pop()


def _check_names(root: Node, sheet: Sheet) -> list[Issue]:
	issues = []
	seen: dict[str, list[int]] = {}
	name_col = sheet.column_index("name")
	for node in root.walk():
		if node is root:
			continue
		where = dict(sheet="survey", row=node.row_number, column="name", col_index=name_col)
		if not node.name:
			example = slug(node.cell("label")) if node.cell("label") else "hh_size"
			issues.append(issue("E-NAME-MISSING", example=example, **where))
			continue
		if not NAME_RE.match(node.name) or node.name.lower().startswith("xml"):
			reason = _name_problem(node.name)
			issues.append(
				issue("E-NAME-INVALID", name=node.name, reason=reason, fixed=slug(node.name), **where)
			)
			continue
		seen.setdefault(node.name, []).append(node.row_number)
	for name, rows in seen.items():
		if len(rows) > 1:
			issues.append(
				issue(
					"E-NAME-DUPLICATE",
					sheet="survey",
					row=rows[1],
					column="name",
					col_index=name_col,
					name=name,
					rows=" and ".join(str(r) for r in rows),
					example=f"{name}_2",
				)
			)
	return issues


def _name_problem(name: str) -> str:
	if " " in name:
		return tr(N_("names can't contain spaces"))
	if name[0].isdigit():
		return tr(N_("names can't start with a number"))
	if name.lower().startswith("xml"):
		return tr(N_('names can\'t start with "xml"'))
	return tr(N_("names can only use letters, numbers, _ . and -"))
