"""Remove Translation records that are exact copies of another.

Earlier versions looked up context-free translations with ``context = ""`` while storing them with no
context, so every publish added another copy of each choice-label translation.
"""

import frappe
from frappe.query_builder.functions import Count, Min


def execute():
	t = frappe.qb.DocType("Translation")
	groups = (
		frappe.qb.from_(t)
		.select(t.language, t.source_text, t.translated_text, t.context, Min(t.name).as_("keep"))
		.groupby(t.language, t.source_text, t.translated_text, t.context)
		.having(Count(t.name) > 1)
		.run(as_dict=True)
	)
	for g in groups:
		query = (
			frappe.qb.from_(t)
			.select(t.name)
			.where(t.language == g.language)
			.where(t.source_text == g.source_text)
			.where(t.translated_text == g.translated_text)
			.where(t.name != g.keep)
		)
		query = query.where(t.context.isnull()) if g.context is None else query.where(t.context == g.context)
		duplicates = [r[0] for r in query.run()]
		if duplicates:
			frappe.db.delete("Translation", {"name": ["in", duplicates]})
	if groups:
		from frappe.translate import clear_cache

		clear_cache()
