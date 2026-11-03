"""Which generated DocTypes belong to which form.

Recorded on the XLSForm (``generated_doctypes``) before any schema change, and committed, so it
survives a publish that fails half-way: MariaDB DDL can't be rolled back, and the next publish of
the same form must reuse what the failed one created instead of making "XF Survey 2". ``apply()``
only ever touches DocTypes listed here (REQUIREMENTS.md section 10).
"""

import json

import frappe


def owned(form: str | None) -> set[str]:
	if not form:
		return set()
	raw = frappe.db.get_value("XLSForm", form, "generated_doctypes")
	return set(json.loads(raw)) if raw else set()


def claim(form: str, names: set[str]) -> None:
	current = owned(form)
	if names <= current:
		return
	frappe.db.set_value("XLSForm", form, "generated_doctypes", json.dumps(sorted(current | names)))
	# Committed before the DDL that follows, which MariaDB commits implicitly anyway; a failed
	# publish must still know which DocTypes it created.
	frappe.db.commit()  # nosemgrep
