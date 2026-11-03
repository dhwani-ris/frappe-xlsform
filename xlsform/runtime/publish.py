"""Publishing: compile a Valid version, apply it, then submit it (REQUIREMENTS.md section 9).

The version is submitted (docstatus 1, immutable) only after the schema changes succeeded,
so "Published" always means "the DocTypes match this version". A site-level lock makes two
publishes run one after the other.
"""

import json
import traceback

import frappe
from frappe import _
from frappe.utils.synchronization import filelock

import xlsform.runtime  # noqa: F401
from xlsform.core.validate import validate
from xlsform.runtime import apply as xf_apply
from xlsform.runtime import settings as xf_settings
from xlsform.runtime import validation

LOCK = "xlsform-publish"


def check_can_publish(version) -> None:
	xf_settings.require_designer()
	s = xf_settings.get()
	if not s.designers_can_publish and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can publish forms on this site."), frappe.PermissionError)
	if version.docstatus != 0:
		frappe.throw(_("This version is already published."))
	if version.state != "Valid":
		frappe.throw(_("Only a version without errors can be published. Fix the workbook and upload it again."))
	if version.warning_count and not version.warnings_accepted:
		frappe.throw(_('This version has warnings. Tick "I understand the warnings" first.'))


def enqueue(version_name: str) -> str:
	version = frappe.get_doc("XLSForm Version", version_name)
	check_can_publish(version)
	version.db_set("publish_status", "queued")
	version.db_set("publish_error", None)
	job_id = f"xlsform-publish-{version_name}"
	frappe.enqueue(
		"xlsform.runtime.publish.run",
		queue="long",
		timeout=1800,
		job_id=job_id,
		deduplicate=True,
		version_name=version_name,
		user=frappe.session.user,
		now=bool(frappe.flags.in_test),
	)
	return job_id


def run(version_name: str, user: str | None = None) -> None:
	if user:
		frappe.set_user(user)
	version = frappe.get_doc("XLSForm Version", version_name)
	try:
		with filelock(LOCK, timeout=600):
			_publish(version)
	except Exception as exc:
		frappe.db.rollback()
		message = str(exc) if isinstance(exc, frappe.ValidationError) else _("Publishing failed: {0}").format(exc)
		frappe.log_error(title=f"XLSForm publish {version_name}", message=traceback.format_exc())
		frappe.db.set_value("XLSForm Version", version_name, {"publish_status": "failed", "publish_error": message})
		frappe.db.commit()
		if frappe.flags.in_test:
			raise
		return
	frappe.db.commit()
	frappe.publish_realtime("xlsform_published", {"version": version_name}, user=user)


def _status(version, status: str) -> None:
	version.db_set("publish_status", status, commit=not frappe.flags.in_test)


def _publish(version) -> None:
	check_can_publish(version)
	form = frappe.get_doc("XLSForm", version.form)
	s = xf_settings.get()
	_status(version, "compiling")

	content, filename = validation.file_content(version.source_file)
	opts = validation.options(form.name, validation.csv_attachments(version.name), bool(form.allow_web))
	result = validate(content, filename, opts)
	errors = [i for i in result.issues if i.severity == "error"]
	if errors or result.plan is None:
		frappe.throw(_("The form no longer passes its checks: {0}").format(errors[0].message if errors else ""))
	plan = result.plan
	parsed = result.form

	_status(version, "migrating")
	xf_apply.apply(plan, form, s.doctype_prefix)

	previous = form.current_version
	version.compiled_meta = json.dumps(plan["compiled_meta"], ensure_ascii=False)
	version.state = "Published"
	version.publish_status = "done"
	version.flags.xf_publishing = True
	version.flags.ignore_permissions = True
	version.submit()

	if previous and previous != version.name:
		frappe.db.set_value("XLSForm Version", previous, "state", "Superseded")
	form.reload()
	form.current_version = version.name
	form.data_doctype = plan["compiled_meta"]["doctypes"]["parent"]
	form.status = "Published"
	form.retired_on = None
	if parsed.title and not form.title:
		form.title = parsed.title
	form.flags.ignore_permissions = True
	form.flags.xf_skip_access_sync = True
	form.save()
	frappe.cache.delete_value(f"xlsform:form-of:{form.data_doctype}")
