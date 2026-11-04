"""Record which generated DocTypes belong to which form, and drop the old [xlsform:<form>] tag.

Before this, ownership was a tag in each generated DocType's description, which users saw in
empty list views. It now lives on the XLSForm (generated_doctypes).
"""

import json
import re

import frappe

TAG = re.compile(r"\s*\[xlsform:([^\]]+)\]")


def execute():
	owned: dict[str, set[str]] = {}
	for dt in frappe.get_all(
		"DocType",
		filters={"module": ["in", ["XLSForm Data", "XLSForm Choices"]], "custom": 1},
		fields=["name", "description"],
	):
		match = TAG.search(dt.description or "")
		if match:
			owned.setdefault(match.group(1), set()).add(dt.name)
			frappe.db.set_value(
				"DocType", dt.name, "description", TAG.sub("", dt.description), update_modified=False
			)
	for form in frappe.get_all("XLSForm", fields=["name", "current_version"]):
		names = owned.get(form.name, set())
		if form.current_version:
			raw = frappe.db.get_value("XLSForm Version", form.current_version, "compiled_meta")
			d = (json.loads(raw) if raw else {}).get("doctypes", {})
			names |= {
				d.get("parent"),
				*d.get("repeats", {}).values(),
				*d.get("lists", {}).values(),
				*d.get("picks", {}).values(),
			} - {None}
		if names:
			frappe.db.set_value(
				"XLSForm", form.name, "generated_doctypes", json.dumps(sorted(names)), update_modified=False
			)
	from xlsform.runtime.navigation import sync_workspace

	sync_workspace()
