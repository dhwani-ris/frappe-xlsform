import frappe


def has_app_permission() -> bool:
	"""Show the XLSForm tile to designers and System Managers."""
	roles = frappe.get_roles()
	return "System Manager" in roles or "XLSForm Designer" in roles
