"""Validate an uploaded workbook on a site and store the results on its XLSForm Version."""

import hashlib
import html
import json

import frappe
from frappe import _
from frappe.model.document import RESERVED_KEYWORDS, Document

import xlsform.runtime
from xlsform.core import preview
from xlsform.core.issues import ERROR, INFO, WARNING, Issue
from xlsform.core.validate import Result, ValidateOptions, validate
from xlsform.runtime import ownership
from xlsform.runtime import settings as xf_settings

ASYNC_BYTES = 1024 * 1024


def reserved_fieldnames() -> set[str]:
	doc = frappe.new_doc("ToDo")
	names = {x for x in dir(doc) if isinstance(x, str)}
	return names | set(RESERVED_KEYWORDS) | {f for f in dir(Document)}


def taken_doctypes(own: set[str], form: str | None = None) -> set[str]:
	names = set(frappe.get_all("DocType", pluck="name"))
	return names - own - leftover_doctypes(form)


def leftover_doctypes(form: str | None) -> set[str]:
	"""DocTypes an earlier, failed publish of this form created (MariaDB DDL can't be rolled
	back). Treating them as the form's own lets the next publish reuse them instead of
	creating "XF Survey 2"."""
	return ownership.owned(form)


def own_doctypes(meta: dict | None) -> set[str]:
	if not meta:
		return set()
	d = meta.get("doctypes", {})
	return (
		{d.get("parent")}
		| set(d.get("repeats", {}).values())
		| set(d.get("lists", {}).values())
		| set(d.get("picks", {}).values())
	)


def published_meta(form: str | None) -> tuple[dict | None, str | None]:
	if not form or not frappe.db.exists("XLSForm", form):
		return None, None
	current = frappe.db.get_value("XLSForm", form, "current_version")
	if not current:
		return None, None
	meta, version = frappe.db.get_value("XLSForm Version", current, ["compiled_meta", "version"])
	return (json.loads(meta) if isinstance(meta, str) else meta), version


def options(form: str | None, files: dict[str, bytes], allow_web: bool = True) -> ValidateOptions:
	s = xf_settings.get()
	prev, published_version = published_meta(form)
	return ValidateOptions(
		max_upload_mb=s.max_upload_mb,
		max_questions=s.max_questions,
		max_choices_per_list=s.max_choices_per_list,
		max_expression_length=s.max_expression_length,
		row_budget_bytes=s.row_budget_bytes,
		columns=frappe.utils.cint(s.columns_per_section) or 1,
		prefix=s.doctype_prefix,
		published_version=published_version,
		previous_meta=prev,
		files=files,
		allow_web=allow_web,
		taken_doctypes=taken_doctypes(own_doctypes(prev), form),
		reserved_fieldnames=reserved_fieldnames(),
	)


def file_content(file_url: str) -> tuple[bytes, str]:
	"""Content of a file the app itself stored, such as a version's source workbook."""
	file = frappe.get_doc("File", {"file_url": file_url})
	return _as_bytes(file.get_content()), file.file_name


def readable_file_content(file_url: str) -> tuple[bytes, str]:
	"""Content of a file named by the caller, only if the caller may download it."""
	from frappe.core.doctype.file.utils import find_file_by_url

	file = find_file_by_url(file_url) if isinstance(file_url, str) and file_url else None
	if not file:
		frappe.throw(_("You don't have access to the file {0}.").format(file_url), frappe.PermissionError)
	return _as_bytes(file.get_content()), file.file_name


def _as_bytes(content: bytes | str) -> bytes:
	return content.encode() if isinstance(content, str) else content


def csv_attachments(version_name: str) -> dict[str, bytes]:
	files = {}
	for f in frappe.get_all(
		"File",
		filters={"attached_to_doctype": "XLSForm Version", "attached_to_name": version_name},
		fields=["name", "file_name"],
	):
		if (f.file_name or "").lower().endswith(".csv"):
			files[f.file_name] = _as_bytes(frappe.get_doc("File", f.name).get_content())
	return files


def sha256(content: bytes) -> str:
	return hashlib.sha256(content).hexdigest()


def run_for_version(version: Document) -> Result:
	"""Validate ``version.source_file`` and write every result field (doc is not saved)."""
	content, filename = file_content(version.source_file)
	allow_web = bool(frappe.db.get_value("XLSForm", version.form, "allow_web")) if version.form else True
	result = validate(content, filename, options(version.form, csv_attachments(version.name), allow_web))
	store(version, result, sha256(content))
	return result


def store(version: Document, result: Result, source_hash: str) -> None:
	counts = {ERROR: 0, WARNING: 0, INFO: 0}
	for i in result.issues:
		counts[i.severity] += 1
	version.source_hash = source_hash
	version.error_count = counts[ERROR]
	version.warning_count = counts[WARNING]
	version.info_count = counts[INFO]
	version.state = "Valid" if result.ok else "Invalid"
	version.validation_report = json.dumps(result.report(), ensure_ascii=False)
	version.report_html = render_report(result.issues, result.skipped)
	version.change_summary = (
		json.dumps(result.change_summary, ensure_ascii=False) if result.change_summary else None
	)
	version.change_html = render_changes(result.change_summary)
	version.parsed_json = json.dumps(result.form.as_dict(), ensure_ascii=False) if result.form else None
	if result.plan:
		version.compiled_meta = json.dumps(result.plan["compiled_meta"], ensure_ascii=False)
		version.preview_json = json.dumps(preview.build(result.plan), ensure_ascii=False)
	else:
		version.compiled_meta = None
		version.preview_json = None
	if not result.ok or counts[WARNING] == 0:
		version.warnings_accepted = 0


SEVERITY_LABEL = {ERROR: "Error", WARNING: "Warning", INFO: "Advice"}
SEVERITY_COLOR = {ERROR: "red", WARNING: "orange", INFO: "blue"}


def render_report(issues: list[Issue], skipped: list[dict]) -> str:
	"""Summary bar plus a table grouped by sheet; every cell reference is click-to-copy."""
	esc = html.escape
	counts = {ERROR: 0, WARNING: 0, INFO: 0}
	for i in issues:
		counts[i.severity] += 1
	if not issues:
		return (
			'<div class="xf-report"><div class="xf-summary xf-ok">'
			+ esc(_("No problems found. This version is ready to preview and publish."))
			+ "</div></div>"
		)
	parts = ['<div class="xf-report"><div class="xf-summary">']
	for sev in (ERROR, WARNING, INFO):
		if counts[sev]:
			label = {ERROR: _("{0} errors"), WARNING: _("{0} warnings"), INFO: _("{0} advice")}[sev].format(
				counts[sev]
			)
			parts.append(f'<span class="indicator-pill {SEVERITY_COLOR[sev]}">{esc(label)}</span> ')
	parts.append("</div>")
	groups: dict[str, list[Issue]] = {}
	for i in issues:
		groups.setdefault(i.sheet or _("Workbook"), []).append(i)
	for sheet, items in groups.items():
		parts.append(f'<h5 class="xf-sheet">{esc(sheet)}</h5>')
		parts.append('<table class="table table-bordered xf-issues"><thead><tr>')
		for h in (_("Cell"), _("Problem"), _("Suggested fix"), _("Code")):
			parts.append(f"<th>{esc(h)}</th>")
		parts.append("</tr></thead><tbody>")
		for i in items:
			ref = f"{i.sheet}!{i.cell}" if i.cell else (f"{i.sheet} {_('row')} {i.row}" if i.row else "")
			cell = (
				f'<a class="xf-copy" data-copy="{esc(ref)}" title="{esc(_("Click to copy"))}">{esc(ref)}</a>'
				if ref
				else ""
			)
			message = i.message.split(": ", 1)[1] if i.cell and ": " in i.message else i.message
			parts.append(
				f'<tr class="xf-{i.severity}"><td class="text-nowrap">'
				f'<span class="indicator {SEVERITY_COLOR[i.severity]}"></span>{cell}</td>'
				f"<td>{esc(message)}</td><td>{esc(i.suggestion)}</td>"
				f'<td class="text-nowrap"><a href="{esc(i.docs_url)}" target="_blank" rel="noopener">{esc(i.code)}</a></td></tr>'
			)
		parts.append("</tbody></table>")
	for s in skipped:
		parts.append(f'<p class="text-muted small">{esc(s["message"])}</p>')
	parts.append("</div>")
	return "".join(parts)


def render_changes(summary: dict | None) -> str:
	if not summary:
		return ""
	esc = html.escape
	rows = []
	for key, label in (
		("added", _("New questions")),
		("removed", _("Removed (answers kept, question hidden)")),
		("renamed", _("Renamed (answers do not move)")),
		("moved", _("Moved into or out of a repeat (answers do not move)")),
		("type_changed", _("Type changed (new column; earlier answers stay in the old one)")),
	):
		items = summary.get(key) or []
		if not items:
			continue
		text = ", ".join(f"{i['from']} → {i['to']}" if isinstance(i, dict) else str(i) for i in items)
		rows.append(f"<tr><th>{esc(label)}</th><td>{esc(text)}</td></tr>")
	if not rows:
		return f'<p class="text-muted">{esc(_("No changes to questions."))}</p>'
	return '<table class="table table-bordered">' + "".join(rows) + "</table>"
