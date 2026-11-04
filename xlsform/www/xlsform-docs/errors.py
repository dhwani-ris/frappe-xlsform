"""Public reference for every issue code: /xlsform-docs/errors#CODE (REQUIREMENTS.md section 7)."""

import copy

import frappe

from xlsform.core.error_docs import ENTRIES

no_cache = 0


def get_context(context):
	entries = copy.deepcopy(ENTRIES)
	for e in entries:
		e["message"] = frappe._(e["message"])
		e["suggestion"] = frappe._(e["suggestion"])
	stages = {}
	for e in entries:
		stages.setdefault((e["stage"], e["stage_name"]), []).append(e)
	context.stages = [
		{"number": n, "name": name, "entries": items} for (n, name), items in sorted(stages.items())
	]
	context.title = frappe._("XLSForm issue codes")
	context.no_breadcrumbs = True
	return context
