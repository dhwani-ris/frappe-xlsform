"""The "Form Data" workspace: one shortcut per published form (REQUIREMENTS.md section 8).

A module's computed sidebar lists at most 15 DocTypes and a form's records were otherwise only
reachable from a dropdown on the XLSForm, so the workspace is rebuilt whenever a form is
published, retired or renamed. It belongs to the site (not shipped as a file), like the forms.
"""

import json

import frappe
from frappe import _

from xlsform.runtime.settings import DATA_MODULE

WORKSPACE = "Form Data"


def sync_workspace() -> None:
	"""Rebuild the workspace. Never lets a navigation problem fail a publish or a retire."""
	try:
		_sync()
	except Exception:
		frappe.log_error(title="XLSForm: Form Data workspace")


def _labels(forms) -> dict[str, str]:
	"""Shortcut labels must be unique; add the form ID when two forms share a title."""
	titles = [(f.title or f.name)[:120] for f in forms]
	return {
		f.name: t if titles.count(t) == 1 else f"{t} ({f.name})"[:140]
		for f, t in zip(forms, titles, strict=True)
	}


def _sync() -> None:
	forms = frappe.get_all(
		"XLSForm",
		filters={"status": "Published", "data_doctype": ["is", "set"]},
		fields=["name", "title", "data_doctype"],
		order_by="title asc",
	)
	forms = [f for f in forms if frappe.db.exists("DocType", f.data_doctype)]
	exists = frappe.db.exists("Workspace", WORKSPACE)
	if not forms and not exists:
		return
	ws = frappe.get_doc("Workspace", WORKSPACE) if exists else frappe.new_doc("Workspace")
	ws.update(
		{
			"label": WORKSPACE,
			"title": WORKSPACE,
			"module": DATA_MODULE,
			"public": 1,
			"is_hidden": 0,
			"icon": "table",
			"standard": 0,
		}
	)
	ws.set("shortcuts", [])
	ws.set("links", [])
	content = [
		{
			"id": "xf_header",
			"type": "header",
			"data": {
				"text": f'<span class="h4"><b>{frappe.utils.escape_html(_("Records collected with your forms"))}</b></span>',
				"col": 12,
			},
		}
	]
	labels = _labels(forms)
	for i, f in enumerate(forms):
		label = labels[f.name]
		ws.append(
			"shortcuts", {"type": "DocType", "link_to": f.data_doctype, "label": label, "color": "Grey"}
		)
		content.append({"id": f"xf_sc_{i}", "type": "shortcut", "data": {"shortcut_name": label, "col": 3}})
	if forms:
		ws.append("links", {"type": "Card Break", "label": _("Forms"), "link_count": len(forms)})
		for f in forms:
			ws.append(
				"links",
				{
					"type": "Link",
					"link_type": "DocType",
					"link_to": f.data_doctype,
					"label": labels[f.name],
				},
			)
		content.append({"id": "xf_card", "type": "card", "data": {"card_name": _("Forms"), "col": 4}})
	ws.content = json.dumps(content)
	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	ws.save() if exists else ws.insert()
