"""Designer API (REQUIREMENTS.md section 11). Every method checks the caller's role."""

import base64
import datetime
import json
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

import xlsform.runtime
from xlsform.core import annotate, engine
from xlsform.core import template as starter
from xlsform.core.issues import Issue
from xlsform.core.meaning import normalize_form_id
from xlsform.core.reader import read_workbook
from xlsform.core.validate import validate
from xlsform.runtime import apply as xf_apply
from xlsform.runtime import navigation, validation
from xlsform.runtime import publish as xf_publish
from xlsform.runtime import settings as xf_settings

TRANSIENT_SECONDS = 3600
TEST_RESULTS_KEPT = 20


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=3600)
def upload(file_url: str | None = None, form: str | None = None, csv_urls: str | None = None) -> dict:
	"""Store a workbook (and the CSVs of ``*_from_file`` questions) as a version and check it.

	Returns ``{form, version, state, issues, skipped}``. ``version`` is empty when the file could not
	be stored as a version (unreadable, or its version is already published); ``report_token`` then
	gives access to the annotated workbook for an hour.
	"""
	xf_settings.require_designer()
	content, filename = _incoming_workbook(file_url)
	csvs = _incoming_csvs(csv_urls)

	form_id, version_str, title = _peek(content, filename)
	if form and form_id and form_id != form:
		frappe.throw(
			_("This workbook is for form {0} (settings sheet), not {1}.").format(
				frappe.bold(form_id), frappe.bold(form)
			)
		)
	form_id = form_id or form
	if not form_id:
		return _transient(content, filename, csvs, form=None)
	proposed = None
	if not version_str:
		version_str = proposed = propose_version(form_id)

	try:
		form_doc = _ensure_form(form_id, title)
		frappe.db.get_value("XLSForm", form_doc.name, "name", for_update=True)
		name = f"{form_id}-v{version_str}"
		existing = frappe.db.get_value("XLSForm Version", name, ["name", "docstatus"], as_dict=True)
		if existing and existing.docstatus == 1:
			return _transient(content, filename, csvs, form=form_id)
		version = _store_version(form_doc, existing, version_str, content, filename, csvs, proposed)
	except frappe.DuplicateEntryError, frappe.QueryDeadlockError:
		frappe.throw(
			_("Another upload of this form is in progress. Wait a moment and upload again."),
			title=_("Upload in progress"),
		)

	report = json.loads(version.validation_report or "{}")
	return {
		"form": form_doc.name,
		"version": version.name,
		"state": version.state,
		"issues": report.get("issues", []),
		"skipped": report.get("skipped", []),
		"proposed_version": proposed,
	}


def _store_version(form_doc, existing, version_str, content, filename, csvs, proposed):
	file_doc = _save_file(content, filename)
	if existing:
		version = frappe.get_doc("XLSForm Version", existing.name)
		version.check_permission("write")
		replaced = version.source_file
		version.source_file = file_doc.file_url
	else:
		if not frappe.has_permission("XLSForm Version", "create"):
			frappe.throw(_("You can't create form versions."), frappe.PermissionError)
		replaced = None
		version = frappe.new_doc("XLSForm Version")
		version.form = form_doc.name
		version.version = version_str
		version.source_file = file_doc.file_url
	version.flags.xf_proposed_version = proposed
	version.flags.xf_csvs = csvs
	version.flags.ignore_permissions = True
	version.save()
	_attach(file_doc, version.name)
	for csv_name, csv_content in csvs.items():
		_attach(_save_file(csv_content, csv_name), version.name)
	if csvs and version.state != "Uploaded":
		version.reload()
		version.flags.xf_force_validation = True
		version.flags.ignore_permissions = True
		version.save()
	if replaced and replaced != file_doc.file_url:
		_delete_replaced_file(replaced, version.name)
	return version


def _incoming_workbook(file_url: str | None) -> tuple[bytes, str]:
	files = getattr(frappe.request, "files", None) if getattr(frappe.local, "request", None) else None
	if files and files.get("file"):
		f = files["file"]
		return f.stream.read(), f.filename
	if file_url:
		return validation.readable_file_content(file_url)
	frappe.throw(_("Attach an .xlsx workbook."))


def _incoming_csvs(csv_urls: str | None) -> dict[str, bytes]:
	out = {}
	files = getattr(frappe.request, "files", None) if getattr(frappe.local, "request", None) else None
	if files:
		for key in files:
			if key != "file":
				f = files[key]
				out[f.filename] = f.stream.read()
	urls = json.loads(csv_urls) if csv_urls else []
	if not isinstance(urls, list):
		frappe.throw(_("csv_urls must be a list of file URLs."))
	for url in urls:
		content, name = validation.readable_file_content(url)
		out[name] = content
	return out


def _peek(content: bytes, filename: str) -> tuple[str | None, str | None, str | None]:
	"""form_id, version and title from the settings sheet, without full validation."""
	wb, _issues = read_workbook(content, filename, max_mb=xf_settings.get().max_upload_mb)
	if wb is None:
		return None, None, None
	settings = wb.sheet("settings")
	if settings is None or not settings.rows:
		return None, None, None
	row = settings.rows[0]
	form_id = normalize_form_id(row.get("form_id") or "") if row.get("form_id") else None
	return form_id, row.get("version") or None, row.get("form_title") or None


def propose_version(form_id: str) -> str:
	prefix = datetime.date.today().strftime("%Y%m%d")
	used = set(frappe.get_all("XLSForm Version", filters={"form": form_id}, pluck="version"))
	for n in range(1, 100):
		candidate = f"{prefix}{n:02d}"
		if candidate not in used:
			return candidate
	return prefix + "99"


def _ensure_form(form_id: str, title: str | None):
	if frappe.db.exists("XLSForm", form_id):
		doc = frappe.get_doc("XLSForm", form_id)
		doc.check_permission("write")
		return doc
	if not frappe.has_permission("XLSForm", "create"):
		frappe.throw(_("You can't create forms."), frappe.PermissionError)
	doc = frappe.new_doc("XLSForm")
	doc.form_id = form_id
	doc.title = title or form_id.replace("_", " ").title()
	doc.status = "Draft"
	doc.insert(ignore_permissions=True)
	return doc


def _save_file(content: bytes, filename: str):
	return frappe.get_doc(
		{"doctype": "File", "file_name": filename, "content": content, "is_private": 1}
	).insert(ignore_permissions=True)


def _attach(file_doc, version_name: str) -> None:
	file_doc.db_set({"attached_to_doctype": "XLSForm Version", "attached_to_name": version_name})


def _delete_replaced_file(file_url: str, version_name: str) -> None:
	for name in frappe.get_all(
		"File",
		filters={
			"file_url": file_url,
			"attached_to_doctype": "XLSForm Version",
			"attached_to_name": version_name,
		},
		pluck="name",
	):
		frappe.delete_doc("File", name, ignore_permissions=True)


def _transient(content: bytes, filename: str, csvs: dict, form: str | None) -> dict:
	result = validate(content, filename, validation.options(form, csvs, True))
	token = secrets.token_urlsafe(16)
	frappe.cache.set_value(
		f"xlsform:transient:{token}",
		{
			"user": frappe.session.user,
			"content": base64.b64encode(content).decode(),
			"filename": filename,
			"issues": [i.__dict__ for i in result.issues],
		},
		expires_in_sec=TRANSIENT_SECONDS,
	)
	report = result.report()
	return {
		"form": form,
		"version": None,
		"state": "Invalid",
		"issues": report["issues"],
		"skipped": report["skipped"],
		"report_token": token,
	}


@frappe.whitelist()
def validation_report(version: str | None = None, format: str = "json", token: str | None = None):
	"""Issues as JSON, or ``format=xlsx`` for the annotated copy of the workbook."""
	xf_settings.require_designer()
	if token:
		data = frappe.cache.get_value(f"xlsform:transient:{token}")
		if not data or data["user"] != frappe.session.user:
			frappe.throw(_("This report has expired. Upload the workbook again."))
		issues = [Issue(**i) for i in data["issues"]]
		content, filename = base64.b64decode(data["content"]), data["filename"]
		proposed = None
	elif version:
		doc = frappe.get_doc("XLSForm Version", version)
		doc.check_permission("read")
		report = json.loads(doc.validation_report or "{}")
		issues = [_StoredIssue(i) for i in report.get("issues", [])]
		content, filename = validation.file_content(doc.source_file)
		proposed = doc.version if not _workbook_has_version(content, filename) else None
	else:
		frappe.throw(_("Give a version or a report token."))
	if format == "json":
		return {"issues": [i.as_dict() for i in issues]}
	if not filename.lower().endswith(".xlsx"):
		frappe.throw(_("This file isn't an Excel workbook, so it can't be annotated."))
	frappe.response["type"] = "download"
	frappe.response["filename"] = filename.rsplit(".", 1)[0] + " - checked.xlsx"
	frappe.response["filecontent"] = annotate.annotate(content, issues, proposed)


def _workbook_has_version(content: bytes, filename: str) -> bool:
	wb, _i = read_workbook(content, filename, max_mb=xf_settings.get().max_upload_mb)
	settings = wb.sheet("settings") if wb else None
	return bool(settings and settings.rows and settings.rows[0].get("version"))


class _StoredIssue(Issue):
	"""An issue read back from ``validation_report``, keeping its stored wording."""

	def __init__(self, d: dict):
		super().__init__(
			d["code"], d["severity"], d.get("sheet"), d.get("row"), d.get("column"), d.get("cell"), {}
		)
		self._stored_message = d.get("message") or ""
		self._stored_suggestion = d.get("suggestion") or ""

	@property
	def message(self) -> str:
		return self._stored_message

	@property
	def suggestion(self) -> str:
		return self._stored_suggestion


@frappe.whitelist()
def preview(version: str) -> dict:
	xf_settings.require_designer()
	doc = frappe.get_doc("XLSForm Version", version)
	doc.check_permission("read")
	if not doc.preview_json:
		frappe.throw(_("Fix the errors first; the preview needs a form without errors."))
	data = json.loads(doc.preview_json) if isinstance(doc.preview_json, str) else doc.preview_json
	data["test_results"] = _test_results(doc)
	return data


@frappe.whitelist(methods=["POST"])
def check_answers(version: str, values: str | dict) -> dict:
	"""Run the server rules on test answers. Nothing is written to data tables."""
	xf_settings.require_designer()
	doc = frappe.get_doc("XLSForm Version", version)
	doc.check_permission("read")
	if not doc.compiled_meta:
		frappe.throw(_("Fix the errors first; answers can only be checked on a form without errors."))
	meta = json.loads(doc.compiled_meta) if isinstance(doc.compiled_meta, str) else doc.compiled_meta
	values = json.loads(values) if isinstance(values, str) else (values or {})
	if not isinstance(values, dict):
		frappe.throw(_("Answers must be an object of question names and values."))
	outcome = engine.run(meta, values)
	failures = [
		{"label": f.label, "message": f.message, "row": f.row, "repeat": f.repeat_label, "kind": f.kind}
		for f in outcome.failures
	]
	calculated = {
		f["name"]: outcome.parent_updates[f["fieldname"]]
		for f in meta.get("fields", [])
		if f.get("type") == "calculate" and f["fieldname"] in outcome.parent_updates
	}
	results = _test_results(doc)
	results.insert(
		0,
		{
			"at": frappe.utils.now(),
			"by": frappe.session.user,
			"ok": not failures,
			"failures": failures,
			"values": values,
		},
	)
	doc.db_set(
		"test_results",
		json.dumps(results[:TEST_RESULTS_KEPT], ensure_ascii=False, default=str),
		update_modified=False,
	)
	return {"ok": not failures, "failures": failures, "calculated": calculated}


def _test_results(doc) -> list:
	return json.loads(doc.test_results) if isinstance(doc.test_results, str) else (doc.test_results or [])


@frappe.whitelist(methods=["POST"])
def publish(version: str, accept_warnings: int | str = 0) -> dict:
	xf_settings.require_designer()
	doc = frappe.get_doc("XLSForm Version", version)
	doc.check_permission("write")
	if frappe.utils.cint(accept_warnings) and doc.warning_count:
		doc.db_set("warnings_accepted", 1)
	job_id = xf_publish.enqueue(version)
	return {"job_id": job_id, **publish_status(version)}


@frappe.whitelist()
def publish_status(version: str) -> dict:
	xf_settings.require_designer()
	row = frappe.db.get_value(
		"XLSForm Version", version, ["publish_status", "publish_error", "state", "docstatus"], as_dict=True
	)
	if not row:
		raise frappe.DoesNotExistError(_("Form version {0} not found.").format(version))
	return {
		"status": row.publish_status or "",
		"error": row.publish_error,
		"state": row.state,
		"published": row.docstatus == 1,
	}


@frappe.whitelist(methods=["POST"])
def retire(form: str) -> dict:
	"""Close a form to new records on every channel; existing data is untouched."""
	xf_settings.require_designer()
	doc = frappe.get_doc("XLSForm", form)
	doc.check_permission("write")
	if doc.status != "Published":
		frappe.throw(_("Only a published form can be retired."))
	doc.status = "Retired"
	doc.retired_on = frappe.utils.now_datetime()
	doc.flags.xf_skip_access_sync = True
	doc.flags.ignore_permissions = True
	doc.save()
	if doc.data_doctype:
		xf_apply.unpublish_web_form(doc.data_doctype)
		xf_apply.unregister_mobile(doc.data_doctype)
	navigation.sync_workspace()
	return {"status": doc.status, "retired_on": str(doc.retired_on)}


@frappe.whitelist()
def template():
	"""Download the starter XLSForm."""
	frappe.response["type"] = "download"
	frappe.response["filename"] = "xlsform-starter.xlsx"
	frappe.response["filecontent"] = starter.build()
