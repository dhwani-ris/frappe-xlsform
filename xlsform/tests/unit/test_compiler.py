"""compile_form() is pure, so every rule in REQUIREMENTS.md section 5 is tested without a site."""

import io
import json
import unittest

from openpyxl import load_workbook

from xlsform.core import annotate, naming, preview, template
from xlsform.core.compiler import FIXED_ROW_BYTES, row_bytes
from xlsform.core.expr import emit_js, parser
from xlsform.core.validate import ValidateOptions, validate
from xlsform.tests.workbooks import HOUSEHOLD, make_xlsx

H = ["type", "name", "label"]


def plan_for(survey, choices=None, settings=None, **opts):
	settings = settings or [["form_title", "form_id", "version"], ["Test Form", "test_form", "1"]]
	result = validate(make_xlsx(survey=survey, choices=choices, settings=settings), "f.xlsx", ValidateOptions(**opts))
	assert result.plan, [(i.code, i.message) for i in result.issues if i.severity == "error"]
	return result.plan


def fields(plan, doctype=None):
	dt = plan["doctypes"][-1] if doctype is None else next(d for d in plan["doctypes"] if d["name"] == doctype)
	return {f["fieldname"]: f for f in dt["fields"]}


class TestNaming(unittest.TestCase):
	def test_sanitize_rules(self):
		taken = set()
		self.assertEqual(naming.sanitize("Hh-Size.v2", "/a", taken), "hh_size_v2")
		self.assertEqual(naming.sanitize("2nd", "/b", taken), "f_2nd")
		self.assertEqual(naming.sanitize("name", "/c", taken), "name_q")
		self.assertEqual(naming.sanitize("select", "/d", taken), "select_q")  # MariaDB
		self.assertEqual(naming.sanitize("class", "/e", taken), "class_q")  # JavaScript
		self.assertEqual(naming.sanitize("xf_form", "/f", taken), "xf_form_q")  # reserved prefix
		long = naming.sanitize("a" * 70, "/g", taken)
		self.assertEqual(len(long), 58)
		self.assertTrue(long.startswith("a" * 51 + "_"))
		self.assertEqual(naming.sanitize("hh_size", "/h", taken), "hh_size")
		self.assertEqual(naming.sanitize("hh_size", "/i", taken), "hh_size_2")  # collision

	def test_reserved_extra(self):
		self.assertEqual(naming.sanitize("save", "/a", set(), {"save"}), "save_q")

	def test_doctype_names(self):
		taken = {"XF Household Survey"}
		self.assertEqual(naming.doctype_name("XF", "Household Survey", taken), "XF Household Survey 2")
		self.assertEqual(len(naming.doctype_name("XF", "x" * 100, set())), 61)
		self.assertEqual(naming.parent_label("सर्वे", "hh"), "hh")
		self.assertEqual(naming.parent_label("Survey: 2026!", "hh"), "hh")
		self.assertEqual(naming.parent_label("Survey 2026", "hh"), "Survey 2026")


class TestCompiler(unittest.TestCase):
	def test_household_plan_snapshot(self):
		plan = validate(make_xlsx(**HOUSEHOLD), "hh.xlsx", ValidateOptions(allow_web=False)).plan
		names = [d["name"] for d in plan["doctypes"]]
		self.assertEqual(
			names,
			[
				"XF hh_survey yes_no",
				"XF hh_survey district",
				"XF hh_survey village",
				"XF hh_survey services",
				"XF hh_survey services pick",
				"XF hh_survey member",
				"XF Household Survey",
			],
		)
		f = fields(plan)
		self.assertEqual(f["consent"]["reqd"], 1)
		self.assertEqual(f["hh_head"]["mandatory_depends_on"], 'eval:(cstr(doc.consent) === "yes")')
		self.assertEqual(f["xf_s_hh"]["fieldtype"], "Section Break")
		self.assertEqual(f["services"]["fieldtype"], "Table MultiSelect")
		self.assertEqual(f["n_members"]["hidden"], 1)
		self.assertEqual(f["summary"]["depends_on"], "eval:(doc.member || []).length > 0")
		self.assertEqual(
			json.loads(f["village"]["link_filters"]),
			[
				["XF hh_survey village", "xf_retired", "=", 0],
				["XF hh_survey village", "district", "=", "eval:cstr(doc.district)"],
			],
		)
		child = fields(plan, "XF hh_survey member")
		self.assertEqual(
			child["m_school"]["depends_on"],
			'eval:((cstr(doc.m_age) !== "" && flt(doc.m_age) >= 5) && (cstr(doc.m_age) !== "" && flt(doc.m_age) <= 18))',
		)
		self.assertEqual(plan["doctypes"][-1]["autoname"], "format:HH_SURVEY-{#####}")
		village = plan["choices"]["XF hh_survey village"]
		self.assertEqual(village[0], {"choice_name": "v1", "label": "Village A", "xf_order": 1, "xf_retired": 0, "district": "d1"})
		self.assertIn(
			{"language": "Hindi (hi)", "source_text": "Household size", "translated_text": "परिवार का आकार", "context": "XF Household Survey"},
			plan["translations"],
		)
		meta = plan["compiled_meta"]
		self.assertEqual(meta["calc_order"], ["/n_members", "/total_age"])
		self.assertEqual(meta["languages"], ["English (en)", "Hindi (hi)"])

	def test_tabs_for_many_groups(self):
		survey = [H]
		for g in range(4):
			survey += [["begin_group", f"g{g}", f"Group {g}"], ["text", f"q{g}", "Q"], ["end_group"]]
		survey.append(["text", "after", "After"])
		f = plan_for(survey)["doctypes"][-1]["fields"]
		kinds = [x["fieldtype"] for x in f if x["fieldtype"].endswith("Break")]
		self.assertEqual(kinds, ["Tab Break"] * 5)

	def test_nested_group_labels_and_conditions(self):
		survey = [
			[*H, "relevant"],
			["integer", "a", "A", None],
			["begin_group", "outer", "Household", "${a} > 1"],
			["begin_group", "inner", "Assets", "${a} > 2"],
			["text", "q", "Q", None],
			["end_group"],
			["end_group"],
			["text", "after", "After", None],
		]
		f = fields(plan_for(survey))
		self.assertEqual(f["xf_s_inner"]["label"], "Household › Assets")
		self.assertIn("&&", f["q"]["depends_on"])
		self.assertNotIn("depends_on", f["after"])
		self.assertTrue(any(k.startswith("xf_sb_") for k in f))

	def test_select_link_length_and_defaults(self):
		survey = [[*H, "default"], ["select_one long", "s", "S", "x" * 25], ["date", "d", "D", "today()"], ["acknowledge", "k", "K", "OK"]]
		choices = [["list_name", "name", "label"], ["long", "x" * 25, "X"]]
		f = fields(plan_for(survey, choices))
		self.assertEqual(f["s"]["length"], 40)
		self.assertEqual(f["s"]["default"], "x" * 25)
		self.assertEqual(f["d"]["default"], "Today")
		self.assertEqual(f["k"]["default"], "1")

	def test_long_label_moves_to_description(self):
		long = "word " * 60
		f = fields(plan_for([[*H, "hint"], ["text", "q", long, "Hint text"]]))
		self.assertLessEqual(len(f["q"]["label"]), 140)
		self.assertTrue(f["q"]["label"].endswith("…"))
		self.assertIn("Hint text", f["q"]["description"])

	def test_metadata_and_hidden_types(self):
		survey = [H, ["start", "start", None], ["username", "who", None], ["hidden", "h", None], ["calculate", "c", "Shown", ], ["text", "x", "X"]]
		survey[4] = ["calculate", "c", "Shown"]
		f = fields(plan_for([[*H, "calculation"], *[r + [None] for r in survey[1:4]], ["calculate", "c", "Shown", "1 + 1"], ["text", "x", "X", None]]))
		self.assertEqual(f["start"]["read_only"], 1)
		self.assertEqual(f["who"]["fieldtype"], "Data")
		self.assertEqual(f["h"]["hidden"], 1)
		self.assertNotIn("hidden", f["c"])  # a labelled calculate is shown read-only

	def test_range_parameters(self):
		f = fields(plan_for([[*H, "parameters"], ["range", "r", "R", "start=0 end=1 step=0.5"], ["range", "i", "I", None]]))
		self.assertEqual(f["r"]["fieldtype"], "Float")
		self.assertEqual(f["i"]["fieldtype"], "Int")
		self.assertEqual(f["r"]["non_negative"], 1)

	def test_instance_name_autoname(self):
		plan = plan_for(
			[H, ["text", "village", "V"], ["text", "head", "H"]],
			settings=[["form_id", "instance_name"], ["abc_form", "concat(${village}, '-', ${head})"]],
		)
		self.assertEqual(plan["doctypes"][-1]["autoname"], "format:{village}-{head}-{#####}")

	def test_row_budget(self):
		survey = [H] + [["barcode", f"b{i}", "B"] for i in range(5)]
		plan = plan_for(survey)
		total = row_bytes(plan["doctypes"][-1]["fields"])
		self.assertEqual(total, FIXED_ROW_BYTES + 258 + 482 + 42 + 5 * 562)

	def test_web_form_spec(self):
		plan = plan_for([H, ["select_multiple yn", "m", "M"], ["geopoint", "g", "G"], ["text", "t", "T"]],
			choices=[["list_name", "name", "label"], ["yn", "y", "Y"]])
		types = {f["fieldname"]: f["fieldtype"] for f in plan["web_form"]["fields"]}
		self.assertEqual(types, {"m": "Table", "t": "Small Text"})
		self.assertEqual(plan["web_form"]["route"], "xf/test-form")


class TestRepublish(unittest.TestCase):
	SURVEY = [H, ["text", "a", "A"], ["integer", "b", "B"], ["select_one yn", "c", "C"]]
	CHOICES = [["list_name", "name", "label"], ["yn", "yes", "Yes"], ["yn", "no", "No"]]

	def publish(self, survey, choices, version, prev=None):
		settings = [["form_title", "form_id", "version"], ["Test Form", "test_form", version]]
		r = validate(make_xlsx(survey=survey, choices=choices, settings=settings), "f.xlsx", ValidateOptions(previous_meta=prev))
		assert r.plan, [i.message for i in r.issues if i.severity == "error"]
		return r

	def test_evolution(self):
		v1 = self.publish(self.SURVEY, self.CHOICES, "1").plan["compiled_meta"]
		survey = [H, ["integer", "a", "A"], ["select_one yn", "c", "C"], ["text", "d", "D"]]
		choices = [*self.CHOICES, ["yn", "maybe_not_sure_long_name_xx", "Maybe"]]
		r2 = self.publish(survey, choices, "2", v1)
		f = fields(r2.plan)
		self.assertEqual(f["a"]["fieldtype"], "Small Text")  # old column kept
		self.assertEqual(f["a"]["hidden"], 1)
		self.assertEqual(f["a_v2"]["fieldtype"], "Int")  # new column for the new type
		self.assertEqual(f["b"]["hidden"], 1)  # removed question kept hidden
		self.assertEqual(f["c"]["length"], 40)  # widened for the longer choice
		self.assertIn("d", f)
		self.assertEqual(r2.change_summary["removed"], ["b"])
		self.assertEqual(r2.change_summary["type_changed"], [{"name": "a", "from": "text", "to": "integer"}])
		meta2 = r2.plan["compiled_meta"]
		b = next(x for x in meta2["fields"] if x["path"] == "/b")
		self.assertEqual(b["retired_in"], "2")
		self.assertEqual(meta2["doctypes"], {**v1["doctypes"], "lists": v1["doctypes"]["lists"]})

		# version 3 keeps names stable and never resurrects retired columns under a new name
		r3 = self.publish(survey, choices, "3", meta2)
		self.assertEqual(fields(r3.plan)["a_v2"]["fieldtype"], "Int")
		self.assertEqual(sum(1 for x in r3.plan["compiled_meta"]["fields"] if x["path"] == "/b"), 1)

	def test_doctype_names_frozen(self):
		v1 = self.publish(self.SURVEY, self.CHOICES, "1").plan["compiled_meta"]
		settings = [["form_title", "form_id", "version"], ["Renamed Title", "test_form", "2"]]
		r = validate(make_xlsx(survey=self.SURVEY, choices=self.CHOICES, settings=settings), "f.xlsx", ValidateOptions(previous_meta=v1))
		self.assertEqual(r.plan["doctypes"][-1]["name"], "XF Test Form")


class TestEmitterSafety(unittest.TestCase):
	def scope(self):
		return emit_js.Scope(fieldname=lambda p: p.strip("/"), type_of=lambda p: "text", repeat_of=lambda p: None)

	def emit(self, text):
		ast = parser.parse(text)
		for n in parser.walk(ast):
			if "ref" in n:
				n["ref"] = "/" + n["name"]
		return emit_js.emit(ast, self.scope())

	def test_quotes_and_backslashes_cannot_break_out(self):
		js = self.emit("${a} = 'x\" + alert(1) + \"'")
		self.assertEqual(js, '(cstr(doc.a) === "x\\" + alert(1) + \\"")')
		self.assertEqual(self.emit("${a} = 'end\\'"), '(cstr(doc.a) === "end\\\\")')

	def test_control_characters_are_not_live(self):
		with self.assertRaises(emit_js.NotLive):
			self.emit("${a} = 'line\nbreak'")
		with self.assertRaises(emit_js.NotLive):
			emit_js.js_string("tab\there")

	def test_unicode_is_raw(self):
		self.assertEqual(self.emit("${a} = 'हाँ'"), '(cstr(doc.a) === "हाँ")')

	def test_parser_rejects_paths_and_unknown_characters(self):
		for bad in ("/data/x = 1", "${a} | ${b}", "${a} ; 1", "${a", "if(1,2", "1 +", "${}"):
			with self.subTest(bad=bad), self.assertRaises(parser.ExprSyntaxError):
				parser.parse(bad)


class TestArtifacts(unittest.TestCase):
	def test_template_is_clean(self):
		r = validate(template.build(), "starter.xlsx", ValidateOptions(allow_web=False))
		self.assertEqual([(i.code, i.message) for i in r.issues], [])

	def test_annotate_marks_cells_and_lists_issues(self):
		survey = [[*H, "relevant"], ["integer", "a", "A", None], ["text", "b", "B", "${aa} > 1"], ["text", "c", None, None]]
		content = make_xlsx(survey=survey)
		r = validate(content, "f.xlsx")
		out = load_workbook(io.BytesIO(annotate.annotate(content, r.issues, "2026110301")))
		cell = out["survey"]["D3"]
		self.assertIn("E-REF-UNKNOWN", cell.comment.text)
		self.assertEqual(cell.fill.fgColor.rgb[-6:], "FFC7CE")
		self.assertEqual(out["settings"]["A2"].value, "2026110301")
		report = list(out["xlsform_report"].iter_rows(values_only=True))
		self.assertEqual(len(report), 1 + len(r.issues))

	def test_preview_payload(self):
		plan = validate(make_xlsx(**HOUSEHOLD), "hh.xlsx").plan
		p = preview.build(plan)
		by = {f["fieldname"]: f for f in p["fields"]}
		self.assertNotIn("xf_form", by)
		self.assertEqual(by["consent"]["fieldtype"], "Autocomplete")
		self.assertEqual(by["consent"]["options"][0], {"value": "yes", "label": "Yes"})
		self.assertEqual(by["services"]["fieldtype"], "Table")
		self.assertEqual(by["services"]["fields"][0]["fieldname"], "choice")
		self.assertEqual(by["member"]["fieldtype"], "Table")
		self.assertIn("m_age", {f["fieldname"] for f in by["member"]["fields"]})


class TestCompilerRules(unittest.TestCase):
	def test_required_and_read_only_rules(self):
		survey = [
			[*H, "required", "read_only"],
			["integer", "a", "A", None, None],
			["text", "b", "B", "${a} > 1", "${a} > 5"],
			["text", "c", "C", None, "yes"],
		]
		f = fields(plan_for(survey))
		self.assertEqual(f["b"]["mandatory_depends_on"], 'eval:(cstr(doc.a) !== "" && flt(doc.a) > 1)')
		self.assertEqual(f["b"]["read_only_depends_on"], 'eval:(cstr(doc.a) !== "" && flt(doc.a) > 5)')
		self.assertEqual(f["c"]["read_only"], 1)

	def test_required_inside_relevant_group(self):
		survey = [
			[*H, "required", "relevant"],
			["integer", "a", "A", None, None],
			["begin_group", "g", "G", None, "${a} > 1"],
			["text", "b", "B", "${a} > 3", None],
			["end_group", None, None, None, None],
		]
		f = fields(plan_for(survey))
		self.assertEqual(
			f["b"]["mandatory_depends_on"],
			'eval:((cstr(doc.a) !== "" && flt(doc.a) > 1) && (cstr(doc.a) !== "" && flt(doc.a) > 3))',
		)

	def test_literal_choice_filter_values(self):
		survey = [[*H, "choice_filter"], ["select_one v", "v", "V", "district = 'd1' and name != ''"]]
		choices = [["list_name", "name", "label", "district"], ["v", "v1", "V1", "d1"]]
		r = validate(make_xlsx(survey=survey, choices=choices), "test_form.xlsx")
		self.assertIn("E-FILTER-UNSUPPORTED", {i.code for i in r.issues})
		survey = [[*H, "choice_filter"], ["select_one v", "v", "V", "district = 'd1' and type = 2"]]
		choices = [["list_name", "name", "label", "district", "type"], ["v", "v1", "V1", "d1", "2"]]
		f = fields(plan_for(survey, choices))
		filters = json.loads(f["v"]["link_filters"])
		self.assertEqual(filters[1][3], "d1")
		self.assertEqual(filters[2][3], "2")

	def test_group_inside_group_spacer_keeps_conditions(self):
		survey = [
			[*H, "relevant"],
			["integer", "a", "A", None],
			["begin_group", "outer", "Outer", "${a} > 1"],
			["begin_group", "inner", "Inner", None],
			["text", "q", "Q", None],
			["end_group"],
			["text", "after_inner", "After inner", None],
			["end_group"],
		]
		f = fields(plan_for(survey))
		spacer = next(v for k, v in f.items() if k.startswith("xf_sb_"))
		self.assertEqual(spacer["depends_on"], 'eval:(cstr(doc.a) !== "" && flt(doc.a) > 1)')
		self.assertEqual(spacer["label"], "Outer")

	def test_hint_and_note_translations(self):
		survey = [[*H, "hint", "label::Hindi (hi)", "hint::Hindi (hi)"], ["text", "q", "Name", "Full name", "नाम", "पूरा नाम"], ["note", "n", "Hello", None, "नमस्ते", None]]
		plan = plan_for(survey)
		texts = {(t["source_text"], t["translated_text"]) for t in plan["translations"]}
		self.assertIn(("Full name", "पूरा नाम"), texts)
		self.assertIn(("<p>Hello</p>", "<p>नमस्ते</p>"), texts)

	def test_retired_select_and_repeat_keep_their_targets(self):
		v1 = [H, ["select_one yn", "s", "S"], ["select_multiple yn", "m", "M"], ["begin_repeat", "r", "R"], ["text", "x", "X"], ["end_repeat"], ["begin_group", "g", "G"], ["text", "y", "Y"], ["end_group"]]
		choices = [["list_name", "name", "label"], ["yn", "y", "Y"]]
		settings = [["form_id", "version"], ["test_form", "1"]]
		p1 = validate(make_xlsx(survey=v1, choices=choices, settings=settings), "f.xlsx").plan
		v2 = [H, ["text", "t", "T"], ["begin_group", "g", "G"], ["text", "y", "Y"], ["end_group"]]
		settings2 = [["form_id", "version"], ["test_form", "2"]]
		p2 = validate(make_xlsx(survey=v2, settings=settings2), "f.xlsx", ValidateOptions(previous_meta=p1["compiled_meta"])).plan
		f = fields(p2)
		self.assertEqual((f["s"]["fieldtype"], f["s"]["options"], f["s"]["hidden"]), ("Link", "XF test_form yn", 1))
		self.assertEqual(f["m"]["options"], "XF test_form yn pick")
		self.assertEqual(f["r"]["options"], "XF test_form r")
		self.assertEqual(f["xf_s_g"]["fieldtype"], "Section Break")  # section name reused
		self.assertIn("XF test_form yn", [d["name"] for d in p2["doctypes"]])  # list still synced

	def test_instance_name_falls_back_for_unknown_parts(self):
		plan = plan_for([H, ["text", "a", "A"]], settings=[["form_id", "instance_name"], ["abc_form", "concat(${a}, ${zz})"]])
		self.assertEqual(plan["doctypes"][-1]["autoname"], "format:ABC_FORM-{#####}")
