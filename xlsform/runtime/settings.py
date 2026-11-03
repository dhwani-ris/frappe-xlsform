"""XLSForm Settings with the documented defaults (REQUIREMENTS.md section 4.4)."""

import frappe

DEFAULTS = {
	"max_upload_mb": 5,
	"max_questions": 400,
	"max_choices_per_list": 20000,
	"max_expression_length": 2000,
	"row_budget_bytes": 60000,
	"doctype_prefix": "XF",
	"designers_can_publish": 1,
	"default_language": "en",
	"allow_data_removal_on_uninstall": 0,
}

DATA_MODULE = "XLSForm Data"
CHOICES_MODULE = "XLSForm Choices"
GENERATED_MODULES = (DATA_MODULE, CHOICES_MODULE)
DESIGNER = "XLSForm Designer"


def get() -> frappe._dict:
	doc = frappe.get_cached_doc("XLSForm Settings")
	out = frappe._dict(DEFAULTS)
	for key in DEFAULTS:
		value = doc.get(key)
		if value not in (None, "") and not (
			isinstance(value, int) and value == 0 and DEFAULTS[key] not in (0, 1)
		):
			out[key] = value
	return out


def is_designer(user: str | None = None) -> bool:
	roles = frappe.get_roles(user)
	return "System Manager" in roles or DESIGNER in roles


def require_designer() -> None:
	if not is_designer():
		frappe.throw(frappe._("Only XLSForm Designers can do this."), frappe.PermissionError)
