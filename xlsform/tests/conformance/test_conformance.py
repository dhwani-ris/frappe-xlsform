"""Python, Frappe JavaScript and mForm SDK must agree with ODK on every case.

Runtimes that aren't available are skipped with a reason, never silently passed:
- Node needs ``FRAPPE_APP_PATH`` (the bench's ``apps/frappe``; set automatically inside the
  dev container and CI).
- Dart needs ``XLSFORM_SDK_RESULTS``: a JSON file produced by ``scripts/conformance-dart.sh``.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

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

	def test_mform_sdk_matches_odk(self):
		path = os.environ.get("XLSFORM_SDK_RESULTS")
		if not path or not os.path.exists(path):
			self.skipTest("run scripts/conformance-dart.sh to produce XLSFORM_SDK_RESULTS")
		with open(path) as f:
			self._compare(json.load(f), "mForm SDK")

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
