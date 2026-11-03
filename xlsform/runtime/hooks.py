"""Document hooks for generated DocTypes, plus install and uninstall.

``validate_record`` is registered for every DocType (``doc_events["*"]``) and returns at
once unless the DocType is an XLSForm parent (it has ``xf_form``), so it costs one cached
meta lookup on other saves. For form records it runs the server rules on every channel —
Desk, Web Form, mForm sync, REST — so a client that skips a check still can't store bad data.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime, nowdate

import xlsform.runtime  # noqa: F401
from xlsform.core import engine
from xlsform.core.form import language_code
from xlsform.runtime.settings import DATA_MODULE, DESIGNER


def _is_form_doctype(doc) -> bool:
	meta = doc.meta
	return meta.module == DATA_MODULE and not meta.istable and meta.has_field("xf_form")


def form_of(doctype: str) -> str | None:
	key = f"xlsform:form-of:{doctype}"
	form = frappe.cache.get_value(key)
	if form is None:
		form = frappe.db.get_value("XLSForm", {"data_doctype": doctype}, "name") or ""
		frappe.cache.set_value(key, form)
	return form or None


def version_meta(version: str) -> dict | None:
	"""compiled_meta of a published version; immutable once published, so cached for good."""
	key = f"xlsform:meta:{version}"
	meta = frappe.cache.get_value(key)
	if meta is None:
		raw, docstatus = frappe.db.get_value("XLSForm Version", version, ["compiled_meta", "docstatus"]) or (None, 0)
		meta = json.loads(raw) if isinstance(raw, str) else raw
		if meta and docstatus == 1:
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
	form_name = doc.get("xf_form") or form_of(doc.doctype)
	if not form_name:
		return
	form = frappe.get_cached_value("XLSForm", form_name, ["status", "current_version", "retired_on"], as_dict=True)
	if doc.is_new():
		if form.status == "Retired":
			when = frappe.utils.format_date(form.retired_on) if form.retired_on else ""
			frappe.throw(
				_("This form was closed on {0}; contact your supervisor.").format(when)
				if when
				else _("This form is closed; contact your supervisor."),
				title=_("Form closed"),
			)
		doc.xf_form = form_name
		doc.xf_version = doc.get("xf_version") or form.current_version
		if not doc.get("xf_channel"):
			doc.xf_channel = _channel(doc)
	version = doc.get("xf_version") or form.current_version
	meta = version_meta(version) if version else None
	if not meta:
		return
	_fill_metadata(doc, meta)

	outcome = engine.run(
		meta,
		doc.as_dict(convert_dates_to_str=True),
		choice_lookup=_choice_lookup(meta),
		language=_language_label(meta),
	)
	for fieldname, value in outcome.parent_updates.items():
		if doc.meta.get_field(fieldname) and doc.meta.get_field(fieldname).fieldtype in ("Table", "Table MultiSelect"):
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
	"""Pick the form language matching the user's language, e.g. 'Hindi (hi)' for hi."""
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
		if t == "start" and not doc.get(fn):
			doc.set(fn, now_datetime())
		elif t == "end":
			doc.set(fn, now_datetime())
		elif t == "today" and not doc.get(fn):
			doc.set(fn, nowdate())
		elif t == "username" and not doc.get(fn):
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
			where = _("{0}, row {1}: ").format(frappe.utils.escape_html(f.repeat_label), f.row + 1)
		items.append(f"<li>{where}{frappe.utils.escape_html(f.message)}</li>")
	return "<ul>" + "".join(items) + "</ul>"


# ── install / uninstall ────────────────────────────────────────────────────────


def after_install() -> None:
	from xlsform.runtime.apply import ensure_module

	ensure_module()
	if not frappe.db.exists("Role", DESIGNER):
		frappe.get_doc({"doctype": "Role", "role_name": DESIGNER, "desk_access": 1}).insert(ignore_permissions=True)
	settings = frappe.get_single("XLSForm Settings")
	from xlsform.runtime.settings import DEFAULTS

	for key, value in DEFAULTS.items():
		if settings.get(key) in (None, "", 0) and value:
			settings.set(key, value)
	if not frappe.db.exists("Language", settings.default_language):
		settings.default_language = None
	settings.flags.ignore_permissions = True
	settings.save()


def before_uninstall() -> None:
	allowed = frappe.db.get_single_value("XLSForm Settings", "allow_data_removal_on_uninstall")
	generated = frappe.get_all("DocType", filters={"module": DATA_MODULE}, pluck="name")
	if generated and not allowed:
		frappe.throw(
			_(
				"Uninstalling XLSForm would delete {0} generated DocTypes and all their records. "
				'Tick "Allow uninstall to delete form data" in XLSForm Settings first.'
			).format(len(generated)),
			title=_("Uninstall stopped"),
		)
	from xlsform.runtime.apply import unregister_mobile

	for name in frappe.get_all("XLSForm", pluck="data_doctype"):
		if name:
			unregister_mobile(name)
	for wf in frappe.get_all("Web Form", filters={"module": DATA_MODULE}, pluck="name"):
		frappe.delete_doc("Web Form", wf, force=True, ignore_permissions=True)
	parents = [d for d in generated if not frappe.db.get_value("DocType", d, "istable")]
	children = [d for d in generated if d not in parents]
	for name in parents + children:
		frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
	if frappe.db.exists("Module Def", DATA_MODULE):
		frappe.delete_doc("Module Def", DATA_MODULE, force=True, ignore_permissions=True)
