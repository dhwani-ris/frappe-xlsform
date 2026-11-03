"""Write broken.xlsx and fixed.xlsx for the UI tests: usage make_fixtures.py <dir> <form_id>."""

import os
import sys

sys.path.insert(0, os.getcwd())

from xlsform.tests.workbooks import HOUSEHOLD, make_xlsx

out, form_id = sys.argv[1], sys.argv[2]
settings = [
	["form_title", "form_id", "version", "default_language"],
	[f"UI Survey {form_id}", form_id, "1", "English (en)"],
]
broken = [list(r) for r in HOUSEHOLD["survey"]]
broken[4][6] = "${hh_sise} > 1"  # survey!G5 refers to an unknown question
with open(os.path.join(out, "broken.xlsx"), "wb") as f:
	f.write(make_xlsx(survey=broken, choices=HOUSEHOLD["choices"], settings=settings))
with open(os.path.join(out, "fixed.xlsx"), "wb") as f:
	f.write(make_xlsx(survey=HOUSEHOLD["survey"], choices=HOUSEHOLD["choices"], settings=settings))
