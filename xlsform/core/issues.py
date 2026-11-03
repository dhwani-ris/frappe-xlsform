"""Issue objects and the v1 issue catalogue (REQUIREMENTS.md section 7).

Every problem the validator reports is an :class:`Issue` built from a catalogue entry,
so codes, severities and wording live in exactly one place. Messages are written in the
designer's terms (question, choice list, formula), never Frappe or Python terms.
"""

from dataclasses import asdict, dataclass, field

from xlsform.core.i18n import N_, translate

ERROR = "error"
WARNING = "warning"
INFO = "info"

DOCS_BASE = "/xlsform-docs/errors"


@dataclass(frozen=True)
class Entry:
	code: str
	severity: str
	stage: int
	message: str
	suggestion: str


def _e(code: str, stage: int, message: str, suggestion: str) -> Entry:
	severity = {"E": ERROR, "W": WARNING, "I": INFO}[code[0]]
	return Entry(code, severity, stage, message, suggestion)


CATALOGUE: dict[str, Entry] = {
	e.code: e
	for e in [
		# Stage 1: file
		_e(
			"E-FILE-TYPE",
			1,
			N_("This file is not an Excel workbook (.xlsx)."),
			N_("Save it as .xlsx from Excel or Google Sheets and upload again."),
		),
		_e(
			"E-FILE-SIZE",
			1,
			N_("The file is {size_mb} MB; the limit is {limit_mb} MB."),
			N_("Remove embedded images or unused sheets."),
		),
		_e(
			"E-FILE-PROTECTED",
			1,
			N_("The workbook is password-protected, so it can't be read."),
			N_("Remove the password and upload again."),
		),
		_e(
			"E-FILE-UNREADABLE",
			1,
			N_("The workbook can't be opened; it may be damaged."),
			N_("Open it in Excel, save it again as .xlsx and upload the new file."),
		),
		_e(
			"E-SHEET-MISSING",
			1,
			N_('The workbook has no "{sheet_name}" sheet.'),
			N_('Rename your {purpose} sheet to "{sheet_name}" (lower case).'),
		),
		# Stage 2: structure
		_e(
			"E-COL-MISSING",
			2,
			N_('The {sheet_name} sheet has no "{column}" column.'),
			N_("Add a column named {column} in row 1."),
		),
		_e(
			"W-COL-UNKNOWN",
			2,
			N_('Column "{column}" isn\'t recognised and will be ignored.'),
			N_("{hint}"),
		),
		_e(
			"W-COL-IGNORED",
			2,
			N_('Column "{column}" isn\'t supported yet and will be ignored.'),
			N_("Remove it, or keep it for use in ODK."),
		),
		_e(
			"E-COL-UNSUPPORTED",
			2,
			N_('Column "{column}" isn\'t supported.'),
			N_("Remove the column; it changes how answers are stored, so it can't be ignored."),
		),
		_e(
			"E-NAME-MISSING",
			2,
			N_("Row {row} has a question type but no name."),
			N_("Add a short name, e.g. {example}."),
		),
		_e(
			"E-NAME-INVALID",
			2,
			N_('"{name}" can\'t be used as a name: {reason}.'),
			N_("Use {fixed}."),
		),
		_e(
			"E-NAME-DUPLICATE",
			2,
			N_("The name {name} is used in rows {rows}."),
			N_("Rename one, e.g. {example}."),
		),
		_e(
			"E-GROUP-UNCLOSED",
			2,
			N_("The {kind} started in row {row} ({name}) is never closed."),
			N_("Add an {end} row where the {kind} should end."),
		),
		_e(
			"E-GROUP-MISMATCH",
			2,
			N_("Row {row} closes a {closing}, but the open block is a {open_kind} started in row {open_row}."),
			N_("Change row {row} to {expected}, or add the missing {closing_end}."),
		),
		_e(
			"E-GROUP-EXTRA-END",
			2,
			N_("Row {row} closes a {kind} that was never opened."),
			N_("Delete row {row}, or add the matching begin row above it."),
		),
		# Stage 3: meaning
		_e(
			"E-TYPE-UNKNOWN",
			3,
			N_('"{type}" isn\'t a question type.'),
			N_("{hint}"),
		),
		_e(
			"E-TYPE-UNSUPPORTED",
			3,
			N_('"{type}" questions aren\'t supported yet (row {row}).'),
			N_("See the supported list in the docs{alternative}."),
		),
		_e(
			"W-META-IGNORED",
			3,
			N_('"{type}" (row {row}) can\'t be collected in this app and will be ignored.'),
			N_("Remove the row, or keep it for use in ODK."),
		),
		_e(
			"E-LIST-MISSING",
			3,
			N_('Row {row} uses choice list "{list}", but the choices sheet has no list with that name.'),
			N_("{hint}"),
		),
		_e(
			"E-LIST-EMPTY",
			3,
			N_('Choice list "{list}" has no choices.'),
			N_("Add choices for it on the choices sheet."),
		),
		_e(
			"E-CHOICE-DUPLICATE",
			3,
			N_('Choice "{choice}" appears twice in list "{list}" (choices rows {rows}).'),
			N_("Remove or rename one."),
		),
		_e(
			"E-CHOICE-NAME",
			3,
			N_('Choice name "{choice}" in list "{list}" {reason}.'),
			N_("Use {fixed}; the label can keep any text."),
		),
		_e(
			"E-LIST-TOO-LARGE",
			3,
			N_('Choice list "{list}" has {count} choices; the limit is {limit}.'),
			N_(
				"Split it with a cascading filter (district, then village), or ask your administrator about larger lists."
			),
		),
		_e(
			"E-FILE-CSV-MISSING",
			3,
			N_("Row {row} uses {file}, which wasn't uploaded with the form."),
			N_("Upload {file} together with the workbook."),
		),
		_e(
			"E-REPEAT-NESTED",
			3,
			N_(
				"Repeat {inner} (row {inner_row}) is inside repeat {outer} (row {outer_row}); repeats inside repeats aren't supported yet."
			),
			N_("Move {inner} out, or flatten it into the outer repeat."),
		),
		_e(
			"E-REPEAT-EMPTY",
			3,
			N_("Repeat {name} (row {row}) has no questions."),
			N_("Add questions between begin_repeat and end_repeat, or remove the repeat."),
		),
		_e(
			"E-REF-UNKNOWN",
			3,
			N_("The formula refers to ${{{name}}}, which isn't a question in this form."),
			N_("{hint}"),
		),
		_e(
			"E-REF-SELF",
			3,
			N_("The {column} of {name} refers to its own name; use . for \"this answer\"."),
			N_("Replace ${{{name}}} with ."),
		),
		_e(
			"E-REF-REPEAT",
			3,
			N_("Row {row} (outside repeat {repeat}) uses ${{{name}}} without count() or sum()."),
			N_("Wrap it, e.g. sum(${{{name}}})."),
		),
		_e(
			"E-EXPR-SYNTAX",
			3,
			N_("The formula can't be read: {reason}."),
			N_("Check the formula: {expr}"),
		),
		_e(
			"E-EXPR-QUOTE",
			3,
			N_("The formula uses curly quotes (‘ ’ or “ ”), which formulas don't accept."),
			N_("Replace them with straight quotes (' or \")."),
		),
		_e(
			"E-EXPR-TOO-LONG",
			3,
			N_("The formula is {length} characters long; the limit is {limit}."),
			N_("Split it into calculate questions."),
		),
		_e(
			"E-FN-UNSUPPORTED",
			3,
			N_("{fn}() isn't supported yet."),
			N_("See the supported function list in the docs."),
		),
		_e(
			"E-FN-ARGS",
			3,
			N_("{fn}() needs {expected} but got {got}."),
			N_("Example: {example}"),
		),
		_e(
			"E-EXPR-NOT-LIVE",
			3,
			N_(
				'{what} can\'t be used in "{column}": this rule is checked while the form is being filled, offline too.'
			),
			N_("Use a simpler condition here, or move the check into a constraint, which is checked on save."),
		),
		_e(
			"E-CALC-NOT-LIVE",
			3,
			N_('"{column}" uses {name}, whose calculation can only run when the form is saved.'),
			N_("Write the condition without {name}, or simplify its calculation."),
		),
		_e(
			"E-CALC-CYCLE",
			3,
			N_("These calculations depend on each other in a loop: {cycle}."),
			N_("Break the loop so one of them doesn't use the other."),
		),
		_e(
			"E-FILTER-UNSUPPORTED",
			3,
			N_("This choice_filter can't be applied: {reason}."),
			N_("Use conditions like district = ${{district}}, joined by and."),
		),
		_e(
			"E-FILTER-COLUMN",
			3,
			N_('choice_filter uses column "{choice_column}", which isn\'t on the choices sheet for list "{list}".'),
			N_('Add a "{choice_column}" column to the choices sheet.'),
		),
		_e(
			"E-FILTER-MULTI",
			3,
			N_("choice_filter on select_multiple questions isn't supported yet (row {row})."),
			N_("Use select_one, or remove the filter."),
		),
		_e(
			"W-WEB-FILTER",
			3,
			N_(
				"On the web form, {name} will list all choices of \"{list}\"; answers that don't match the filter are rejected when saved."
			),
			N_("No change needed; the filter works on Desk and mForm."),
		),
		_e(
			"E-DEFAULT-DYNAMIC",
			3,
			N_('The default "{value}" can\'t be used; defaults must be fixed values, today() or now().'),
			N_("Use a fixed value, or a calculate question."),
		),
		_e(
			"W-APPEARANCE",
			3,
			N_('Appearance "{appearance}" (row {row}) isn\'t supported and will be ignored.'),
			N_("Remove it, or keep it for use in ODK."),
		),
		_e(
			"W-PARAMETER",
			3,
			N_('Parameter "{parameter}" (row {row}) isn\'t supported and will be ignored.'),
			N_("Remove it, or keep it for use in ODK."),
		),
		_e(
			"E-PARAMETER-INVALID",
			3,
			N_('Parameter "{parameter}" (row {row}) has the value "{value}", which isn\'t a number.'),
			N_("Use a number, e.g. {parameter}=10."),
		),
		_e(
			"E-SETTING-INVALID",
			3,
			N_('The setting {setting} = "{value}" isn\'t valid: {reason}.'),
			N_("{hint}"),
		),
		_e(
			"E-SETTING-ENCRYPTED",
			3,
			N_("Encrypted forms (public_key) aren't supported."),
			N_("Remove the public_key setting."),
		),
		_e(
			"W-SETTING-IGNORED",
			3,
			N_('The setting "{setting}" is ignored by this app.'),
			N_("Remove it, or keep it for use in ODK."),
		),
		_e(
			"W-INSTANCE-NAME",
			3,
			N_("instance_name can only combine questions and fixed text with concat(); it will be ignored."),
			N_("Example: concat(${{village}}, '-', ${{hh_head}})"),
		),
		_e(
			"E-VERSION-ORDER",
			3,
			N_('Version "{version}" is not newer than the published version "{published}".'),
			N_("Set a higher value in the version setting."),
		),
		_e(
			"E-VERSION-PUBLISHED",
			3,
			N_('Version "{version}" of this form is already published.'),
			N_("Set a new, higher version in the settings sheet."),
		),
		# Stage 4: Frappe limits
		_e(
			"E-LIMIT-QUESTIONS",
			4,
			N_("The form has {count} questions; the limit is {limit}."),
			N_("Split it into two forms, or ask your administrator to raise the limit."),
		),
		_e(
			"E-ROW-BUDGET",
			4,
			N_(
				"The form has too many short-answer questions outside repeats to store in one record ({bytes} of {limit} bytes)."
			),
			N_("Move some into a repeat, or shorten long choice names."),
		),
		# Stage 5: version diff
		_e(
			"W-RENAME",
			5,
			N_("{old} was removed and {new} added; existing answers to {old} won't move to the new question."),
			N_("Keep the old name if it's the same question."),
		),
		_e(
			"W-MOVE-REPEAT",
			5,
			N_("{name} moved {direction} repeat {repeat}; existing answers won't move."),
			N_("Confirm this is intended."),
		),
		_e(
			"W-TYPE-CHANGE",
			5,
			N_("{name} changed from {old} to {new}; earlier answers stay in the old column."),
			N_("Confirm this is intended."),
		),
		_e(
			"W-REMOVED",
			5,
			N_("{name} was removed; its earlier answers are kept but no longer shown on the form."),
			N_("Confirm this is intended."),
		),
		# Info
		_e(
			"I-NO-LABEL",
			3,
			N_("Row {row} ({name}) has no label, so collectors will see only its name."),
			N_("Add a label."),
		),
	]
}


@dataclass
class Issue:
	code: str
	severity: str
	sheet: str | None = None
	row: int | None = None
	column: str | None = None
	cell: str | None = None
	params: dict = field(default_factory=dict)

	@property
	def entry(self) -> Entry:
		return CATALOGUE[self.code]

	@property
	def message(self) -> str:
		text = _render(self.entry.message, self.params)
		if self.sheet and self.cell:
			return f"{self.sheet}!{self.cell}: {text}"
		return text

	@property
	def suggestion(self) -> str:
		return _render(self.entry.suggestion, self.params)

	@property
	def docs_url(self) -> str:
		return f"{DOCS_BASE}#{self.code}"

	def as_dict(self) -> dict:
		data = asdict(self)
		data.pop("params")
		data["message"] = self.message
		data["suggestion"] = self.suggestion
		data["docs_url"] = self.docs_url
		return data


class _SafeDict(dict):
	def __missing__(self, key):
		return "{" + key + "}"


def _render(template: str, params: dict) -> str:
	return translate(template).format_map(_SafeDict({k: _fmt(v) for k, v in params.items()}))


def _fmt(value) -> str:
	if isinstance(value, int) and not isinstance(value, bool):
		return f"{value:,}"
	if isinstance(value, list | tuple):
		return ", ".join(str(v) for v in value)
	return "" if value is None else str(value)


def issue(code: str, *, sheet=None, row=None, column=None, col_index=None, **params) -> Issue:
	"""Build an issue from the catalogue. ``col_index`` is 1-based and yields the cell ref."""
	if code not in CATALOGUE:
		raise KeyError(f"Unknown issue code {code}")
	cell = f"{column_letter(col_index)}{row}" if (col_index and row) else None
	if row is not None:
		params.setdefault("row", row)
	if column is not None:
		params.setdefault("column", column)
	return Issue(code, CATALOGUE[code].severity, sheet, row, column, cell, params)


def column_letter(index: int) -> str:
	letters = ""
	while index:
		index, rem = divmod(index - 1, 26)
		letters = chr(65 + rem) + letters
	return letters


def counts(issues: list[Issue]) -> dict[str, int]:
	out = {ERROR: 0, WARNING: 0, INFO: 0}
	for i in issues:
		out[i.severity] += 1
	return out


def sort_key(i: Issue):
	order = {"settings": 0, "survey": 1, "choices": 2}
	return (order.get(i.sheet or "", -1), i.row or 0, i.column or "", i.code)
