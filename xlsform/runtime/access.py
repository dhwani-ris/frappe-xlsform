"""Per-form access = role permissions on the generated DocTypes (REQUIREMENTS.md section 10).

The XLSForm's Access table is the only input. A role with no row sees nothing, because
Frappe denies by default. No User Permissions, no permission query hooks.
"""

import json

import frappe
from frappe import _

from xlsform.runtime.settings import DESIGNER

BLOCKED_ROLES = {"Guest", "All", "Administrator"}
FULL = dict(read=1, write=1, create=1, delete=1, report=1, export=1, print=1, email=1, share=1)
FLAGS = {
	"can_read": "read",
	"can_write": "write",
	"can_create": "create",
	"can_delete": "delete",
	"can_export": "export",
	"can_report": "report",
	"can_print": "print",
}


def validate_rows(form) -> None:
	seen = set()
	for row in form.get("access") or []:
		if row.role in BLOCKED_ROLES:
			frappe.throw(
				_("Row {0}: the role {1} can't be given access to form data.").format(row.idx, frappe.bold(row.role))
			)
		if row.role in seen:
			frappe.throw(_("Row {0}: the role {1} is listed twice.").format(row.idx, frappe.bold(row.role)))
		seen.add(row.role)
		if any(row.get(k) for k in ("can_write", "can_create", "can_delete", "can_export", "can_report", "can_print")):
			row.can_read = 1


def _perm(role: str, **flags) -> dict:
	out = {"role": role, "permlevel": 0}
	for k, v in flags.items():
		out["import" if k == "import_" else k] = v
	return out


def default_permissions(doctype_doc) -> None:
	doctype_doc.set("permissions", [])
	doctype_doc.append("permissions", _perm("System Manager", **FULL, import_=doctype_doc.allow_import or 0))
	doctype_doc.append("permissions", _perm(DESIGNER, read=1, report=1, export=1, print=1))


def rules_for(form) -> list[dict]:
	rows = [_perm("System Manager", **FULL, import_=1), _perm(DESIGNER, read=1, report=1, export=1, print=1)]
	for row in form.get("access") or []:
		if row.role in BLOCKED_ROLES:
			continue
		flags = {perm: 1 for field, perm in FLAGS.items() if row.get(field)}
		if not flags:
			continue
		flags["read"] = 1
		if row.only_own:
			flags["if_owner"] = 1
		if row.role == DESIGNER:
			rows[1].update(flags)
			continue
		rows.append(_perm(row.role, **flags))
	return rows


def sync(form, plan_meta: dict | None = None) -> None:
	"""Write the Access table onto the form's parent DocType and its choice lists."""
	meta = plan_meta
	if meta is None:
		if not form.current_version:
			return
		raw = frappe.db.get_value("XLSForm Version", form.current_version, "compiled_meta")
		meta = json.loads(raw) if isinstance(raw, str) else raw
	if not meta:
		return
	doctypes = meta.get("doctypes", {})
	parent = doctypes.get("parent")
	if parent and frappe.db.exists("DocType", parent):
		_write(parent, rules_for(form))
	readers = [_perm("System Manager", **FULL), _perm(DESIGNER, read=1, report=1)]
	for row in form.get("access") or []:
		if row.role not in BLOCKED_ROLES and row.role != DESIGNER and any(row.get(f) for f in FLAGS):
			readers.append(_perm(row.role, read=1))
	for name in doctypes.get("lists", {}).values():
		if frappe.db.exists("DocType", name):
			_write(name, readers)


def _write(doctype: str, rules: list[dict]) -> None:
	doc = frappe.get_doc("DocType", doctype)
	current = sorted(_normalise(p.as_dict()) for p in doc.permissions)
	wanted = sorted(_normalise(r) for r in rules)
	if current == wanted:
		return
	doc.set("permissions", [])
	for r in rules:
		doc.append("permissions", r)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.clear_cache(doctype=doctype)


PERM_KEYS = ("role", "read", "write", "create", "delete", "report", "export", "print", "email", "share", "import", "if_owner")


def _normalise(p: dict) -> tuple:
	return tuple((k, int(p.get(k) or 0) if k != "role" else p.get(k)) for k in PERM_KEYS)
