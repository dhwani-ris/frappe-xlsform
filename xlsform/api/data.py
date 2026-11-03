"""Export a form's data with the original XLSForm column names (REQUIREMENTS.md section 11).

Columns follow the designer's workbook, not Frappe fieldnames. Repeats become extra sheets
(or CSV files in a zip) linked to the parent by ``PARENT_KEY``, as ODK exports do.
select_multiple answers are space-separated choice names. Records are read with
``frappe.get_list``, so role permissions and "only their own records" apply.
"""

import csv
import io
import json
import zipfile

import frappe
from frappe import _

import xlsform.runtime  # noqa: F401
from xlsform.core.values import MULTI

PAGE = 5000


@frappe.whitelist()
def export(form: str, format: str = "xlsx", include_retired: int | str = 1):
	doc = frappe.get_doc("XLSForm", form)
	if not doc.data_doctype or not doc.current_version:
		frappe.throw(_("This form has not been published yet."))
	if not frappe.has_permission(doc.data_doctype, "export"):
		frappe.throw(_("You don't have permission to export this form's data."), frappe.PermissionError)
	raw = frappe.db.get_value("XLSForm Version", doc.current_version, "compiled_meta")
	meta = json.loads(raw) if isinstance(raw, str) else raw
	sheets = build_sheets(meta, doc.data_doctype, bool(frappe.utils.cint(include_retired)))
	base = f"{doc.form_id}-{frappe.utils.nowdate()}"
	frappe.response["type"] = "download"
	if format == "csv":
		if len(sheets) == 1:
			frappe.response["filename"] = f"{base}.csv"
			frappe.response["filecontent"] = _csv(*next(iter(sheets.values())))
		else:
			buf = io.BytesIO()
			with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
				for name, (header, rows) in sheets.items():
					zf.writestr(f"{name}.csv", _csv(header, rows))
			frappe.response["filename"] = f"{base}.zip"
			frappe.response["filecontent"] = buf.getvalue()
	else:
		frappe.response["filename"] = f"{base}.xlsx"
		frappe.response["filecontent"] = _xlsx(sheets)


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
	names = []
	rows = []
	start = 0
	while True:
		batch = frappe.get_list(
			parent,
			fields=["name", "owner", "creation", "xf_version", *(f["fieldname"] for f in parent_cols if f["fieldtype"] != "Table MultiSelect")],
			order_by="creation asc",
			limit_start=start,
			limit_page_length=PAGE,
		)
		if not batch:
			break
		multi = _multi_values(parent, [f for f in parent_cols if f["fieldtype"] == "Table MultiSelect"], [r.name for r in batch])
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
				fields=["name", "parent", "idx", *(f["fieldname"] for f in cols if f["fieldtype"] != "Table MultiSelect")],
				order_by="parent asc, idx asc",
			)
			multi = _multi_values(child, [f for f in cols if f["fieldtype"] == "Table MultiSelect"], [r.name for r in records])
			for r in records:
				child_rows.append([f"{r.parent}/{table['name']}[{r.idx}]", r.parent, *(_cell(f, r, multi) for f in cols)])
		sheet_header = ["KEY", "PARENT_KEY", *(_title(f) for f in cols)]
		sheets[f"{meta['form_id']}-{table['name']}"[:31]] = (sheet_header, child_rows)
	return sheets


def _title(f: dict) -> str:
	return f"{f['name']} (retired {f['retired_in']})" if f.get("retired_in") else f["name"]


def _multi_values(doctype: str, fields: list[dict], names: list[str]) -> dict:
	"""{(record, fieldname): "a b"} for Table MultiSelect answers."""
	out: dict = {}
	if not fields or not names:
		return out
	for f in fields:
		pick = frappe.get_meta(doctype).get_field(f["fieldname"])
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
