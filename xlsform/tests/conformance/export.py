"""Write the Live conformance cases as JSON, for the mForm SDK repository to run in Dart.

Each entry is ``{id, js, doc, parent}``; the expected result is in ``cases/*.json``.

usage: python -m xlsform.tests.conformance.export <out.json>
"""

import sys

from xlsform.tests.conformance import harness

if __name__ == "__main__":
	harness.write_js_cases(harness.build(harness.load_cases()), sys.argv[1])
