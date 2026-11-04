"""Export a form's data with the original XLSForm column names (REQUIREMENTS.md section 11).

Columns follow the designer's workbook, not Frappe fieldnames. Repeats become extra sheets (or CSV
files in a zip) linked to the parent by ``PARENT_KEY``, as ODK exports do. select_multiple answers are
space-separated choice names. Records are read with ``frappe.get_list``, so role permissions and
"only their own records" apply. Every export is a private File attached to the XLSForm and is
recorded in the Access Log. Large exports run in a background job.
"""

import csv
import io
import json
import zipfile

import frappe
from frappe import _
from frappe.core.doctype.access_log.access_log import make_access_log

import xlsform.runtime
from xlsform.core.values import MULTI

PAGE = 5000
SYNC_LIMIT = 5000
EXPORT_FILE_DAYS = 1
FORMATS = ("xlsx", "csv")


@frappe.whitelist(methods=["POST"])
def export(form: str, format: str = "xlsx", include_retired: int | str = 1) -> dict:
	"""Export ``form``'s records. Returns ``{"file_url": ...}``, or ``{"queued": True}`` for a large
	export; the user then gets the ``xlsform_export_ready`` realtime event with the file URL."""
	if format not in FORMATS:
		frappe.throw(_("Export format must be xlsx or csv."))
	doc = frappe.get_doc("XLSForm", form)
	if not doc.data_doctype or not doc.current_version:
		frappe.throw(_("This form has not been published yet."))
	if not frappe.has_permission(doc.data_doctype, "export"):
		frappe.throw(_("You don't have permission to export this form's data."), frappe.PermissionError)
	retired = bool(frappe.utils.cint(include_retired))
	if len(frappe.get_list(doc.data_doctype, pluck="name", limit_page_length=SYNC_LIMIT + 1)) > SYNC_LIMIT:
		frappe.enqueue(
			"xlsform.api.data.export_job",
			queue="long",
			timeout=3600,
			job_id=f"xlsform-export-{form}-{frappe.session.user}",
			deduplicate=True,
			enqueue_after_commit=not frappe.flags.in_test,
			now=bool(frappe.flags.in_test),
			form=form,
			format=format,
			include_retired=retired,
			user=frappe.session.user,
		)
		return {"queued": True}
	return {"queued": False, "file_url": build_export(doc, format, retired)}


def export_job(form: str, format: str, include_retired: bool, user: str) -> None:
	"""Background export. Runs as the user who asked for it."""
	doc = frappe.get_doc("XLSForm", form)
	file_url = build_export(doc, format, include_retired)
	frappe.publish_realtime(
		"xlsform_export_ready", {"form": form, "file_url": file_url}, user=user, after_commit=True
	)


def build_export(doc, format: str, include_retired: bool) -> str:
	"""Write the export as a private File attached to the XLSForm and return its URL."""
	raw = frappe.db.get_value("XLSForm Version", doc.current_version, "compiled_meta")
	meta = json.loads(raw) if isinstance(raw, str) else raw
	sheets = build_sheets(meta, doc.data_doctype, include_retired)
	base = f"{doc.form_id}-export-{frappe.utils.now_datetime().strftime('%Y%m%d-%H%M%S')}"
	if format == "csv" and len(sheets) == 1:
		filename, content = f"{base}.csv", _csv(*next(iter(sheets.values())))
	elif format == "csv":
		filename, content = f"{base}.zip", _zip(sheets)
	else:
		filename, content = f"{base}.xlsx", _xlsx(sheets)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": content,
			"is_private": 1,
			"attached_to_doctype": "XLSForm",
			"attached_to_name": doc.name,
		}
	).insert(ignore_permissions=True)
	make_access_log(doctype=doc.data_doctype, document=doc.name, method="Export", file_type=format)
	return file.file_url


def delete_old_exports() -> None:
	"""Daily job: remove export files older than ``EXPORT_FILE_DAYS``."""
	cutoff = frappe.utils.add_days(frappe.utils.now_datetime(), -EXPORT_FILE_DAYS)
	for name in frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "XLSForm",
			"file_name": ["like", "%-export-%"],
			"creation": ["<", cutoff],
		},
		pluck="name",
	):
		frappe.delete_doc("File", name, ignore_permissions=True)


def build_sheets(meta: dict, parent: str, include_retired: bool) -> dict[str, tuple[list[str], list[list]]]:
	fields = [
		f
		for f in meta["fields"]
		if f.get("kind", "question") == "question"
		and f["type"] != "note"
		and (include_retired or not f.get("retired_in"))
	]
	repeats = meta["doctypes"].get("repeats", {})
	tables = {r: next((f for f in meta["fields"] if f["path"] == r), None) for r in repeats}

	def columns(doctype):
		return [f for f in fields if f["doctype"] == doctype]

	parent_cols = columns(parent)
	header = ["KEY", *(_title(f) for f in parent_cols), "SUBMITTED_BY", "SUBMITTED_AT", "FORM_VERSION"]
	names, rows = [], []
	start = 0
	while True:
		batch = frappe.get_list(
			parent,
			fields=[
				"name",
				"owner",
				"creation",
				"xf_version",
				*(f["fieldname"] for f in parent_cols if f["fieldtype"] != "Table MultiSelect"),
			],
			order_by="creation asc, name asc",
			limit_start=start,
			limit_page_length=PAGE,
		)
		if not batch:
			break
		multi = _multi_values(
			parent, [f for f in parent_cols if f["fieldtype"] == "Table MultiSelect"], [r.name for r in batch]
		)
		for r in batch:
			names.append(r.name)
			rows.append(
				[r.name, *(_cell(f, r, multi) for f in parent_cols), r.owner, r.creation, r.xf_version]
			)
		start += PAGE
	sheets = {meta["form_id"]: (header, rows)}
	for path, child in repeats.items():
		table = tables.get(path)
		if table is None:
			continue
		cols = columns(child)
		child_rows = []
		for chunk in _chunks(names, 1000):
			records = frappe.get_all(
				child,
				filters={"parent": ["in", chunk], "parenttype": parent, "parentfield": table["fieldname"]},
				fields=[
					"name",
					"parent",
					"idx",
					*(f["fieldname"] for f in cols if f["fieldtype"] != "Table MultiSelect"),
				],
				order_by="parent asc, idx asc",
			)
			multi = _multi_values(
				child, [f for f in cols if f["fieldtype"] == "Table MultiSelect"], [r.name for r in records]
			)
			for r in records:
				child_rows.append(
					[f"{r.parent}/{table['name']}[{r.idx}]", r.parent, *(_cell(f, r, multi) for f in cols)]
				)
		sheet_header = ["KEY", "PARENT_KEY", *(_title(f) for f in cols)]
		sheets[f"{meta['form_id']}-{table['name']}"[:31]] = (sheet_header, child_rows)
	return sheets


def _title(f: dict) -> str:
	return f"{f['name']} (retired {f['retired_in']})" if f.get("retired_in") else f["name"]


def _multi_values(doctype: str, fields: list[dict], names: list[str]) -> dict:
	"""``{(record, fieldname): "a b"}`` for Table MultiSelect answers."""
	out: dict = {}
	if not fields or not names:
		return out
	meta = frappe.get_meta(doctype)
	for f in fields:
		pick = meta.get_field(f["fieldname"])
		if not pick:
			continue
		for chunk in _chunks(names, 1000):
			for r in frappe.get_all(
				pick.options,
				filters={"parent": ["in", chunk], "parenttype": doctype, "parentfield": f["fieldname"]},
				fields=["parent", "choice"],
				order_by="idx asc",
			):
				key = (r.parent, f["fieldname"])
				out[key] = (out.get(key, "") + " " + (r.choice or "")).strip()
	return out


def _cell(f: dict, record, multi: dict):
	if f["type"] in MULTI:
		return multi.get((record.name, f["fieldname"]), "")
	value = record.get(f["fieldname"])
	if f["type"] == "acknowledge":
		return "OK" if value else ""
	return "" if value is None else value


def _chunks(items, size):
	for i in range(0, len(items), size):
		yield items[i : i + size]


def _csv(header, rows) -> bytes:
	buf = io.StringIO()
	writer = csv.writer(buf)
	writer.writerow(header)
	for r in rows:
		writer.writerow([_safe(v) for v in r])
	return ("﻿" + buf.getvalue()).encode("utf-8")


def _zip(sheets: dict) -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
		for name, (header, rows) in sheets.items():
			zf.writestr(f"{name}.csv", _csv(header, rows))
	return buf.getvalue()


def _safe(value):
	"""Neutralise spreadsheet formula injection in exported text."""
	if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
		return "'" + value
	return value


def _xlsx(sheets: dict) -> bytes:
	from openpyxl import Workbook
	from openpyxl.styles import Font

	wb = Workbook()
	wb.remove(wb.active)
	for name, (header, rows) in sheets.items():
		ws = wb.create_sheet(name[:31])
		ws.append(header)
		for c in ws[1]:
			c.font = Font(bold=True)
		for r in rows:
			ws.append([_safe(v) if not hasattr(v, "isoformat") else v for v in r])
		ws.freeze_panes = "A2"
	buf = io.BytesIO()
	wb.save(buf)
	return buf.getvalue()
