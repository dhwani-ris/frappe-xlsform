"""Python and Frappe JavaScript must agree with ODK on every case, and every emitted string
must be in the JavaScript profile the mForm SDK reads (``core/expr/profile.py``).

Node needs ``FRAPPE_APP_PATH`` (the bench's ``apps/frappe``; set automatically inside the dev
container and CI); without it the JavaScript run is skipped with a reason, never passed.
The SDK repository can run the same cases itself: ``python -m xlsform.tests.conformance.export``.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from xlsform.core.expr import profile
from xlsform.tests.conformance import harness

CASES = harness.load_cases()
RESULTS = harness.build(CASES)
BY_ID = {c["id"]: c for c in CASES}


def _frappe_app_path() -> str | None:
	path = os.environ.get("FRAPPE_APP_PATH")
	if path and os.path.isdir(path):
		return path
	guess = os.path.expanduser("~/bench/frappe-bench/apps/frappe")
	return guess if os.path.isdir(guess) else None


class TestConformance(unittest.TestCase):
	def test_enough_cases(self):
		self.assertGreaterEqual(len(CASES), 300, "REQUIREMENTS.md section 6.4 asks for 300+ cases")

	def test_python_matches_odk(self):
		failures = []
		for case in CASES:
			if "expected" in case:
				got = RESULTS["python"][case["id"]]
				if got != case["expected"]:
					failures.append(f"{case['id']}: {case['expr']} -> {got}, ODK {case['expected']}")
			if "expected_value" in case:
				got = RESULTS["python"][case["id"]]
				if got != case["expected_value"]:
					failures.append(
						f"{case['id']}: {case['expr']} -> {got!r}, ODK {case['expected_value']!r}"
					)
		self.assertEqual(failures, [], "\n".join(failures))

	def test_not_live_rejected(self):
		failures = []
		for case in CASES:
			if case.get("not_live"):
				codes = RESULTS["validation"][case["id"]]
				if not codes & {"E-EXPR-NOT-LIVE", "E-CALC-NOT-LIVE"}:
					failures.append(
						f"{case['id']}: {case['expr']} was accepted in relevant ({sorted(codes)})"
					)
		self.assertEqual(failures, [], "\n".join(failures))

	def test_frappe_javascript_matches_odk(self):
		app = _frappe_app_path()
		node = shutil.which("node")
		if not app or not node:
			self.skipTest("node and the Frappe app source are needed (set FRAPPE_APP_PATH)")
		with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
			path = f.name
		harness.write_js_cases(RESULTS, path)
		runner = os.path.join(harness.HERE, "run_js.js")
		out = subprocess.run([node, runner, app, path], capture_output=True, text=True, check=True)
		os.unlink(path)
		self._compare(json.loads(out.stdout), "Frappe JS")

	def test_filter_literals_evaluate_to_themselves_in_frappe(self):
		"""link.js parse_filters runs value.split("eval:")[1] through frappe.utils.eval."""
		app = _frappe_app_path()
		node = shutil.which("node")
		if not app or not node:
			self.skipTest("node and the Frappe app source are needed (set FRAPPE_APP_PATH)")
		cases = harness.filter_literal_cases()
		with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
			json.dump(cases, f, ensure_ascii=False)
			path = f.name
		runner = os.path.join(harness.HERE, "run_js.js")
		out = subprocess.run([node, runner, app, path], capture_output=True, text=True, check=True)
		os.unlink(path)
		got = {r["id"]: r.get("result", r.get("error")) for r in json.loads(out.stdout)}
		self.assertEqual(got, {c["id"]: c["expected"] for c in cases})

	def test_every_emitted_string_is_in_the_sdk_profile(self):
		strings = [c["js"] for c in RESULTS["js_cases"]]
		strings += [c["js"] for c in harness.filter_literal_cases()]
		self.assertGreater(len(strings), 1000)
		outside = [code for code in strings if not profile.is_valid(code)]
		self.assertEqual(outside, [])

	def _compare(self, results: list[dict], runtime: str):
		failures = []
		seen = set()
		for r in results:
			case = BY_ID[r["id"]]
			seen.add(r["id"])
			if "error" in r:
				failures.append(f"{r['id']}: {case['expr']} -> error {r['error']}")
			elif r["result"] != case["expected"]:
				failures.append(f"{r['id']}: {case['expr']} -> {r['result']}, ODK {case['expected']}")
		missing = {c["id"] for c in RESULTS["js_cases"]} - seen
		self.assertFalse(missing, f"{runtime} did not report {sorted(missing)}")
		self.assertEqual(failures, [], f"{runtime} disagrees with ODK:\n" + "\n".join(failures))
