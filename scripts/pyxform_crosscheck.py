"""Cross-check the xlsform validator against pyxform on a corpus of real workbooks.

pyxform can't be an app dependency (it pins xlrd==2.0.1; Frappe v16 needs xlrd~=2.0.2), so it
runs from its own virtualenv as a second opinion:

    python scripts/pyxform_crosscheck.py <pyxform-python> <corpus dir> [--json out.json]

For each workbook:

- both accept                    -> ok
- we reject, pyxform accepts     -> ok only if every error is a documented v1 limitation
                                    (LIMITATION_CODES); otherwise a possible false rejection
- we accept, pyxform rejects     -> a missed error
- both reject                    -> ok

Disagreements reviewed by a person are recorded, with the reason, in ``<corpus>/expected.json``.
Exit status 1 when any other workbook needs attention, so CI fails on a regression.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xlsform.core.validate import ValidateOptions, validate  # noqa: E402

# Errors that mean "valid XLSForm, but outside the v1 subset" (REQUIREMENTS.md section 2).
LIMITATION_CODES = {
	"E-TYPE-UNSUPPORTED",
	"E-FN-UNSUPPORTED",
	"E-EXPR-NOT-LIVE",
	"E-CALC-NOT-LIVE",
	"E-REPEAT-NESTED",
	"E-FILTER-UNSUPPORTED",
	"E-FILTER-MULTI",
	"E-COL-UNSUPPORTED",
	"E-SETTING-ENCRYPTED",
	"E-DEFAULT-DYNAMIC",
	"E-FILE-CSV-MISSING",
	"E-CHOICE-NAME",  # choice names become document names: no spaces or < > % " # * ? \ /
	"E-SETTING-INVALID",  # form_id must be a valid Frappe name; pyxform accepts any
	"E-REF-SELF",  # ${own_name} inside its own constraint: we ask for "." instead
	"E-LIMIT-QUESTIONS",
	"E-ROW-BUDGET",
	"E-SHEET-UNSUPPORTED",  # entities
	"E-CHOICE-DUPLICATE",  # choice names are document names, so unique within a list
	"E-REF-REPEAT",  # ${repeat_question} outside its repeat needs count()/sum(); indexed-repeat is v2
}

PYXFORM_SNIPPET = r"""
import json, sys
from pyxform.xls2xform import convert
out = {}
for path in sys.argv[1:]:
    try:
        convert(xlsform=path, validate=False, pretty_print=False)
        out[path] = {"ok": True}
    except Exception as exc:
        out[path] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
print(json.dumps(out))
"""


def run_pyxform(python: str, paths: list[str]) -> dict:
	result = subprocess.run([python, "-c", PYXFORM_SNIPPET, *paths], capture_output=True, text=True, check=True)
	return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> int:
	python, corpus = sys.argv[1], sys.argv[2]
	json_out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
	paths = sorted(
		os.path.join(root, f)
		for root, _dirs, files in os.walk(corpus)
		for f in files
		if f.lower().endswith(".xlsx")
	)
	theirs = run_pyxform(python, paths)
	expected_path = os.path.join(corpus, "expected.json")
	expected = json.load(open(expected_path)) if os.path.exists(expected_path) else {}
	rows = []
	attention = 0
	for path in paths:
		with open(path, "rb") as f:
			result = validate(f.read(), os.path.basename(path), ValidateOptions(max_questions=10_000))
		errors = sorted({i.code for i in result.issues if i.severity == "error"})
		ours_ok = not errors
		pyx = theirs[path]
		if ours_ok and pyx["ok"]:
			verdict = "ok"
		elif not ours_ok and pyx["ok"]:
			verdict = "limitation" if set(errors) <= LIMITATION_CODES else "possible false rejection"
		elif ours_ok and not pyx["ok"]:
			verdict = "missed error"
		else:
			verdict = "both reject"
		override = expected.get(os.path.relpath(path, corpus))
		if override and verdict in ("possible false rejection", "missed error") and not ours_ok:
			verdict = f"{override['verdict']} (reviewed)"
		if verdict in ("possible false rejection", "missed error"):
			attention += 1
		rows.append(
			{
				"workbook": os.path.relpath(path, corpus),
				"verdict": verdict,
				"xlsform_errors": errors,
				"xlsform_first": next((i.message for i in result.issues if i.severity == "error"), ""),
				"pyxform": pyx.get("error", "ok"),
			}
		)
	width = max(len(r["workbook"]) for r in rows)
	for r in rows:
		print(f"{r['workbook']:<{width}}  {r['verdict']:<26} {', '.join(r['xlsform_errors']) or '-'}")
		if r["verdict"] in ("possible false rejection", "missed error"):
			print(f"{'':<{width}}    ours:    {r['xlsform_first']}")
			print(f"{'':<{width}}    pyxform: {r['pyxform']}")
	summary = {v: sum(1 for r in rows if r["verdict"] == v) for v in sorted({r["verdict"] for r in rows})}
	print("\n" + ", ".join(f"{k}: {v}" for k, v in summary.items()))
	if json_out:
		with open(json_out, "w") as f:
			json.dump({"summary": summary, "rows": rows}, f, indent=1)
	return 1 if attention else 0


if __name__ == "__main__":
	sys.exit(main())
