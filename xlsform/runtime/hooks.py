"""Document hooks for generated DocTypes, plus install, migrate and uninstall.

``validate_record`` is registered for every DocType (``doc_events["*"]``) and returns at once unless
the DocType is an XLSForm parent, so other saves pay one cached meta lookup. For form records it runs
the server rules on every channel (Desk, Web Form, mForm sync, REST), so a client that skips a check
still cannot store bad data.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime, nowdate

import xlsform.runtime
from xlsform.core import engine
from xlsform.core.form import language_code
from xlsform.runtime.settings import DATA_MODULE, DEFAULTS, GENERATED_MODULES


def _is_form_doctype(doc) -> bool:
	meta = doc.meta
	return meta.module == DATA_MODULE and not meta.istable and meta.has_field("xf_form")


def form_of(doctype: str) -> str | None:
	"""The XLSForm whose published parent DocType is ``doctype``."""
	key = f"xlsform:form-of:{doctype}"
	form = frappe.cache.get_value(key)
	if form is None:
		form = frappe.db.get_value("XLSForm", {"data_doctype": doctype}, "name") or ""
		frappe.cache.set_value(key, form)
	return form or None


def version_meta(version: str) -> dict | None:
	"""compiled_meta of a published version. Published versions never change, so it is cached."""
	key = f"xlsform:meta:{version}"
	meta = frappe.cache.get_value(key)
	if meta is None:
		row = frappe.db.get_value("XLSForm Version", version, ["compiled_meta", "docstatus"], as_dict=True)
		if not row or row.docstatus != 1:
			return None
		meta = json.loads(row.compiled_meta) if isinstance(row.compiled_meta, str) else row.compiled_meta
		if meta:
			frappe.cache.set_value(key, meta)
	return meta


def _channel(doc) -> str:
	request = getattr(frappe.local, "request", None)
	path = getattr(request, "path", "") or ""
	if "web_form" in path or "webform" in path:
		return "Web"
	if doc.get("mobile_uuid"):
		return "mForm"
	if "frappe.desk.form.save" in path or "savedocs" in path:
		return "Desk"
	return "API"


def validate_record(doc, method=None) -> None:
	if not _is_form_doctype(doc):
		return
	form_name = form_of(doc.doctype)
	if not form_name:
		return
	form = frappe.get_cached_value(
		"XLSForm", form_name, ["status", "current_version", "retired_on"], as_dict=True
	)
	if not form:
		return
	if doc.is_new():
		_prepare_new_record(doc, form_name, form)
	else:
		_refuse_identity_change(doc)
	meta = version_meta(doc.xf_version) if doc.xf_version else None
	if not meta:
		return
	_fill_metadata(doc, meta)
	_apply_rules(doc, meta)


def _prepare_new_record(doc, form_name: str, form) -> None:
	if form.status == "Retired":
		when = frappe.utils.format_date(form.retired_on) if form.retired_on else ""
		frappe.throw(
			_("This form was closed on {0}; contact your supervisor.").format(when)
			if when
			else _("This form is closed; contact your supervisor."),
			title=_("Form closed"),
		)
	requested = doc.get("xf_version")
	if requested and requested != form.current_version and not _is_published_version(requested, form_name):
		frappe.throw(
			_("Form version {0} isn't a published version of this form.").format(frappe.bold(requested)),
			title=_("Unknown form version"),
		)
	doc.xf_form = form_name
	doc.xf_version = requested or form.current_version
	doc.xf_channel = _channel(doc)


def _is_published_version(version: str, form_name: str) -> bool:
	row = frappe.db.get_value("XLSForm Version", version, ["form", "docstatus"], as_dict=True)
	return bool(row and row.form == form_name and row.docstatus == 1)


def _refuse_identity_change(doc) -> None:
	before = doc.get_doc_before_save()
	if not before:
		return
	for fieldname in ("xf_form", "xf_version"):
		if before.get(fieldname) and doc.get(fieldname) != before.get(fieldname):
			frappe.throw(
				_("{0} can't be changed after the record is created.").format(
					doc.meta.get_label(fieldname) or fieldname
				),
				title=_("Not allowed"),
			)


def _apply_rules(doc, meta: dict) -> None:
	outcome = engine.run(
		meta,
		doc.as_dict(convert_dates_to_str=True),
		choice_lookup=_choice_lookup(meta),
		language=_language_label(meta),
	)
	for fieldname, value in outcome.parent_updates.items():
		field = doc.meta.get_field(fieldname)
		if field and field.fieldtype in ("Table", "Table MultiSelect"):
			doc.set(fieldname, value or [])
		else:
			doc.set(fieldname, value)
	for (table, idx), updates in outcome.row_updates.items():
		rows = doc.get(table) or []
		if idx < len(rows):
			for fieldname, value in updates.items():
				field = rows[idx].meta.get_field(fieldname)
				if field and field.fieldtype == "Table MultiSelect":
					rows[idx].set(fieldname, value or [])
				else:
					rows[idx].set(fieldname, value)
	if outcome.failures:
		frappe.throw(_failure_html(outcome.failures), title=_("Please check these answers"))


def _language_label(meta: dict) -> str | None:
	"""The form language that matches the user's language, for example 'Hindi (hi)' for hi."""
	lang = (frappe.local.lang or "en").lower()
	for spec in meta.get("languages") or []:
		code = language_code(spec)
		if (code and code.lower() == lang) or spec.split("(")[0].strip().lower() == lang:
			return spec
	return None


def _fill_metadata(doc, meta: dict) -> None:
	for f in meta.get("fields", []):
		if f.get("retired_in") or f.get("kind", "question") != "question" or f["path"].count("/") > 1:
			continue
		t, fn = f["type"], f["fieldname"]
		if doc.get(fn):
			continue
		if t in ("start", "end"):
			doc.set(fn, now_datetime())
		elif t == "today":
			doc.set(fn, nowdate())
		elif t == "username":
			doc.set(fn, frappe.session.user)


def _choice_lookup(meta: dict):
	lists = meta.get("doctypes", {}).get("lists", {})
	cache: dict = {}

	def lookup(list_name: str, choice: str) -> dict | None:
		doctype = lists.get(list_name)
		if not doctype:
			return None
		key = (doctype, choice)
		if key not in cache:
			cache[key] = frappe.db.get_value(doctype, choice, "*", as_dict=True)
		return cache[key]

	return lookup


def _failure_html(failures) -> str:
	items = []
	for f in failures:
		where = ""
		if f.row is not None and f.repeat_label:
			where = _("{0}, row {1}:").format(frappe.utils.escape_html(f.repeat_label), f.row + 1) + " "
		items.append(f"<li>{where}{frappe.utils.escape_html(f.message)}</li>")
	return "<ul>" + "".join(items) + "</ul>"


def after_install() -> None:
	"""Make the generated-data modules and fill XLSForm Settings with the documented defaults."""
	from xlsform.runtime.apply import ensure_module

	ensure_module()
	settings = frappe.get_single("XLSForm Settings")
	for key, value in DEFAULTS.items():
		if settings.get(key) in (None, "", 0) and value:
			settings.set(key, value)
	if settings.default_language and not frappe.db.exists("Language", settings.default_language):
		settings.default_language = None
	settings.flags.ignore_permissions = True
	settings.save()


def after_migrate() -> None:
	"""Keep the generated-data modules present. Never touches settings an admin chose."""
	from xlsform.runtime.apply import ensure_module

	ensure_module()


def before_uninstall() -> None:
	allowed = frappe.db.get_single_value("XLSForm Settings", "allow_data_removal_on_uninstall")
	generated = frappe.get_all("DocType", filters={"module": ["in", GENERATED_MODULES]}, pluck="name")
	if generated and not allowed:
		frappe.throw(
			_(
				"Uninstalling XLSForm would delete {0} generated DocTypes and all their records. "
				'Tick "Allow uninstall to delete form data" in XLSForm Settings first.'
			).format(len(generated)),
			title=_("Uninstall stopped"),
		)
	for wf in frappe.get_all("Web Form", filters={"module": DATA_MODULE}, pluck="name"):
		frappe.delete_doc("Web Form", wf, force=True, ignore_permissions=True)
	remove_generated_doctypes(generated)
	for module in GENERATED_MODULES:
		if frappe.db.exists("Module Def", module):
			frappe.delete_doc("Module Def", module, force=True, ignore_permissions=True)


def remove_generated_doctypes(names: list[str]) -> None:
	"""Delete generated DocTypes and drop their tables, parents before child tables.

	Frappe keeps the table of a deleted DocType, so the records would otherwise stay in the database.
	"""
	generated = [
		name
		for name in names
		if frappe.db.get_value("DocType", name, "module") in GENERATED_MODULES
		and frappe.db.get_value("DocType", name, "custom")
	]
	parents = [d for d in generated if not frappe.db.get_value("DocType", d, "istable")]
	children = [d for d in generated if d not in parents]
	from xlsform.runtime.apply import unregister_mobile

	for name in parents:
		unregister_mobile(name)
		for wf in frappe.get_all("Web Form", filters={"doc_type": name}, pluck="name"):
			frappe.delete_doc("Web Form", wf, force=True, ignore_permissions=True)
	for name in parents + children:
		frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
		frappe.db.sql_ddl("DROP TABLE IF EXISTS `tab{}`".format(name.replace("`", "``")))
