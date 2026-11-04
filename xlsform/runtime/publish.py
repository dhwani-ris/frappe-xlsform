"""Publishing: compile a Valid version, check it, apply it, then submit it (REQUIREMENTS.md section 9).

The version is submitted (docstatus 1, immutable) only after the schema changes succeeded, so
"Published" always means "the DocTypes match this version". A Redis lock, shared by every worker of
the site, makes two publishes run one after the other. MariaDB commits DDL at once, so a publish
that fails after its first schema change leaves those changes in place; ownership is recorded first,
and publishing again reuses them.
"""

import json
import traceback

import frappe
from frappe import _

import xlsform.runtime
from xlsform.core.validate import validate
from xlsform.runtime import apply as xf_apply
from xlsform.runtime import navigation, validation
from xlsform.runtime import settings as xf_settings

LOCK_SECONDS = 1800
LOCK_WAIT_SECONDS = 600


def check_can_publish(version) -> None:
	xf_settings.require_designer()
	s = xf_settings.get()
	if not s.designers_can_publish and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can publish forms on this site."), frappe.PermissionError)
	if version.docstatus != 0:
		frappe.throw(_("This version is already published."))
	if version.state != "Valid":
		frappe.throw(
			_("Only a version without errors can be published. Fix the workbook and upload it again.")
		)
	if version.warning_count and not version.warnings_accepted:
		frappe.throw(_('This version has warnings. Tick "I understand the warnings" first.'))


def enqueue(version_name: str) -> str:
	version = frappe.get_doc("XLSForm Version", version_name)
	check_can_publish(version)
	version.db_set({"publish_status": "queued", "publish_error": None})
	job_id = f"xlsform-publish-{version_name}"
	in_test = bool(frappe.flags.in_test)
	frappe.enqueue(
		"xlsform.runtime.publish.run",
		queue="long",
		timeout=LOCK_SECONDS,
		job_id=job_id,
		deduplicate=True,
		enqueue_after_commit=not in_test,
		version_name=version_name,
		user=frappe.session.user,
		now=in_test,
	)
	return job_id


def run(version_name: str, user: str | None = None) -> None:
	"""The background job. Runs as the user who queued it, so permission checks still apply."""
	version = frappe.get_doc("XLSForm Version", version_name)
	try:
		with frappe.cache.lock(
			f"xlsform-publish:{frappe.local.site}", timeout=LOCK_SECONDS, blocking_timeout=LOCK_WAIT_SECONDS
		):
			_publish(version)
	except Exception as exc:
		frappe.db.rollback()
		message = (
			str(exc)
			if isinstance(exc, frappe.ValidationError)
			else _("Publishing failed: {0}").format(str(exc))
		)
		frappe.log_error(title=f"XLSForm publish {version_name}", message=traceback.format_exc())
		frappe.db.set_value(
			"XLSForm Version", version_name, {"publish_status": "failed", "publish_error": message}
		)
		frappe.db.commit()  # nosemgrep
		if frappe.flags.in_test:
			raise
		return
	frappe.publish_realtime("xlsform_published", {"version": version_name}, user=user, after_commit=True)


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
		frappe.throw(
			_("The form no longer passes its checks: {0}").format(errors[0].message if errors else "")
		)
	plan = result.plan
	xf_apply.preflight(plan, form, s.doctype_prefix)

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
	if result.form.title and not form.title:
		form.title = result.form.title
	form.flags.ignore_permissions = True
	form.flags.xf_skip_access_sync = True
	form.save()
	frappe.cache.delete_value(f"xlsform:form-of:{form.data_doctype}")
	navigation.sync_workspace()
