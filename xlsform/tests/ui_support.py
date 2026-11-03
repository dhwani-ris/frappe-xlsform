"""Helpers for UI tests on throwaway sites. Never called by the app itself."""

import frappe


def complete_setup() -> None:
	"""Mark the setup wizard done so Desk opens straight away (CI and local UI test sites only)."""
	if not frappe.conf.get("allow_tests") and not frappe.conf.get("developer_mode"):
		frappe.throw("complete_setup is only for test or developer sites")
	for app in frappe.get_installed_apps():
		frappe.db.set_value("Installed Application", {"app_name": app}, "is_setup_complete", 1)
	frappe.db.set_single_value(
		"System Settings", {"setup_complete": 1, "country": "India", "time_zone": "Asia/Kolkata"}
	)
	frappe.db.set_default("desktop:home_page", "workspace")
	frappe.db.commit()
