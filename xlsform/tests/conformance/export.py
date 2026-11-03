"""Write the Live conformance cases as JSON for the Dart (mForm SDK) runner.

usage: python -m xlsform.tests.conformance.export <out.json>
"""

import sys

from xlsform.tests.conformance import harness

if __name__ == "__main__":
	harness.write_js_cases(harness.build(harness.load_cases()), sys.argv[1])
