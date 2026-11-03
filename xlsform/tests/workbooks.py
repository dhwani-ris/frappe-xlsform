"""Build XLSForm workbooks in memory for tests.

Fixtures are written as Python data rather than committed .xlsx files, so every test shows
exactly which cells it relies on and a diff shows exactly what changed.
"""

import io

import openpyxl


def make_xlsx(survey, choices=None, settings=None, extra_sheets=None) -> bytes:
	"""Each sheet is a list of rows; the first row is the header. Dict rows are also accepted."""
	wb = openpyxl.Workbook()
	wb.remove(wb.active)
	for title, rows in (
		("survey", survey),
		("choices", choices),
		("settings", settings),
		*(extra_sheets or {}).items(),
	):
		if rows is None:
			continue
		ws = wb.create_sheet(title)
		for row in _rows(rows):
			ws.append(row)
	buf = io.BytesIO()
	wb.save(buf)
	return buf.getvalue()


def _rows(rows):
	if rows and isinstance(rows[0], dict):
		header = []
		for r in rows:
			for k in r:
				if k not in header:
					header.append(k)
		return [header] + [[r.get(h) for h in header] for r in rows]
	return rows


HOUSEHOLD = dict(
	survey=[
		[
			"type",
			"name",
			"label",
			"label::Hindi (hi)",
			"hint",
			"relevant",
			"required",
			"constraint",
			"constraint_message",
			"calculation",
			"choice_filter",
			"appearance",
		],
		["start", "start", None, None, None, None, None, None, None, None, None, None],
		[
			"select_one yes_no",
			"consent",
			"Do you consent?",
			"क्या आप सहमत हैं?",
			None,
			None,
			"yes",
			None,
			None,
			None,
			None,
			None,
		],
		[
			"begin_group",
			"hh",
			"Household",
			"परिवार",
			None,
			"${consent} = 'yes'",
			None,
			None,
			None,
			None,
			None,
			"field-list",
		],
		[
			"text",
			"hh_head",
			"Head of household",
			"परिवार का मुखिया",
			"Full name",
			None,
			"yes",
			None,
			None,
			None,
			None,
			None,
		],
		[
			"integer",
			"hh_size",
			"Household size",
			"परिवार का आकार",
			None,
			None,
			"yes",
			". > 0 and . < 40",
			"Between 1 and 39",
			None,
			None,
			None,
		],
		[
			"select_one district",
			"district",
			"District",
			"जिला",
			None,
			None,
			"yes",
			None,
			None,
			None,
			None,
			"minimal",
		],
		[
			"select_one village",
			"village",
			"Village",
			"गाँव",
			None,
			None,
			"yes",
			None,
			None,
			None,
			"district = ${district}",
			None,
		],
		[
			"select_multiple services",
			"services",
			"Services received",
			"सेवाएं",
			None,
			None,
			None,
			None,
			None,
			None,
			None,
			None,
		],
		[
			"text",
			"health_detail",
			"Which health service?",
			None,
			None,
			"selected(${services}, 'health')",
			"yes",
			None,
			None,
			None,
			None,
			None,
		],
		["end_group", None, None, None, None, None, None, None, None, None, None, None],
		[
			"begin_repeat",
			"member",
			"Members",
			"सदस्य",
			None,
			"${hh_size} > 0",
			None,
			None,
			None,
			None,
			None,
			None,
		],
		["text", "m_name", "Name", "नाम", None, None, "yes", None, None, None, None, None],
		["integer", "m_age", "Age", "उम्र", None, None, "yes", ". >= 0 and . <= 120", None, None, None, None],
		[
			"select_one yes_no",
			"m_school",
			"In school?",
			None,
			None,
			"${m_age} >= 5 and ${m_age} <= 18",
			None,
			None,
			None,
			None,
			None,
			None,
		],
		["end_repeat", None, None, None, None, None, None, None, None, None, None, None],
		["calculate", "n_members", None, None, None, None, None, None, None, "count(${member})", None, None],
		["calculate", "total_age", None, None, None, None, None, None, None, "sum(${m_age})", None, None],
		[
			"note",
			"summary",
			"Thank you. **{n}** members recorded.",
			None,
			None,
			"${n_members} > 0",
			None,
			None,
			None,
			None,
			None,
			None,
		],
		[
			"acknowledge",
			"ack",
			"I confirm the answers are correct",
			None,
			None,
			None,
			"yes",
			None,
			None,
			None,
			None,
			None,
		],
	],
	choices=[
		["list_name", "name", "label", "label::Hindi (hi)", "district"],
		["yes_no", "yes", "Yes", "हाँ", None],
		["yes_no", "no", "No", "नहीं", None],
		["district", "d1", "Pune", "पुणे", None],
		["district", "d2", "Nashik", "नासिक", None],
		["village", "v1", "Village A", None, "d1"],
		["village", "v2", "Village B", None, "d1"],
		["village", "v3", "Village C", None, "d2"],
		["services", "health", "Health", "स्वास्थ्य", None],
		["services", "education", "Education", "शिक्षा", None],
	],
	settings=[
		["form_title", "form_id", "version", "default_language"],
		["Household Survey", "hh_survey", "2026110301", "English (en)"],
	],
)
