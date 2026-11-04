"""Server rules for one record (REQUIREMENTS.md section 8), without a site."""

import datetime
import math
import re
import time
import unittest

from xlsform.core import engine
from xlsform.core.expr.evaluate import Context, evaluate
from xlsform.core.expr.parser import parse, walk
from xlsform.core.validate import validate
from xlsform.core.values import answer
from xlsform.tests.workbooks import HOUSEHOLD, make_xlsx

META = validate(make_xlsx(**HOUSEHOLD), "hh.xlsx").plan["compiled_meta"]
GOOD = {
	"consent": "yes",
	"hh_head": "Asha",
	"hh_size": 2,
	"district": "d1",
	"village": "v1",
	"services": [{"choice": "health"}],
	"health_detail": "x",
	"ack": 1,
	"member": [{"m_name": "A", "m_age": 30}, {"m_name": "B", "m_age": 9}],
}
CHOICES = {"v1": {"district": "d1"}, "v2": {"district": "d1"}, "v3": {"district": "d2"}}


def lookup(list_name, choice):
	return CHOICES.get(choice) if list_name == "village" else {}


def run(doc, **kw):
	return engine.run(META, doc, choice_lookup=lookup, **kw)


class TestEngine(unittest.TestCase):
	def test_good_record(self):
		out = run(GOOD)
		self.assertEqual(out.failures, [])
		self.assertEqual(out.parent_updates["n_members"], "2")
		self.assertEqual(out.parent_updates["total_age"], "39")

	def test_required_and_constraint_messages(self):
		out = run({**GOOD, "hh_size": 50, "hh_head": None})
		messages = {f.label: f.message for f in out.failures}
		self.assertEqual(messages["Household size"], "Between 1 and 39")
		self.assertEqual(messages["Head of household"], "Head of household is required.")

	def test_non_relevant_cleared_and_not_required(self):
		out = run({"consent": "no", "hh_head": "Asha", "services": [{"choice": "health"}], "ack": 1})
		self.assertEqual(out.failures, [])
		self.assertIsNone(out.parent_updates["hh_head"])
		self.assertEqual(out.parent_updates["services"], [])

	def test_repeat_rows(self):
		out = run({**GOOD, "member": [{"m_name": "A", "m_age": 200}, {"m_name": None, "m_age": 3}]})
		rows = sorted((f.row, f.label, f.repeat_label) for f in out.failures)
		self.assertEqual(rows, [(0, "Age", "Members"), (1, "Name", "Members")])

	def test_repeat_relevance_clears_rows(self):
		doc = {**GOOD, "hh_size": 0, "member": [{"m_name": "A", "m_age": 3}]}
		out = run(doc)
		self.assertEqual(out.parent_updates["member"], [])

	def test_choice_filter_on_server(self):
		out = run({**GOOD, "village": "v3"})
		self.assertEqual([f.kind for f in out.failures], ["choice"])

	def test_acknowledge_required(self):
		out = run({**GOOD, "ack": 0})
		self.assertEqual([f.label for f in out.failures], ["I confirm the answers are correct"])

	def test_language_of_messages(self):
		out = run({**GOOD, "hh_head": None}, language="Hindi (hi)")
		self.assertEqual(out.failures[0].label, "परिवार का मुखिया")

	def test_nan_calculation_stored_blank(self):
		meta = validate(
			make_xlsx(
				survey=[
					["type", "name", "label", "calculation"],
					["integer", "a", "A", None],
					["calculate", "c", None, "${a} + 1"],
				]
			),
			"f.xlsx",
		).plan["compiled_meta"]
		self.assertEqual(engine.run(meta, {"a": None}).parent_updates["c"], "")
		self.assertEqual(engine.run(meta, {"a": 2}).parent_updates["c"], "3")

	def test_range_and_repeat_count(self):
		survey = [
			["type", "name", "label", "parameters", "repeat_count"],
			["range", "r", "R", "start=0 end=10 step=2", None],
			["integer", "n", "N", None, None],
			["begin_repeat", "kids", "Kids", None, "${n}"],
			["text", "k", "K", None, None],
			["end_repeat", None, None, None, None],
		]
		meta = validate(make_xlsx(survey=survey), "f.xlsx").plan["compiled_meta"]
		kinds = sorted(f.kind for f in engine.run(meta, {"r": 3, "n": 2, "kids": [{"k": "a"}]}).failures)
		self.assertEqual(kinds, ["range", "repeat_count"])
		self.assertEqual(engine.run(meta, {"r": 4, "n": 1, "kids": [{"k": "a"}]}).failures, [])

	def test_once_and_uuid(self):
		ctx = Context(data={"/x": "kept"}, self_path="/x")
		self.assertEqual(evaluate(parse("once(uuid())"), ctx), "kept")
		ctx = Context(data={"/x": ""}, self_path="/x")
		self.assertEqual(len(evaluate(parse("once(uuid())"), ctx)), 36)
		self.assertEqual(len(evaluate(parse("uuid(8)"), Context(data={}))), 8)


def ev(text, data=None, self_path=None):
	ast = parse(text)
	for node in walk(ast):
		if "ref" in node:
			node["ref"] = "/" + node["name"]
	return evaluate(ast, Context(data=data or {}, self_path=self_path))


class TestCollectorDataCantSlowASave(unittest.TestCase):
	"""Answers are untrusted: no function may take seconds or crash on them."""

	def assertFast(self, text, data=None, self_path=None, limit=0.5):
		start = time.monotonic()
		value = ev(text, data, self_path)
		self.assertLess(time.monotonic() - start, limit, text)
		return value

	def test_regex_refuses_unsafe_patterns_and_long_text(self):
		data = {"/x": "a" * 30 + "!"}
		self.assertFalse(self.assertFast("regex(., '^([a-zA-Z0-9]+\\s?)*$')", data, "/x"))
		self.assertFalse(self.assertFast("regex(., 'x.*y.*z')", {"/x": "xy" * 500}, "/x"))
		self.assertTrue(self.assertFast("regex(., '^[a-z]+!$')", data, "/x"))
		self.assertFalse(ev("regex(., 'a')", {"/x": "a" * 5000}, "/x"))

	def test_regex_matcher_agrees_with_python(self):
		import random

		from xlsform.core.expr.regex_safety import safe_search, unsafe_reason

		patterns = [
			r"^[0-9]{10}$",
			r"^[a-z0-9._]+@[a-z0-9.-]+\.[a-z]{2,}$",
			r"^(yes|no)+$",
			r"^\d+(\.\d{1,2})?$",
			r"\bab\B",
			r"^a?b{2,3}c*$",
			r"(ab|cd){1,3}e",
			r"[^a-c]+x",
			r"\w+\s\w+",
			r"a|b|",
		]
		rng = random.Random(7)
		for pattern in patterns:
			self.assertIsNone(unsafe_reason(pattern), pattern)
			for _ in range(500):
				text = "".join(rng.choice("abcde019.@ \nAB_") for _ in range(rng.randint(0, 12)))
				self.assertEqual(
					safe_search(pattern, text), re.search(pattern, text) is not None, (pattern, text)
				)

	def test_huge_arguments_are_bounded(self):
		self.assertEqual(self.assertFast("round(1.23456, 300000000)"), 1.23456)
		self.assertEqual(self.assertFast("round(1234.5, -300000000)"), 1235.0)
		self.assertEqual(len(self.assertFast("uuid(100000000)")), 64)
		self.assertEqual(len(self.assertFast("uuid(0)")), 1)
		self.assertTrue(math.isinf(self.assertFast("pow(10, 1000000000)")))
		self.assertEqual(self.assertFast("substr('abc', 1 div 0)"), "")
		self.assertEqual(self.assertFast("substr('abc', -1 div 0, 1 div 0)"), "abc")
		self.assertEqual(self.assertFast("substr('abc', 0 div 0)"), "abc")
		self.assertEqual(self.assertFast("date(1 div 0)"), "")
		self.assertEqual(self.assertFast("date(100000000000)"), "")
		self.assertEqual(self.assertFast("format-date(1 div 0, '%Y')"), "")
		self.assertEqual(self.assertFast("date('2026-13-45')"), "")
		self.assertEqual(self.assertFast("int(1 div 0)"), math.inf)

	def test_repeat_count_overflow_is_a_failure(self):
		survey = [
			["type", "name", "label", "repeat_count"],
			["integer", "a", "A", None],
			["integer", "b", "B", None],
			["begin_repeat", "kids", "Kids", "${a} div ${b}"],
			["text", "k", "K", None],
			["end_repeat", None, None, None],
		]
		meta = validate(make_xlsx(survey=survey), "f.xlsx").plan["compiled_meta"]
		for b in (0, None):
			out = engine.run(meta, {"a": 1, "b": b, "kids": [{"k": "x"}]})
			self.assertEqual([f.kind for f in out.failures], ["repeat_count"] if b == 0 else [])
		out = engine.run(meta, {"a": 10**300, "b": 10**-300, "kids": []})
		self.assertEqual([f.kind for f in out.failures], ["repeat_count"])


class TestValues(unittest.TestCase):
	def test_answers(self):
		self.assertEqual(answer("integer", None), "")
		self.assertEqual(answer("integer", 3), 3.0)
		self.assertEqual(answer("select_multiple", [{"choice": "a"}, {"choice": "b"}]), "a b")
		self.assertEqual(answer("acknowledge", 1), "OK")
		self.assertEqual(answer("date", datetime.date(2026, 1, 2)), "2026-01-02")
		geo = '{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[73.8,18.5]}}]}'
		self.assertEqual(answer("geopoint", geo), "18.5 73.8 0 0")
