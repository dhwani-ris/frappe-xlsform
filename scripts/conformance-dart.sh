#!/usr/bin/env bash
# Run the expression conformance cases through the mForm SDK's own interpreter.
#
#   scripts/conformance-dart.sh [python] [sdk-ref]
#
# 1. exports the Live cases (emitted depends_on strings + documents) to JSON,
# 2. fetches frappe-mobile-sdk at a pinned commit and copies lib/src/utils/js_expression.dart
#    (a pure-Dart file) next to the runner,
# 3. runs them with `dart` (locally, or in the dart:stable container when dart is missing),
# 4. re-runs the conformance test with XLSFORM_SDK_RESULTS so mismatches fail the build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${1:-python}"
SDK_REF="${2:-${XLSFORM_SDK_REF:-1058b155bc9024072fe6352c42f7030f81f20940}}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$ROOT"
"$PYTHON" -m xlsform.tests.conformance.export "$WORK/cases.json"

git init -q "$WORK/sdk"
git -C "$WORK/sdk" fetch -q --depth 1 https://github.com/dhwani-ris/frappe-mobile-sdk.git "$SDK_REF"
git -C "$WORK/sdk" checkout -q FETCH_HEAD
cp -r xlsform/tests/conformance/dart "$WORK/runner"
mkdir -p "$WORK/runner/lib"
cp "$WORK/sdk/lib/src/utils/js_expression.dart" "$WORK/runner/lib/js_expression.dart"

if command -v dart >/dev/null 2>&1; then
	(cd "$WORK/runner" && dart run bin/run.dart "$WORK/cases.json") > "$WORK/results.json"
else
	docker run --rm -v "$WORK:/w" -w /w/runner dart:stable dart run bin/run.dart /w/cases.json > "$WORK/results.json"
fi
cp "$WORK/results.json" "$ROOT/.sdk-conformance-results.json"
echo "SDK results: $(python3 -c "import json;r=json.load(open('$WORK/results.json'));print(len(r),'cases,',sum('error' in x for x in r),'errors')")"
XLSFORM_SDK_RESULTS="$ROOT/.sdk-conformance-results.json" "$PYTHON" -m pytest -q xlsform/tests/conformance -k sdk
