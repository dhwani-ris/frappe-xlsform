"""Every issue code fires on a minimal bad workbook, at the right place, and not on its fix.

REQUIREMENTS.md section 13: one failing and one passing fixture per code in section 7.
"""

import io
import re
import unittest
import zipfile

from xlsform.core.issues import CATALOGUE
from xlsform.core.meaning import compare_versions
from xlsform.core.validate import ValidateOptions, validate
from xlsform.tests.workbooks import HOUSEHOLD, make_xlsx

PLACEHOLDER = re.compile(r"(?<!\$)\{[a-z_]+\}")
H = ["type", "name", "label"]
YN = [["list_name", "name", "label"], ["yn", "yes", "Yes"], ["yn", "no", "No"]]
SETTINGS = [["form_id", "version"], ["test_form", "2"]]


def wb(survey, choices=YN, settings=SETTINGS, **extra):
	return make_xlsx(survey=survey, choices=choices, settings=settings, **extra)


def simple(*rows, header=H, **kw):
	return wb([header, *rows], **kw)


def published_meta(survey, choices=YN):
	result = validate(wb(survey, choices), "f.xlsx")
	assert result.ok, [i.message for i in result.issues if i.severity == "error"]
	return result.plan["compiled_meta"]


def ocsp_encrypted() -> bytes:
	return (
		b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
		+ b"\x00" * 64
		+ "EncryptedPackage".encode("utf-16-le")
		+ b"\x00" * 64
	)


def broken_zip() -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		zf.writestr("[Content_Types].xml", "<Types/>")
		zf.writestr("xl/workbook.xml", "not xml at all")
	return buf.getvalue()


def macro_workbook() -> bytes:
	data = io.BytesIO(simple(["text", "a", "A"]))
	out = io.BytesIO()
	with zipfile.ZipFile(data) as src, zipfile.ZipFile(out, "w") as dst:
		for item in src.infolist():
			dst.writestr(item, src.read(item.filename))
		dst.writestr("xl/vbaProject.bin", b"macro")
	return out.getvalue()


PREV_SURVEY = [
	["type", "name", "label"],
	["text", "village", "Village name"],
	["integer", "income", "Income"],
	["integer", "age", "Age"],
	["text", "gone", "Old question"],
	["begin_repeat", "member", "Members"],
	["text", "mname", "Name"],
	["end_repeat"],
]
PREV_META = None


def prev_meta():
	global PREV_META
	if PREV_META is None:
		PREV_META = published_meta(PREV_SURVEY)
	return PREV_META


# code: (bad (content, filename, options), good (content, filename, options), expected location)
def cases():
	big = ValidateOptions(max_upload_mb=0.001)
	return {
		"E-FILE-TYPE": (
			(b"name,label\n", "form.csv", None),
			(simple(["text", "a", "A"]), "form.xlsx", None),
			{},
		),
		"E-FILE-SIZE": (
			(simple(["text", "a", "A"]), "f.xlsx", big),
			(simple(["text", "a", "A"]), "f.xlsx", None),
			{},
		),
		"E-FILE-PROTECTED": (
			(ocsp_encrypted(), "f.xlsx", None),
			(simple(["text", "a", "A"]), "f.xlsx", None),
			{},
		),
		"E-FILE-UNREADABLE": (
			(broken_zip(), "f.xlsx", None),
			(simple(["text", "a", "A"]), "f.xlsx", None),
			{},
		),
		"E-SHEET-MISSING": (
			(make_xlsx(survey=None, extra_sheets={"questions": [H, ["text", "a", "A"]]}), "f.xlsx", None),
			(make_xlsx(survey=[H, ["text", "a", "A"]]), "f.xlsx", None),
			{},
		),
		"E-COL-MISSING": (
			(wb([["type", "label"], ["text", "A"]]), "f.xlsx", None),
			(wb([["type", "name", "label"], ["text", "a", "A"]]), "f.xlsx", None),
			{"sheet": "survey", "column": "name"},
		),
		"W-COL-UNKNOWN": (
			(wb([["type", "name", "lable"], ["text", "a", "A"]]), "f.xlsx", None),
			(wb([["type", "name", "label"], ["text", "a", "A"]]), "f.xlsx", None),
			{"sheet": "survey", "row": 1, "cell": "C1"},
		),
		"W-COL-IGNORED": (
			(wb([["type", "name", "label", "media::image"], ["text", "a", "A", "x.png"]]), "f.xlsx", None),
			(wb([["type", "name", "label"], ["text", "a", "A"]]), "f.xlsx", None),
			{"cell": "D1"},
		),
		"E-COL-UNSUPPORTED": (
			(wb([["type", "name", "label", "trigger"], ["text", "a", "A", "${a}"]]), "f.xlsx", None),
			(wb([["type", "name", "label"], ["text", "a", "A"]]), "f.xlsx", None),
			{"cell": "D1"},
		),
		"E-NAME-MISSING": (
			(simple(["text", None, "Household size"]), "f.xlsx", None),
			(simple(["text", "hh_size", "Household size"]), "f.xlsx", None),
			{"row": 2, "cell": "B2"},
		),
		"E-NAME-INVALID": (
			(simple(["text", "Household size", "A"]), "f.xlsx", None),
			(simple(["text", "household_size", "A"]), "f.xlsx", None),
			{"row": 2, "cell": "B2"},
		),
		"E-NAME-DUPLICATE": (
			(simple(["text", "age", "A"], ["integer", "age", "B"]), "f.xlsx", None),
			(simple(["text", "age", "A"], ["integer", "child_age", "B"]), "f.xlsx", None),
			{"row": 3},
		),
		"E-GROUP-UNCLOSED": (
			(simple(["begin_group", "g", "G"], ["text", "a", "A"]), "f.xlsx", None),
			(simple(["begin_group", "g", "G"], ["text", "a", "A"], ["end_group"]), "f.xlsx", None),
			{"row": 2},
		),
		"E-GROUP-MISMATCH": (
			(simple(["begin_group", "g", "G"], ["text", "a", "A"], ["end_repeat"]), "f.xlsx", None),
			(simple(["begin_group", "g", "G"], ["text", "a", "A"], ["end_group"]), "f.xlsx", None),
			{"row": 4},
		),
		"E-GROUP-EXTRA-END": (
			(simple(["text", "a", "A"], ["end_group"]), "f.xlsx", None),
			(simple(["text", "a", "A"]), "f.xlsx", None),
			{"row": 3},
		),
		"E-TYPE-UNKNOWN": (
			(simple(["selec_one yn", "a", "A"]), "f.xlsx", None),
			(simple(["select_one yn", "a", "A"]), "f.xlsx", None),
			{"row": 2, "cell": "A2"},
		),
		"E-TYPE-UNSUPPORTED": (
			(simple(["rank yn", "a", "A"]), "f.xlsx", None),
			(simple(["select_multiple yn", "a", "A"]), "f.xlsx", None),
			{"row": 2},
		),
		"W-META-IGNORED": (
			(simple(["deviceid", "dev"], ["text", "a", "A"]), "f.xlsx", None),
			(simple(["text", "a", "A"]), "f.xlsx", None),
			{"row": 2},
		),
		"E-LIST-MISSING": (
			(simple(["select_one district", "a", "A"]), "f.xlsx", None),
			(simple(["select_one yn", "a", "A"]), "f.xlsx", None),
			{"row": 2},
		),
		"E-LIST-EMPTY": (
			(
				simple(["select_one_from_file v.csv", "a", "A"]),
				"f.xlsx",
				ValidateOptions(files={"v.csv": b"name,label\n"}),
			),
			(
				simple(["select_one_from_file v.csv", "a", "A"]),
				"f.xlsx",
				ValidateOptions(files={"v.csv": b"name,label\nx,X\n"}),
			),
			{},
		),
		"E-CHOICE-DUPLICATE": (
			(simple(["select_one yn", "a", "A"], choices=[YN[0], YN[1], YN[1]]), "f.xlsx", None),
			(simple(["select_one yn", "a", "A"]), "f.xlsx", None),
			{"sheet": "choices", "row": 3},
		),
		"E-CHOICE-NAME": (
			(
				simple(["select_multiple c", "a", "A"], choices=[YN[0], ["c", "not sure", "Not sure"]]),
				"f.xlsx",
				None,
			),
			(
				simple(["select_multiple c", "a", "A"], choices=[YN[0], ["c", "not_sure", "Not sure"]]),
				"f.xlsx",
				None,
			),
			{"sheet": "choices", "row": 2, "cell": "B2"},
		),
		"E-LIST-TOO-LARGE": (
			(simple(["select_one yn", "a", "A"]), "f.xlsx", ValidateOptions(max_choices_per_list=1)),
			(simple(["select_one yn", "a", "A"]), "f.xlsx", ValidateOptions(max_choices_per_list=2)),
			{},
		),
		"E-FILE-CSV-MISSING": (
			(simple(["select_one_from_file v.csv", "a", "A"]), "f.xlsx", None),
			(
				simple(["select_one_from_file v.csv", "a", "A"]),
				"f.xlsx",
				ValidateOptions(files={"v.csv": b"name,label\nx,X\n"}),
			),
			{"row": 2},
		),
		"E-REPEAT-NESTED": (
			(
				simple(
					["begin_repeat", "hh", "H"],
					["begin_repeat", "m", "M"],
					["text", "a", "A"],
					["end_repeat"],
					["end_repeat"],
				),
				"f.xlsx",
				None,
			),
			(simple(["begin_repeat", "hh", "H"], ["text", "a", "A"], ["end_repeat"]), "f.xlsx", None),
			{"row": 3},
		),
		"E-REPEAT-EMPTY": (
			(simple(["text", "a", "A"], ["begin_repeat", "m", "M"], ["end_repeat"]), "f.xlsx", None),
			(
				simple(["text", "a", "A"], ["begin_repeat", "m", "M"], ["text", "b", "B"], ["end_repeat"]),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"E-REF-UNKNOWN": (
			(
				simple(
					["integer", "hh_size", "A"], ["text", "b", "B", "${hh_sise} > 1"], header=[*H, "relevant"]
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["integer", "hh_size", "A"], ["text", "b", "B", "${hh_size} > 1"], header=[*H, "relevant"]
				),
				"f.xlsx",
				None,
			),
			{"row": 3, "cell": "D3"},
		),
		"E-REF-SELF": (
			(simple(["integer", "age", "A", "${age} > 0"], header=[*H, "constraint"]), "f.xlsx", None),
			(simple(["integer", "age", "A", ". > 0"], header=[*H, "constraint"]), "f.xlsx", None),
			{"row": 2},
		),
		"E-REF-REPEAT": (
			(
				simple(
					["begin_repeat", "member", "M"],
					["integer", "age", "A"],
					["end_repeat"],
					["calculate", "x", None, "${age} + 1"],
					header=[*H, "calculation"],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["begin_repeat", "member", "M"],
					["integer", "age", "A"],
					["end_repeat"],
					["calculate", "x", None, "sum(${age})"],
					header=[*H, "calculation"],
				),
				"f.xlsx",
				None,
			),
			{"row": 5},
		),
		"E-EXPR-SYNTAX": (
			(
				simple(
					["integer", "a", "A"], ["text", "b", "B", "if(${a} > 3, 'x'"], header=[*H, "relevant"]
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["integer", "a", "A"],
					["text", "b", "B", "if(${a} > 3, 'x', '')"],
					header=[*H, "relevant"],
				),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"E-EXPR-QUOTE": (
			(
				simple(["text", "a", "A"], ["text", "b", "B", "${a} = ‘x’"], header=[*H, "relevant"]),
				"f.xlsx",
				None,
			),
			(
				simple(["text", "a", "A"], ["text", "b", "B", "${a} = 'x'"], header=[*H, "relevant"]),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"E-EXPR-TOO-LONG": (
			(
				simple(
					["text", "a", "A"],
					["text", "b", "B", "${a} = '" + "x" * 50 + "'"],
					header=[*H, "relevant"],
				),
				"f.xlsx",
				ValidateOptions(max_expression_length=20),
			),
			(
				simple(["text", "a", "A"], ["text", "b", "B", "${a} = 'x'"], header=[*H, "relevant"]),
				"f.xlsx",
				ValidateOptions(max_expression_length=20),
			),
			{"row": 3},
		),
		"E-FN-UNSUPPORTED": (
			(
				simple(["calculate", "a", None, "pulldata('x', 'y', 'z', 'w')"], header=[*H, "calculation"]),
				"f.xlsx",
				None,
			),
			(
				simple(["calculate", "a", None, "concat('x', 'y')"], header=[*H, "calculation"]),
				"f.xlsx",
				None,
			),
			{"row": 2},
		),
		"E-FN-ARGS": (
			(
				simple(
					["select_multiple yn", "s", "S"],
					["text", "b", "B", "selected(${s})"],
					header=[*H, "relevant"],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["select_multiple yn", "s", "S"],
					["text", "b", "B", "selected(${s}, 'yes')"],
					header=[*H, "relevant"],
				),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"E-EXPR-NOT-LIVE": (
			(
				simple(["date", "d", "D"], ["text", "b", "B", "${d} < today()"], header=[*H, "relevant"]),
				"f.xlsx",
				None,
			),
			(
				simple(["date", "d", "D"], ["text", "b", "B", "${d} != ''"], header=[*H, "relevant"]),
				"f.xlsx",
				None,
			),
			{"row": 3, "column": "relevant"},
		),
		"E-CALC-NOT-LIVE": (
			(
				simple(
					["date", "d", "D"],
					["calculate", "age", None, None, "int((today() - ${d}) div 365)"],
					["text", "b", "B", "${age} > 18", None],
					header=[*H, "relevant", "calculation"],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["date", "d", "D"],
					["calculate", "age", None, None, "int((today() - ${d}) div 365)"],
					["text", "b", "B", "${d} != ''", None],
					header=[*H, "relevant", "calculation"],
				),
				"f.xlsx",
				None,
			),
			{"row": 4},
		),
		"E-CALC-CYCLE": (
			(
				simple(
					["calculate", "total", None, "${share} + 1"],
					["calculate", "share", None, "${total} div 2"],
					header=[*H, "calculation"],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["calculate", "total", None, "1"],
					["calculate", "share", None, "${total} div 2"],
					header=[*H, "calculation"],
				),
				"f.xlsx",
				None,
			),
			{},
		),
		"E-FILTER-UNSUPPORTED": (
			(
				simple(
					["select_one d", "d", "D", None],
					["select_one v", "v", "V", "district = ${d} or district = ''"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["select_one d", "d", "D", None],
					["select_one v", "v", "V", "district = ${d}"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"E-FILTER-COLUMN": (
			(
				simple(
					["select_one d", "d", "D", None],
					["select_one v", "v", "V", "state = ${d}"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["select_one d", "d", "D", None],
					["select_one v", "v", "V", "district = ${d}"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"E-FILTER-MULTI": (
			(
				simple(
					["select_one d", "d", "D", None],
					["select_multiple v", "v", "V", "district = ${d}"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["select_one d", "d", "D", None],
					["select_one v", "v", "V", "district = ${d}"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"W-WEB-FILTER": (
			(
				simple(
					["select_one d", "d", "D", None],
					["select_one v", "v", "V", "district = ${d}"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				None,
			),
			(
				simple(
					["select_one d", "d", "D", None],
					["select_one v", "v", "V", "district = ${d}"],
					header=[*H, "choice_filter"],
					choices=[
						["list_name", "name", "label", "district"],
						["d", "d1", "D1", None],
						["v", "v1", "V1", "d1"],
					],
				),
				"f.xlsx",
				ValidateOptions(allow_web=False),
			),
			{"row": 3},
		),
		"W-WEB-FIELD": (
			(simple(["geopoint", "gps", "Location"]), "f.xlsx", None),
			(simple(["geopoint", "gps", "Location"]), "f.xlsx", ValidateOptions(allow_web=False)),
			{"row": 2},
		),
		"E-DEFAULT-DYNAMIC": (
			(
				simple(["integer", "a", "A", None], ["integer", "b", "B", "${a}"], header=[*H, "default"]),
				"f.xlsx",
				None,
			),
			(
				simple(["integer", "a", "A", None], ["date", "b", "B", "today()"], header=[*H, "default"]),
				"f.xlsx",
				None,
			),
			{"row": 3},
		),
		"W-APPEARANCE": (
			(simple(["text", "a", "A", "quick-compact"], header=[*H, "appearance"]), "f.xlsx", None),
			(simple(["text", "a", "A", "multiline"], header=[*H, "appearance"]), "f.xlsx", None),
			{"row": 2},
		),
		"W-PARAMETER": (
			(simple(["image", "a", "A", "max-pixels=1024"], header=[*H, "parameters"]), "f.xlsx", None),
			(simple(["image", "a", "A", None], header=[*H, "parameters"]), "f.xlsx", None),
			{"row": 2},
		),
		"E-PARAMETER-INVALID": (
			(simple(["range", "a", "A", "start=one end=10"], header=[*H, "parameters"]), "f.xlsx", None),
			(simple(["range", "a", "A", "start=1 end=10"], header=[*H, "parameters"]), "f.xlsx", None),
			{"row": 2},
		),
		"E-SETTING-INVALID": (
			(wb([H, ["text", "a", "A"]], settings=[["form_id"], ["Household Survey"]]), "f.xlsx", None),
			(wb([H, ["text", "a", "A"]], settings=[["form_id"], ["household_survey"]]), "f.xlsx", None),
			{"sheet": "settings", "cell": "A2"},
		),
		"E-SETTING-ENCRYPTED": (
			(
				wb([H, ["text", "a", "A"]], settings=[["form_id", "public_key"], ["abc_form", "MIIB"]]),
				"f.xlsx",
				None,
			),
			(wb([H, ["text", "a", "A"]], settings=[["form_id"], ["abc_form"]]), "f.xlsx", None),
			{"sheet": "settings"},
		),
		"W-SETTING-IGNORED": (
			(
				wb(
					[H, ["text", "a", "A"]],
					settings=[["form_id", "submission_url"], ["abc_form", "https://x"]],
				),
				"f.xlsx",
				None,
			),
			(wb([H, ["text", "a", "A"]], settings=[["form_id"], ["abc_form"]]), "f.xlsx", None),
			{"sheet": "settings", "cell": "B2"},
		),
		"W-INSTANCE-NAME": (
			(
				wb([H, ["text", "a", "A"]], settings=[["form_id", "instance_name"], ["abc_form", "uuid()"]]),
				"f.xlsx",
				None,
			),
			(
				wb(
					[H, ["text", "a", "A"]],
					settings=[["form_id", "instance_name"], ["abc_form", "concat(${a}, '-x')"]],
				),
				"f.xlsx",
				None,
			),
			{"sheet": "settings"},
		),
		"E-VERSION-ORDER": (
			(
				wb([H, ["text", "a", "A"]], settings=[["form_id", "version"], ["abc_form", "2024-01"]]),
				"f.xlsx",
				ValidateOptions(published_version="2025-03"),
			),
			(
				wb([H, ["text", "a", "A"]], settings=[["form_id", "version"], ["abc_form", "2025-04"]]),
				"f.xlsx",
				ValidateOptions(published_version="2025-03"),
			),
			{"sheet": "settings"},
		),
		"E-VERSION-PUBLISHED": (
			(
				wb([H, ["text", "a", "A"]], settings=[["form_id", "version"], ["abc_form", "2025-03"]]),
				"f.xlsx",
				ValidateOptions(published_version="2025-03"),
			),
			(
				wb([H, ["text", "a", "A"]], settings=[["form_id", "version"], ["abc_form", "2025-03b"]]),
				"f.xlsx",
				ValidateOptions(published_version="2025-03"),
			),
			{"sheet": "settings"},
		),
		"E-LIMIT-QUESTIONS": (
			(simple(["text", "a", "A"], ["text", "b", "B"]), "f.xlsx", ValidateOptions(max_questions=1)),
			(simple(["text", "a", "A"], ["text", "b", "B"]), "f.xlsx", ValidateOptions(max_questions=2)),
			{},
		),
		"E-ROW-BUDGET": (
			(
				simple(*[["barcode", f"b{i}", "B"] for i in range(5)]),
				"f.xlsx",
				ValidateOptions(row_budget_bytes=5000),
			),
			(
				simple(*[["text", f"b{i}", "B"] for i in range(5)]),
				"f.xlsx",
				ValidateOptions(row_budget_bytes=5000),
			),
			{},
		),
		"W-RENAME": (
			(
				wb([PREV_SURVEY[0], ["text", "village_name", "Village name"], *PREV_SURVEY[2:]]),
				"f.xlsx",
				"prev",
			),
			(wb(PREV_SURVEY), "f.xlsx", "prev"),
			{"row": 2},
		),
		"W-MOVE-REPEAT": (
			(
				wb(
					[
						PREV_SURVEY[0],
						PREV_SURVEY[1],
						PREV_SURVEY[2],
						PREV_SURVEY[4],
						["begin_repeat", "member", "Members"],
						["text", "mname", "Name"],
						["integer", "age", "Age"],
						["end_repeat"],
					]
				),
				"f.xlsx",
				"prev",
			),
			(wb(PREV_SURVEY), "f.xlsx", "prev"),
			{"row": 7},
		),
		"W-TYPE-CHANGE": (
			(
				wb([PREV_SURVEY[0], PREV_SURVEY[1], ["text", "income", "Income"], *PREV_SURVEY[3:]]),
				"f.xlsx",
				"prev",
			),
			(wb(PREV_SURVEY), "f.xlsx", "prev"),
			{"row": 3},
		),
		"W-REMOVED": (
			(wb([r for r in PREV_SURVEY if r[1:2] != ["gone"]]), "f.xlsx", "prev"),
			(wb(PREV_SURVEY), "f.xlsx", "prev"),
			{},
		),
		"I-NO-LABEL": (
			(simple(["text", "a", None]), "f.xlsx", None),
			(simple(["text", "a", "A"]), "f.xlsx", None),
			{"row": 2},
		),
	}


def run(spec):
	content, filename, opts = spec
	if opts == "prev":
		opts = ValidateOptions(previous_meta=prev_meta())
	return validate(content, filename, opts)


class TestIssueCatalogue(unittest.TestCase):
	def test_every_code_has_fixtures(self):
		missing = set(CATALOGUE) - set(cases())
		self.assertEqual(missing, set(), f"codes without a failing/passing fixture: {sorted(missing)}")

	def test_each_code_fires_and_its_fix_passes(self):
		for code, (bad, good, where) in cases().items():
			with self.subTest(code=code):
				result = run(bad)
				hits = [i for i in result.issues if i.code == code]
				self.assertTrue(hits, f"{code} did not fire; got {[i.code for i in result.issues]}")
				for key, value in (where or {}).items():
					self.assertEqual(getattr(hits[0], key), value, f"{code}: {key}")
				issue = hits[0]
				for text in (issue.message, issue.suggestion):
					self.assertIsNone(PLACEHOLDER.search(text), f"{code}: unfilled placeholder in {text!r}")
				self.assertNotIn("Traceback", issue.message)
				fixed = run(good)
				self.assertFalse(
					[i for i in fixed.issues if i.code == code],
					f"{code} still fires on the fixed workbook",
				)

	def test_household_form_is_clean(self):
		result = validate(make_xlsx(**HOUSEHOLD), "hh.xlsx", ValidateOptions(allow_web=False))
		self.assertEqual([(i.code, i.message) for i in result.issues], [])
		self.assertIsNotNone(result.plan)

	def test_all_issues_reported_at_once(self):
		content = simple(
			["selec_one yn", "a", "A", None],
			["text", "b", "B", "${zz} = 1"],
			["integer", "c", "C", "pulldata('a')"],
			header=[*H, "relevant"],
		)
		codes = {i.code for i in validate(content, "f.xlsx").issues}
		self.assertTrue({"E-TYPE-UNKNOWN", "E-REF-UNKNOWN", "E-FN-UNSUPPORTED"} <= codes, codes)

	def test_structure_errors_skip_later_stages_and_say_so(self):
		result = validate(simple(["text", "a b", "A"]), "f.xlsx")
		self.assertTrue(result.skipped)
		self.assertEqual(result.skipped[0]["stage"], 3)
		self.assertIsNone(result.plan)

	def test_macro_workbook_rejected(self):
		codes = {i.code for i in validate(macro_workbook(), "f.xlsx").issues}
		self.assertEqual(codes, {"E-FILE-TYPE"})

	def test_xls_rejected(self):
		codes = {
			i.code for i in validate(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "f.xls").issues
		}
		self.assertEqual(codes, {"E-FILE-TYPE"})

	def test_issue_dict_shape(self):
		result = validate(
			simple(
				["integer", "hh_size", "A"], ["text", "b", "B", "${hh_sise} > 1"], header=[*H, "relevant"]
			),
			"f.xlsx",
		)
		data = next(i for i in result.issues if i.code == "E-REF-UNKNOWN").as_dict()
		self.assertEqual(
			set(data),
			{"code", "severity", "sheet", "row", "column", "cell", "message", "suggestion", "docs_url"},
		)
		self.assertEqual(data["cell"], "D3")
		self.assertIn("hh_size", data["suggestion"])
		self.assertTrue(data["message"].startswith("survey!D3"))
		self.assertTrue(data["docs_url"].endswith("#E-REF-UNKNOWN"))

	def test_pyxform_type_aliases_accepted(self):
		content = simple(
			["begin group", "g", "G"],
			["select one yn", "a", "A"],
			["select multiple yn", "b", "B"],
			["end group"],
		)
		self.assertEqual([i.code for i in validate(content, "f.xlsx").issues if i.severity == "error"], [])

	def test_version_ordering(self):
		self.assertEqual(compare_versions("2026110301", "2026110201"), 1)
		self.assertEqual(compare_versions("2025-03", "2024-12"), 1)
		self.assertEqual(compare_versions("1.10", "1.9"), 1)
		self.assertEqual(compare_versions("2", "2"), 0)
		self.assertEqual(compare_versions("v2", "v10"), -1)
