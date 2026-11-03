"""Write xlsform/locale/main.pot.

Same extraction as ``bench generate-pot-file --app xlsform``, which can't run when the app is
symlinked into the bench (its .gitignore check needs the app inside the bench directory).

usage (from frappe-bench/sites): ../env/bin/python /path/to/xlsform/scripts/generate_pot.py <site>
"""

import os
import sys

import frappe
from babel.messages.extract import extract_from_dir
from frappe.gettext.translate import PYTHON_KEYWORDS, get_method_map, new_catalog, write_catalog

APP = "xlsform"
SKIP_DIRS = {"node_modules", "tests", "dist", "corpus"}


def main(site: str) -> None:
	frappe.init(site=site, sites_path=".")
	frappe.connect()
	app_path = frappe.get_pymodule_path(APP, "..")
	# hooks.py holds no user-facing text, and Frappe's navbar extractor for it needs the app
	# to live inside the bench directory
	method_map = [("**/hooks.py", "ignore"), *get_method_map(APP), *get_method_map("frappe")]
	catalog = new_catalog(APP)

	def keep(dirpath) -> bool:
		name = os.path.basename(dirpath)
		return not (name.startswith((".", "_")) or name in SKIP_DIRS)

	for filename, lineno, message, comments, context in extract_from_dir(
		app_path, method_map, directory_filter=keep, keywords=PYTHON_KEYWORDS
	):
		if message:
			catalog.add(message, locations=[(filename, lineno)], auto_comments=comments, context=context)
	print("POT file created at", write_catalog(APP, catalog), "with", len(catalog), "messages")
	frappe.destroy()


if __name__ == "__main__":
	main(sys.argv[1])
