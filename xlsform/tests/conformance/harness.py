"""Expression conformance harness (REQUIREMENTS.md section 6.4).

Every case in ``cases/*.json`` is checked against the ODK result written in the case:

1. Python — the server evaluator, on the AST the validator stored in ``compiled_meta``;
2. JavaScript — the ``depends_on`` string the compiler emitted, run by ``run_js.js``
   with Frappe's own ``cstr``/``cint``/``flt`` source, as Frappe Desk runs it;
3. Dart — the same string run by the mForm SDK's interpreter (``dart/bin/run.dart``).

Cases go through the real pipeline: each case becomes a probe question in a generated
workbook (``relevant`` for Live cases, ``constraint``/``calculation`` for server-only ones),
so parsing, name resolution, the emitter and the compiler are all exercised.

Case fields: ``id``, ``expr``, ``doc`` (Frappe-shaped values by fieldname), and one of
``expected`` (bool) / ``expected_value`` (string, server-only) / ``not_live`` (true: the
validator must reject the formula in ``relevant``). Optional ``scope: "member"`` with
``row`` evaluates inside a repeat row.
"""

import datetime
import glob
import json
import os

from xlsform.core.engine import calculated_data
from xlsform.core.expr.evaluate import to_bool, to_string
from xlsform.core.validate import ValidateOptions, validate
from xlsform.core.values import MetaIndex
from xlsform.tests.workbooks import make_xlsx

HERE = os.path.dirname(__file__)
TODAY = datetime.date(2026, 11, 3)
NOW = datetime.datetime(2026, 11, 3, 10, 30, 0)

HEADER = ["type", "name", "label", "relevant", "constraint", "calculation"]
BASE_SURVEY = [
	["text", "t", "T"],
	["text", "t2", "T2"],
	["integer", "n", "N"],
	["integer", "n2", "N2"],
	["decimal", "d", "D"],
	["select_one yn", "s", "S"],
	["select_one colors", "s2", "S2"],
	["select_multiple colors", "m", "M"],
	["date", "dt", "Date"],
	["date", "dt2", "Date 2"],
	["acknowledge", "ack", "Ack"],
	["calculate", "c_total", None, None, None, "${n} + ${n2}"],
	["calculate", "c_label", None, None, None, "concat(${t}, '!')"],
	["calculate", "c_age", None, None, None, "int((today() - ${dt}) div 365.25)"],
]
REPEAT_SURVEY = [
	["begin_repeat", "member", "Members"],
	["integer", "age", "Age"],
	["text", "mname", "Name"],
	["select_multiple colors", "likes", "Likes"],
]
CHOICES = [
	["list_name", "name", "label"],
	["yn", "yes", "Yes"],
	["yn", "no", "No"],
	["colors", "red", "Red"],
	["colors", "green", "Green"],
	["colors", "blue", "Blue"],
	["colors", "1", "One"],
	["colors", "10", "Ten"],
]


def load_cases() -> list[dict]:
	cases = []
	for path in sorted(glob.glob(os.path.join(HERE, "cases", "*.json"))):
		with open(path, encoding="utf-8") as f:
			data = json.load(f)
		for case in data["cases"]:
			case["group"] = data["group"]
			cases.append(case)
	ids = [c["id"] for c in cases]
	dupes = {i for i in ids if ids.count(i) > 1}
	if dupes:
		raise ValueError(f"duplicate case ids: {sorted(dupes)}")
	return cases


def _row(*cells) -> list:
	row = list(cells) + [None] * (len(HEADER) - len(cells))
	return row


def _workbook(cases: list[dict], column: str) -> bytes:
	top, inner = [], []
	for i, case in enumerate(cases):
		name = f"p{i}"
		case["_probe"] = name
		cells = {"relevant": None, "constraint": None, "calculation": None}
		cells[column] = case["expr"]
		qtype = "calculate" if column == "calculation" else "text"
		row = _row(
			qtype,
			name,
			None if qtype == "calculate" else "Probe",
			cells["relevant"],
			cells["constraint"],
			cells["calculation"],
		)
		(inner if case.get("scope") == "member" else top).append(row)
	survey = (
		[HEADER]
		+ [_row(*r) for r in BASE_SURVEY]
		+ top
		+ [_row(*r) for r in REPEAT_SURVEY]
		+ inner
		+ [_row("end_repeat")]
	)
	settings = [["form_id", "version"], ["conformance", "1"]]
	return make_xlsx(survey=survey, choices=CHOICES, settings=settings)


def build(cases: list[dict]) -> dict:
	"""Run Python for every case and collect the JS strings for the other runtimes."""
	live = [c for c in cases if "expected" in c and not c.get("server")]
	server = [c for c in cases if c.get("server") and "expected" in c]
	values = [c for c in cases if "expected_value" in c]
	not_live = [c for c in cases if c.get("not_live")]
	results = {"python": {}, "js_cases": [], "validation": {}}

	for group, column in ((live, "relevant"), (server, "constraint"), (values, "calculation")):
		if not group:
			continue
		result = validate(_workbook(group, column), "conformance.xlsx", ValidateOptions(max_questions=100000))
		errors = [i for i in result.issues if i.severity == "error"]
		if errors:
			raise AssertionError(
				"conformance workbook failed validation: " + "; ".join(i.message for i in errors)
			)
		meta = result.plan["compiled_meta"]
		index = MetaIndex(meta)
		fields = {f["path"]: f for f in meta["fields"]}
		doctype_fields = {}
		for dt in result.plan["doctypes"]:
			for f in dt["fields"]:
				doctype_fields[(dt["name"], f["fieldname"])] = f
		for case in group:
			path = ("/member/" if case.get("scope") == "member" else "/") + case["_probe"]
			ast = meta["expressions"][path][column]
			doc = dict(case["doc"])
			self_path = None
			if "self_value" in case:
				self_path = path
				doc[fields[path]["fieldname"]] = case["self_value"]
			data = calculated_data(meta, doc, today=lambda: TODAY, now=lambda: NOW)
			scope_repeat = "/member" if case.get("scope") == "member" else None
			ctx = index.context(
				data,
				scope_repeat=scope_repeat,
				row=case.get("row"),
				self_path=self_path,
				today=lambda: TODAY,
				now=lambda: NOW,
			)
			from xlsform.core.expr.evaluate import evaluate

			value = evaluate(ast, ctx)
			results["python"][case["id"]] = to_string(value) if column == "calculation" else to_bool(value)
			if column == "relevant":
				f = fields[path]
				docfield = doctype_fields[(f["doctype"], f["fieldname"])]
				js = docfield["depends_on"][len("eval:") :]
				doc = case["doc"]
				parent = None
				if scope_repeat:
					parent = doc
					doc = (doc.get("member") or [])[case.get("row", 0)]
				results["js_cases"].append({"id": case["id"], "js": js, "doc": doc, "parent": parent})

	if not_live:
		for case in not_live:
			result = validate(_workbook([case], "relevant"), "conformance.xlsx")
			codes = {i.code for i in result.issues}
			results["validation"][case["id"]] = codes
	return results


FILTER_LITERALS = [
	"d1",
	"eval:window.x=1",
	"a eval:b eval:c",
	'say "hi" \\ bye',
	"' + alert(1) + '",
	"हाँ",
	"eval:",
]


def filter_literal_cases() -> list[dict]:
	"""Each literal in a choice_filter, as Frappe's link.js would evaluate the compiled value."""
	survey = [["type", "name", "label", "choice_filter"]]
	choices = [["list_name", "name", "label", "region"]]
	for i, text in enumerate(FILTER_LITERALS):
		quote = '"' if "'" in text else "'"
		survey.append([f"select_one l{i}", f"q{i}", "Q", f"region = {quote}{text}{quote}"])
		choices.append([f"l{i}", "c1", "C1", text])
	content = make_xlsx(survey=survey, choices=choices, settings=[["form_id"], ["filters_form"]])
	result = validate(content, "filters.xlsx", ValidateOptions(allow_web=False))
	errors = [i.message for i in result.issues if i.severity == "error"]
	if errors:
		raise AssertionError("; ".join(errors))
	parent = result.plan["doctypes"][-1]["fields"]
	cases = []
	for i, text in enumerate(FILTER_LITERALS):
		field = next(f for f in parent if f["fieldname"] == f"q{i}")
		value = json.loads(field["link_filters"])[1][3]
		code = value.split("eval:")[1] if value.startswith("eval:") else None
		cases.append({"id": f"filter-{i}", "js": code, "doc": {}, "value": True, "expected": text})
	return cases


def write_js_cases(results: dict, path: str) -> None:
	with open(path, "w", encoding="utf-8") as f:
		json.dump(results["js_cases"], f, ensure_ascii=False)
