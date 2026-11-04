"""Turn a compiler plan into DocTypes, choice records, translations and a Web Form.

This is the only code that changes a site's schema (REQUIREMENTS.md section 10). It runs inside the
publish job after the caller's role was checked, touches only the DocTypes the form owns, never
removes a field or a table, and never changes an existing field's type.
"""

import frappe
from frappe import _

from xlsform.core.form import language_code
from xlsform.runtime import access, ownership
from xlsform.runtime.settings import DATA_MODULE, GENERATED_MODULES

DOCTYPE_PROPS = (
	"istable",
	"autoname",
	"naming_rule",
	"title_field",
	"show_title_field_in_link",
	"translated_doctype",
	"search_fields",
	"sort_field",
	"sort_order",
	"track_changes",
	"allow_import",
)
FIELD_PROPS = (
	"label",
	"options",
	"reqd",
	"read_only",
	"hidden",
	"depends_on",
	"mandatory_depends_on",
	"read_only_depends_on",
	"description",
	"default",
	"length",
	"link_filters",
	"in_list_view",
	"in_standard_filter",
	"non_negative",
	"unique",
	"max_height",
	"set_only_once",
	"search_index",
)
CLEARED_TO_NONE = (
	"depends_on",
	"mandatory_depends_on",
	"read_only_depends_on",
	"description",
	"default",
	"link_filters",
	"max_height",
)
CLEARED_TO_ZERO = ("reqd", "read_only", "hidden")
LAYOUT_TYPES = ("Section Break", "Tab Break", "Column Break")


class ApplyRefused(frappe.ValidationError):
	pass


def ensure_module() -> None:
	for module in GENERATED_MODULES:
		if not frappe.db.exists("Module Def", module):
			frappe.get_doc(
				{"doctype": "Module Def", "module_name": module, "app_name": "xlsform", "custom": 1}
			).insert(ignore_permissions=True)


def guard(name: str, prefix: str, form: str) -> None:
	"""Refuse a DocType that is not an XLSForm DocType of ``form``."""
	if not name.startswith(prefix + " "):
		raise ApplyRefused(_("Refusing to change DocType {0}: it isn't an XLSForm DocType.").format(name))
	if frappe.db.exists("DocType", name):
		module, custom = frappe.db.get_value("DocType", name, ["module", "custom"])
		if module not in GENERATED_MODULES or not custom:
			raise ApplyRefused(
				_("Refusing to change DocType {0}: it belongs to module {1}.").format(name, module)
			)
		if name not in ownership.owned(form):
			raise ApplyRefused(_("Refusing to change DocType {0}: it belongs to another form.").format(name))


def preflight(plan: dict, form, prefix: str) -> None:
	"""Run Frappe's own DocType validation on every planned DocType before any DDL.

	The checks run inside a savepoint that is always rolled back. A new DocType's meta rows are
	inserted without DDL, so the DocTypes after it in the plan can link to it, and a problem stops the
	publish while the site is still unchanged.
	"""
	for dt in plan["doctypes"]:
		guard(dt["name"], prefix, form.name)
	savepoint = "xlsform_preflight"
	created = []
	frappe.db.savepoint(savepoint)
	try:
		for spec in plan["doctypes"]:
			doc, exists = _build_doctype(spec, form)
			_validate_without_ddl(doc)
			if not exists:
				doc.db_insert()
				for child in doc.get_all_children():
					child.db_insert()
				created.append(doc.name)
	finally:
		frappe.db.rollback(save_point=savepoint)
		for name in created:
			frappe.clear_cache(doctype=name)


def _validate_without_ddl(doc) -> None:
	"""The checks of ``DocType.validate`` that only read. ``validate`` itself can alter child tables."""
	from frappe.core.doctype.doctype.doctype import validate_fields, validate_permissions

	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.validate_name()
	doc.scrub_field_names()
	validate_fields(doc)
	if not doc.istable:
		validate_permissions(doc)
	doc._validate_mandatory()
	doc._validate_length()


def apply(plan: dict, form, prefix: str) -> None:
	ensure_module()
	for dt in plan["doctypes"]:
		guard(dt["name"], prefix, form.name)
	ownership.claim(form.name, {dt["name"] for dt in plan["doctypes"]})
	for spec in plan["doctypes"]:
		doc, exists = _build_doctype(spec, form)
		doc.flags.ignore_permissions = True
		doc.save() if exists else doc.insert()
	for doctype, records in plan["choices"].items():
		_sync_choices(doctype, records)
	_sync_translations(plan["translations"])
	parent = plan["doctypes"][-1]["name"]
	access.sync(form, plan_meta=plan["compiled_meta"])
	if form.allow_web:
		_sync_web_form(plan["web_form"], form)
	else:
		unpublish_web_form(parent)
	if form.allow_mobile:
		_register_mobile(parent)
	for dt in plan["doctypes"]:
		frappe.clear_cache(doctype=dt["name"])


def _build_doctype(spec: dict, form):
	name = spec["name"]
	exists = bool(frappe.db.exists("DocType", name))
	doc = frappe.get_doc("DocType", name) if exists else frappe.new_doc("DocType")
	if not exists:
		doc.name = name
		doc.module = spec.get("module") or DATA_MODULE
		doc.custom = 1
		doc.engine = "InnoDB"
		doc.row_format = "Dynamic"
		doc.description = _(
			"Records of the form {0}, created by XLSForm. Change the form, not this DocType."
		).format(form.title or form.name)
	for prop in DOCTYPE_PROPS:
		if prop in spec:
			doc.set(prop, spec[prop])
	existing = {f.fieldname: f for f in doc.fields}
	order = []
	for f in spec["fields"]:
		order.append(f["fieldname"])
		row = existing.get(f["fieldname"])
		if row is None:
			doc.append("fields", {"fieldname": f["fieldname"], "fieldtype": f["fieldtype"], **_props(f)})
			continue
		if row.fieldtype != f["fieldtype"] and not (row.fieldtype == "Data" and f["fieldtype"] == "Link"):
			frappe.throw(
				_("Field {0} of {1} is a {2} on the site but the form needs a {3}.").format(
					f["fieldname"], name, row.fieldtype, f["fieldtype"]
				)
			)
		_update_field(row, f)
	stale_layout = set()
	for fieldname, row in existing.items():
		if fieldname in order:
			continue
		if row.fieldtype in LAYOUT_TYPES and not fieldname.startswith("mobile_"):
			stale_layout.add(fieldname)
			continue
		if not fieldname.startswith("mobile_"):
			row.hidden = 1
		order.append(fieldname)
	position = {fn: i for i, fn in enumerate(order)}
	doc.fields = sorted(
		(r for r in doc.fields if r.fieldname not in stale_layout),
		key=lambda r: position.get(r.fieldname, len(position)),
	)
	for i, row in enumerate(doc.fields, start=1):
		row.idx = i
	if not doc.istable and not doc.permissions:
		access.default_permissions(doc)
	return doc, exists


def _update_field(row, f: dict) -> None:
	for prop in CLEARED_TO_NONE:
		if prop not in f:
			row.set(prop, None)
	for prop in CLEARED_TO_ZERO:
		if prop not in f:
			row.set(prop, 0)
	for prop, value in _props(f).items():
		if prop == "length" and row.length and value and int(value) < int(row.length):
			continue
		row.set(prop, value)


def _props(f: dict) -> dict:
	return {k: f[k] for k in FIELD_PROPS if k in f}


def _sync_choices(doctype: str, records: list[dict]) -> None:
	columns = [c for c in (records[0].keys() if records else []) if c != "choice_name"]
	existing = {
		r.name: r
		for r in frappe.get_all(
			doctype,
			fields=["name", "xf_retired", *[c for c in columns if c != "xf_retired"]],
			limit_page_length=0,
		)
	}
	keep = set()
	new_rows = []
	for r in records:
		keep.add(r["choice_name"])
		current = existing.get(r["choice_name"])
		if current is None:
			new_rows.append(r)
			continue
		changes = {c: r.get(c) for c in columns if (current.get(c) or None) != (r.get(c) or None)}
		if changes:
			frappe.db.set_value(doctype, r["choice_name"], changes, update_modified=False)
	if new_rows:
		now = frappe.utils.now()
		user = frappe.session.user
		fields = [
			"name",
			"choice_name",
			*columns,
			"owner",
			"modified_by",
			"creation",
			"modified",
			"docstatus",
		]
		values = [
			(r["choice_name"], r["choice_name"], *[r.get(c) for c in columns], user, user, now, now, 0)
			for r in new_rows
		]
		frappe.db.bulk_insert(doctype, fields, values, chunk_size=1000)
	retired = [n for n, r in existing.items() if n not in keep and not r.xf_retired]
	if retired:
		table = frappe.qb.DocType(doctype)
		frappe.qb.update(table).set(table.xf_retired, 1).where(table.name.isin(retired)).run()


def _language(spec: str) -> str | None:
	code = language_code(spec)
	if code and frappe.db.exists("Language", code):
		return code
	name = spec.split("(")[0].strip()
	return frappe.db.get_value("Language", {"language_name": name}, "name") or (
		name.lower() if frappe.db.exists("Language", name.lower()) else None
	)


def _sync_translations(translations: list[dict]) -> None:
	languages: dict[str, str | None] = {}
	changed = False
	for t in translations:
		spec = t["language"]
		if spec not in languages:
			languages[spec] = _language(spec)
		lang = languages[spec]
		if not lang:
			continue
		context = t.get("context") or None
		filters = {
			"language": lang,
			"source_text": t["source_text"],
			"context": context if context else ["is", "not set"],
		}
		name = frappe.db.get_value("Translation", filters)
		if name:
			if frappe.db.get_value("Translation", name, "translated_text") != t["translated_text"]:
				frappe.db.set_value("Translation", name, "translated_text", t["translated_text"])
				changed = True
		else:
			frappe.get_doc(
				{
					"doctype": "Translation",
					"language": lang,
					"source_text": t["source_text"],
					"translated_text": t["translated_text"],
					"context": context,
				}
			).insert(ignore_permissions=True)
			changed = True
	if changed:
		from frappe.translate import clear_cache

		clear_cache()


def _sync_web_form(spec: dict, form) -> None:
	name = frappe.db.get_value("Web Form", {"doc_type": spec["doc_type"]})
	doc = frappe.get_doc("Web Form", name) if name else frappe.new_doc("Web Form")
	doc.update(
		{
			"title": spec["title"],
			"route": spec["route"],
			"doc_type": spec["doc_type"],
			"module": DATA_MODULE,
			"is_standard": 0,
			"published": 1,
			"login_required": 1,
			"allow_edit": 1,
			"allow_multiple": 1,
			"show_list": 1,
			"apply_document_permissions": 1,
			"anonymous": 0,
			"custom_css": spec.get("custom_css") or "",
		}
	)
	doc.set("web_form_fields", [])
	for f in spec["fields"]:
		doc.append("web_form_fields", {k: v for k, v in f.items() if k != "length"})
	doc.flags.ignore_permissions = True
	if name:
		doc.save()
	else:
		doc.insert(set_name=spec["route"].replace("/", "-"))


def unpublish_web_form(parent: str) -> None:
	name = frappe.db.get_value("Web Form", {"doc_type": parent})
	if name:
		frappe.db.set_value("Web Form", name, "published", 0)


def _mobile_control_ready() -> bool:
	return "mobile_control" in frappe.get_installed_apps() and bool(
		frappe.db.exists("DocType", "Mobile Configuration")
	)


def _register_mobile(parent: str) -> None:
	if not _mobile_control_ready():
		return
	config = frappe.get_single("Mobile Configuration")
	config.flags.ignore_permissions = True
	if any(row.mobile_workspace_item == parent for row in config.get("table_lwis") or []):
		config.save()
		return
	group = None
	if frappe.db.exists("DocType", "Mobile Workspace Group"):
		group = "Forms"
		if not frappe.db.exists("Mobile Workspace Group", group):
			frappe.get_doc({"doctype": "Mobile Workspace Group", "group_name": group}).insert(
				ignore_permissions=True
			)
	config.append("table_lwis", {"mobile_workspace_item": parent, "workspace_group_name": group})
	config.save()


def unregister_mobile(parent: str) -> None:
	if not _mobile_control_ready():
		return
	config = frappe.get_single("Mobile Configuration")
	rows = [r for r in config.get("table_lwis") or [] if r.mobile_workspace_item != parent]
	if len(rows) != len(config.get("table_lwis") or []):
		config.set("table_lwis", rows)
		config.flags.ignore_permissions = True
		config.save()
