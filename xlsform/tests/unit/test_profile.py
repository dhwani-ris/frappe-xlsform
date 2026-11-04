"""The emitted-JavaScript profile (core/expr/profile.py) accepts what the emitter writes and
nothing that Frappe Desk and the mForm SDK could read differently or that could run code."""

import json
import unittest

from xlsform.core.expr import emit_js, parser, profile
from xlsform.core.validate import validate
from xlsform.tests.workbooks import HOUSEHOLD, make_xlsx

GOOD = [
	'(cstr(doc.a) === "x")',
	'(cstr(doc.n) !== "" && flt(doc.n) > 5)',
	'(doc.m || []).some(r => r.choice === "x")',
	'cstr(doc.t).split(" ").filter(s => s !== "").length',
	"(doc.member || []).length > 0",
	"[1].length",
	'(cstr(doc.a) === "say \\"hi\\" \\\\")',
	'("ev" + "al:window.x=1")',
	"!!((flt(doc.n) / flt(doc.n2)))",
	"(flt(doc.d) > 0.0000001)",
	"(-(-5))",
	"(cint(doc.a) ? true : false)",
	'cstr(parent.x) === ""',
	"null === undefined",
	'in_list(["a"], cstr(doc.a))',
]
BAD = [
	"doc.a = 1",
	"doc.a; window.x = 1",
	"new Date()",
	"`template ${doc.a}`",
	"/re/.test(doc.a)",
	"1e-07 > doc.a",
	"1E5",
	"010 === 8",
	"0x10",
	"1.",
	"doc.a--",
	"--doc.a",
	"doc.a <!-- comment",
	"doc.a // comment",
	"eval:window.x=1",
	'"eval:" + 1',
	"window.x",
	"frappe.session.user",
	"alert(1)",
	"doc.constructor.constructor('alert(1)')()",
	"doc['a']",
	"(doc.a)(1)",
	"doc.a.sort()",
	"r => r",
	"(doc.a || []).some(function (r) { return r })",
	"(doc.a || []).some(doc => doc)",
	"'single'",
	'"tab\there"',
	'"\\n"',
	'"unterminated',
	"typeof doc.a",
	"doc.a ? 1",
	"",
]


class TestProfile(unittest.TestCase):
	def test_accepts_emitter_shapes(self):
		for code in GOOD:
			with self.subTest(code=code):
				profile.check(code)

	def test_rejects_everything_else(self):
		for code in BAD:
			with self.subTest(code=code):
				self.assertFalse(profile.is_valid(code))

	def test_every_eval_string_in_a_compiled_form_fits(self):
		plan = validate(make_xlsx(**HOUSEHOLD), "hh.xlsx").plan
		strings = []
		for dt in plan["doctypes"]:
			for f in dt["fields"]:
				for key in ("depends_on", "mandatory_depends_on", "read_only_depends_on"):
					if str(f.get(key, "")).startswith("eval:"):
						strings.append(f[key][len("eval:") :])
				for flt in json.loads(f.get("link_filters") or "[]"):
					if str(flt[3]).startswith("eval:"):
						strings.append(flt[3][len("eval:") :])
		self.assertGreater(len(strings), 5)
		for code in strings:
			with self.subTest(code=code):
				profile.check(code)

	def test_deep_formulas_stay_in_profile_or_are_not_live(self):
		scope = emit_js.Scope(
			fieldname=lambda p: p.strip("/"), type_of=lambda p: "integer", repeat_of=lambda p: None
		)
		for depth in (10, 40, 97):
			for text in (
				"not(" * depth + "${a} > 1" + ")" * depth,
				"-" * depth + "${a} > 1",
				"${a}" + " + 1" * depth,
			):
				with self.subTest(depth=depth, text=text[:12]):
					ast = parser.parse(text)
					for n in parser.walk(ast):
						if "ref" in n:
							n["ref"] = "/a"
					try:
						code = emit_js.emit(ast, scope)
					except emit_js.NotLive:
						continue
					profile.check(code)
