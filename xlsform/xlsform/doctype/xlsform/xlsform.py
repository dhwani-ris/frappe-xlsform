# Copyright (c) 2026, Dhwani RIS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

import xlsform.runtime  # noqa: F401
from xlsform.core.meaning import FORM_ID_RE
from xlsform.runtime import access


class XLSForm(Document):
	def validate(self):
		if not FORM_ID_RE.match(self.form_id or ""):
			frappe.throw(_("Form ID must start with a letter and use only a-z, 0-9 and _ (3 to 41 characters)."))
		access.validate_rows(self)

	def on_update(self):
		if self.flags.xf_skip_access_sync or not self.data_doctype:
			return
		if self.has_value_changed("access") or self._access_changed():
			access.sync(self)
		if self.status == "Published" and (self.has_value_changed("allow_web") or self.has_value_changed("allow_mobile")):
			frappe.msgprint(
				_("Channel changes take effect when the next version is published."), indicator="blue", alert=True
			)

	def _access_changed(self) -> bool:
		before = self.get_doc_before_save()
		if before is None:
			return True
		def rows(doc):
			return sorted(
				tuple((r.role, *(int(r.get(k) or 0) for k in (*access.FLAGS, "only_own")))) for r in doc.get("access") or []
			)
		return rows(before) != rows(self)

	def on_trash(self):
		if self.data_doctype and frappe.db.exists("DocType", self.data_doctype):
			frappe.throw(_("A published form can't be deleted, because its data would be lost. Retire it instead."))
