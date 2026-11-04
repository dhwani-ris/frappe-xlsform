# Copyright (c) 2026, Dhwani RIS and contributors
# For license information, please see LICENSE

import re

import frappe
from frappe import _
from frappe.model.document import Document


class XLSFormSettings(Document):
	def validate(self):
		if self.doctype_prefix and not re.match(r"^[A-Z][A-Za-z0-9]{0,7}$", self.doctype_prefix):
			frappe.throw(
				_("The prefix must start with a capital letter and use only letters and numbers (up to 8).")
			)
		before = self.get_doc_before_save()
		if before and before.doctype_prefix and before.doctype_prefix != self.doctype_prefix:
			if frappe.db.count("XLSForm", {"data_doctype": ["is", "set"]}):
				frappe.throw(_("The prefix can't change once forms are published."))
		if self.row_budget_bytes and self.row_budget_bytes > 65000:
			frappe.throw(_("The row size budget must stay under MariaDB's limit of 65,535 bytes."))
