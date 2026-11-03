# Copyright (c) 2026, Dhwani RIS and contributors
# For license information, please see license.txt

import traceback

import frappe
from frappe import _
from frappe.model.document import Document

import xlsform.runtime
from xlsform.runtime import validation


class XLSFormVersion(Document):
	def before_insert(self):
		if not self.form or not self.version:
			frappe.throw(
				_(
					"Upload workbooks with the Upload button on the XLSForm, so the form and version are read from it."
				)
			)

	def validate(self):
		if self.docstatus != 0 or not self.source_file:
			return
		if self.is_new() or self.has_value_changed("source_file") or self.flags.xf_force_validation:
			if self._size() > validation.ASYNC_BYTES and not frappe.flags.in_test:
				self.state = "Uploaded"
				self.flags.xf_validate_later = True
			else:
				validation.run_for_version(self)

	def on_update(self):
		if self.flags.xf_validate_later:
			frappe.enqueue(
				"xlsform.xlsform.doctype.xlsform_version.xlsform_version.validate_in_background",
				queue="long",
				timeout=300,
				job_id=f"xlsform-validate-{self.name}",
				deduplicate=True,
				enqueue_after_commit=True,
				version_name=self.name,
			)

	def _size(self) -> int:
		return frappe.db.get_value("File", {"file_url": self.source_file}, "file_size") or 0

	def before_submit(self):
		if not self.flags.xf_publishing:
			frappe.throw(
				_("Use the Publish button: it checks the form and creates its DocTypes before publishing.")
			)

	def before_cancel(self):
		frappe.throw(_("A published version can't be cancelled. Upload a new version, or retire the form."))

	def on_trash(self):
		if frappe.db.get_value("XLSForm", self.form, "current_version") == self.name:
			frappe.throw(_("The current version of a form can't be deleted."))


def validate_in_background(version_name: str) -> None:
	"""Check a large workbook outside the request. A failure marks the version Invalid with the reason."""
	doc = frappe.get_doc("XLSForm Version", version_name)
	if doc.docstatus != 0:
		return
	try:
		validation.run_for_version(doc)
		doc.publish_error = None
	except Exception:
		frappe.log_error(title=f"XLSForm validation {version_name}", message=traceback.format_exc())
		doc.reload()
		doc.state = "Invalid"
		doc.publish_error = _(
			"The workbook could not be checked. Upload it again, or ask your administrator."
		)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.publish_realtime(
		"xlsform_validated",
		{"version": version_name},
		doctype="XLSForm Version",
		docname=version_name,
		after_commit=True,
	)
