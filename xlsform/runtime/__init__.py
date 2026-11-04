"""Frappe-facing side of the app. Importing it routes the core's messages through ``frappe._``."""

import frappe

from xlsform.core.i18n import set_translator

set_translator(lambda text: frappe._(text))
