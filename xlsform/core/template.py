"""The starter XLSForm (REQUIREMENTS.md section 11, ``forms.template``).

A small but complete household survey that shows every supported building block: groups,
skip logic, required answers, constraints, cascading choices, a repeat, calculations, a
note, multilingual labels and the settings sheet. It validates with zero issues (tested).
"""

import io

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

SURVEY = [
	["type", "name", "label", "label::Hindi (hi)", "hint", "required", "relevant", "constraint", "constraint_message", "calculation", "choice_filter", "appearance", "default"],
	["start", "start"],
	["end", "end"],
	["today", "visit_date"],
	["select_one yes_no", "consent", "Does the respondent agree to take part?", "क्या उत्तरदाता भाग लेने के लिए सहमत है?", None, "yes"],
	["begin_group", "household", "Household", "परिवार", None, None, "${consent} = 'yes'"],
	["text", "head_name", "Name of the head of household", "परिवार के मुखिया का नाम", "Full name as on the ration card", "yes"],
	["integer", "hh_size", "How many people live in this household?", "इस परिवार में कितने लोग रहते हैं?", None, "yes", None, ". > 0 and . <= 30", "Enter a number from 1 to 30"],
	["select_one district", "district", "District", "जिला", None, "yes"],
	["select_one village", "village", "Village", "गाँव", "Only villages of the chosen district are listed", "yes", None, None, None, None, "district = ${district}"],
	["select_multiple services", "services", "Which services did the household receive this year?", "इस वर्ष परिवार को कौन सी सेवाएँ मिलीं?"],
	["text", "health_details", "Which health services?", "कौन सी स्वास्थ्य सेवाएँ?", None, "yes", "selected(${services}, 'health')"],
	["end_group"],
	["begin_repeat", "member", "Household members", "परिवार के सदस्य", None, None, "${hh_size} > 0"],
	["text", "member_name", "Name", "नाम", None, "yes"],
	["integer", "member_age", "Age in years", "उम्र (वर्ष)", None, "yes", None, ". >= 0 and . <= 120", "Age must be between 0 and 120"],
	["select_one yes_no", "in_school", "Goes to school?", "स्कूल जाता/जाती है?", None, None, "${member_age} >= 5 and ${member_age} <= 18"],
	["end_repeat"],
	["calculate", "member_count", None, None, None, None, None, None, None, "count(${member})"],
	["calculate", "total_age", None, None, None, None, None, None, None, "sum(${member_age})"],
	["note", "thanks", "Thank you. Please check the answers before saving.", "धन्यवाद। सहेजने से पहले उत्तर जाँच लें।"],
]
CHOICES = [
	["list_name", "name", "label", "label::Hindi (hi)", "district"],
	["yes_no", "yes", "Yes", "हाँ"],
	["yes_no", "no", "No", "नहीं"],
	["district", "pune", "Pune", "पुणे"],
	["district", "nashik", "Nashik", "नासिक"],
	["village", "khed", "Khed", "खेड", "pune"],
	["village", "maval", "Maval", "मावळ", "pune"],
	["village", "sinnar", "Sinnar", "सिन्नर", "nashik"],
	["services", "health", "Health", "स्वास्थ्य"],
	["services", "education", "Education", "शिक्षा"],
	["services", "livelihood", "Livelihood", "आजीविका"],
]

SETTINGS = [
	["form_title", "form_id", "version", "default_language"],
	["Household Survey", "household_survey", "2026110301", "English (en)"],
]

HELP = {
	("survey", "A1"): "Question type, e.g. text, integer, select_one <list>, begin_group. See the docs for the full list.",
	("survey", "B1"): "Short unique name: letters, numbers and _ only. Used in formulas as ${name}.",
	("survey", "G1"): "Show the question only when this formula is true, e.g. ${consent} = 'yes'.",
	("survey", "H1"): "Answer must make this true. Use . for this answer, e.g. . > 0.",
	("survey", "K1"): "For cascading lists: a column on the choices sheet = ${question}.",
	("choices", "A1"): "Name of the list used after select_one / select_multiple.",
	("settings", "C1"): "Raise this every time you upload a changed form, e.g. 2026110302.",
}


def build() -> bytes:
	wb = Workbook()
	wb.remove(wb.active)
	for title, rows in (("survey", SURVEY), ("choices", CHOICES), ("settings", SETTINGS)):
		ws = wb.create_sheet(title)
		for row in rows:
			ws.append(row)
		for cell in ws[1]:
			cell.font = Font(bold=True)
			cell.fill = PatternFill("solid", fgColor="E7EEF8")
		ws.freeze_panes = "A2"
		for col in ws.columns:
			width = max(len(str(c.value or "")) for c in col)
			ws.column_dimensions[col[0].column_letter].width = min(max(12, width + 2), 60)
	for (sheet, ref), text in HELP.items():
		wb[sheet][ref].comment = Comment(text, "XLSForm for Frappe")
	buf = io.BytesIO()
	wb.save(buf)
	return buf.getvalue()
