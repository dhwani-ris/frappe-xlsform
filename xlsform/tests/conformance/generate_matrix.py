"""Generate cases/matrix.json: every comparison operator against every kind of answer.

The expected results come from ``odk()`` below: a deliberately tiny, independent statement
of the XPath 1.0 / JavaRosa comparison rules, so the evaluator under test is never its own
oracle. Re-run after changing the matrix: ``python -m xlsform.tests.conformance.generate_matrix``.
"""

import json
import math
import os

OPS = ["=", "!=", "<", "<=", ">", ">="]
FIELDS = {
	# field -> (XLSForm kind, values as stored by Frappe; None = unanswered)
	"n": ("number", [None, 0, 5, 7, -2]),
	"d": ("number", [None, 2.5, 5.0]),
	"t": ("text", [None, "", "5", "7", "abc", " 5", "5.0", "1,000", "5abc"]),
	"s2": ("text", [None, "1", "10", "red"]),
}
LITERALS = [("5", 5.0), ("0", 0.0), ("-2", -2.0), ("2.5", 2.5), ("'5'", "5"), ("''", ""), ("'red'", "red")]


def odk(op, kind, value, lit):
	# the answer as XPath sees it: unanswered is "", numbers are numbers, text is text
	a = "" if value is None or value == "" else (float(value) if kind == "number" else value)
	b = lit

	def num(x):
		if isinstance(x, float):
			return x
		try:
			return float(x) if x.strip() else math.nan
		except ValueError:
			return math.nan

	if op in ("=", "!="):
		if isinstance(a, float) or isinstance(b, float):
			eq = num(a) == num(b)
		else:
			eq = a == b
		return eq if op == "=" else not eq
	x, y = num(a), num(b)
	if math.isnan(x) or math.isnan(y):
		return False
	return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]


def cases():
	out = []
	for field, (kind, values) in FIELDS.items():
		for vi, value in enumerate(values):
			for lit_text, lit in LITERALS:
				for op in OPS:
					expr = f"${{{field}}} {op} {lit_text}"
					out.append(
						{
							"id": f"mx-{field}-{vi}-{OPS.index(op)}-{LITERALS.index((lit_text, lit))}",
							"expr": expr,
							"doc": {field: value},
							"expected": odk(op, kind, value, lit),
						}
					)
	return out


def _numeric(text: str) -> bool:
	try:
		float(text)
		return True
	except ValueError:
		return False


if __name__ == "__main__":
	path = os.path.join(os.path.dirname(__file__), "cases", "matrix.json")
	with open(path, "w", encoding="utf-8") as f:
		json.dump(
			{"group": "Comparison matrix (generated)", "cases": cases()}, f, ensure_ascii=False, indent=1
		)
	print(len(cases()), "cases written to", path)
