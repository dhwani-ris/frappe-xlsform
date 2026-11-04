"""The annotated copy of the designer's own workbook (REQUIREMENTS.md section 7).

Designers live in Excel, so this is the main fixing workflow: every cell with a problem is
filled red (error), amber (warning) or blue (advice) and carries the message as a cell
comment, and an ``xlsform_report`` sheet lists every issue in order.
"""

import io

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

from xlsform.core.i18n import N_, tr
from xlsform.core.issues import ERROR, INFO, WARNING, Issue

FILLS = {
	ERROR: PatternFill("solid", fgColor="FFC7CE"),
	WARNING: PatternFill("solid", fgColor="FFEB9C"),
	INFO: PatternFill("solid", fgColor="DDEBF7"),
}
RANK = {INFO: 0, WARNING: 1, ERROR: 2}
REPORT_SHEET = "xlsform_report"
AUTHOR = "XLSForm for Frappe"


def annotate(content: bytes, issues: list[Issue], proposed_version: str | None = None) -> bytes:
	wb = load_workbook(io.BytesIO(content), keep_vba=False, keep_links=False)
	sheets = {ws.title.strip().lower(): ws for ws in wb.worksheets}
	marked: dict[tuple[str, str], str] = {}
	for i in issues:
		ws = sheets.get((i.sheet or "").lower())
		if ws is None or not i.row:
			continue
		ref = i.cell or f"A{i.row}"
		cell = ws[ref]
		key = (ws.title, ref)
		best = marked.get(key)
		if best is None or RANK[i.severity] > RANK[best]:
			cell.fill = FILLS[i.severity]
			marked[key] = i.severity
		text = f"[{i.code}] {i.message}\n→ {i.suggestion}"
		if cell.comment is not None and cell.comment.author == AUTHOR:
			text = cell.comment.text + "\n\n" + text
		comment = Comment(text, AUTHOR)
		comment.width = 360
		comment.height = 160
		cell.comment = comment

	if proposed_version:
		ws = sheets.get("settings")
		if ws is None:
			ws = wb.create_sheet("settings")
		col = None
		for c in ws[1]:
			if str(c.value or "").strip().lower() == "version":
				col = c.column
		if col is None:
			col = ws.max_column + 1 if ws.max_column and ws["A1"].value else 1
			ws.cell(row=1, column=col, value="version")
		ws.cell(row=2, column=col, value=proposed_version)

	if REPORT_SHEET in wb.sheetnames:
		del wb[REPORT_SHEET]
	report = wb.create_sheet(REPORT_SHEET)
	headers = [
		tr(N_("Severity")),
		tr(N_("Code")),
		tr(N_("Where")),
		tr(N_("Problem")),
		tr(N_("Suggested fix")),
	]
	report.append(headers)
	for c in report[1]:
		c.font = Font(bold=True)
	for i in issues:
		where = (
			f"{i.sheet}!{i.cell}"
			if i.sheet and i.cell
			else (f"{i.sheet} row {i.row}" if i.sheet and i.row else "")
		)
		report.append([i.severity, i.code, where, i.message, i.suggestion])
		report.cell(row=report.max_row, column=1).fill = FILLS[i.severity]
	for col, width in zip("ABCDE", (10, 22, 16, 80, 60), strict=True):
		report.column_dimensions[col].width = width

	buf = io.BytesIO()
	wb.save(buf)
	return buf.getvalue()
