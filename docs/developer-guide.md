# Developer guide

## Code layout

| Path | Contents |
|---|---|
| `xlsform/core/` | Reader, validator, compiler, diff, server engine and the formula parser, evaluator and JavaScript emitter. Never imports frappe. Tested without a site |
| `xlsform/runtime/` | Frappe side: validation storage, publish job, `apply()`, access sync, document hooks |
| `xlsform/api/` | Whitelisted endpoints |
| `xlsform/xlsform/doctype/` | XLSForm, XLSForm Access, XLSForm Version, XLSForm Settings |

`compile_form()` is pure: it has no database access. `runtime/apply.py` is the only code that changes a site's schema. [REQUIREMENTS.md](REQUIREMENTS.md) is the source of truth.

## API

All methods are under `/api/method/`.

| Method | Path | Who | Returns |
|---|---|---|---|
| POST | `xlsform.api.forms.upload` | Designer | `{form, version, state, issues, skipped}`. Send the file as `file`, CSVs as other files |
| GET | `xlsform.api.forms.validation_report` | Designer | Issues as JSON, or `format=xlsx` for the marked workbook |
| GET | `xlsform.api.forms.preview` | Designer | Preview field definitions and test runs |
| POST | `xlsform.api.forms.check_answers` | Designer | `{ok, failures, calculated}` for test answers |
| POST | `xlsform.api.forms.publish` | Designer or System Manager | Job ID and status |
| GET | `xlsform.api.forms.publish_status` | Designer | `queued`, `compiling`, `migrating`, `done` or `failed` |
| POST | `xlsform.api.forms.retire` | Designer | New status |
| GET | `xlsform.api.forms.template` | Any logged-in user | The starter workbook |
| POST | `xlsform.api.data.export` | Users with Export on the form's data | `{file_url}` of a private CSV, ZIP or XLSX with the original column names, or `{queued: true}` above 5,000 records (then the `xlsform_export_ready` realtime event) |

An issue looks like this:

```json
{"code": "E-REF-UNKNOWN", "severity": "error", "sheet": "survey", "row": 25,
 "column": "relevant", "cell": "H25",
 "message": "survey!H25 refers to ${hh_sise}, which isn't a question in this form.",
 "suggestion": "Did you mean ${hh_size}?", "docs_url": "/xlsform-docs/errors#E-REF-UNKNOWN"}
```

Records of generated DocTypes use the standard REST API. The server rules run on every save.

## Development setup

1. Get the app on a Frappe v16 bench and install it on a site:

   ```bash
   bench get-app https://github.com/dhwani-ris/frappe-xlsform --branch develop
   bench --site <site> install-app xlsform
   bench --site <site> set-config allow_tests true
   ```

2. Install the pre-commit hooks. The hooks run ruff, ruff-format, prettier and eslint.

   ```bash
   cd apps/xlsform
   pip install pre-commit
   pre-commit install
   ```

## Tests

Run these from the bench folder:

| What | Command |
|---|---|
| Unit and conformance (no site) | `cd apps/xlsform && FRAPPE_APP_PATH=../frappe ../../env/bin/python -m pytest xlsform/tests/unit xlsform/tests/conformance` |
| Server integration | `bench --site <site> run-tests --app xlsform` |
| pyxform cross-check | `python scripts/pyxform_crosscheck.py <pyxform-venv>/bin/python xlsform/tests/fixtures/corpus` |
| Lint | `pre-commit run --all-files` |

CI also runs the Frappe Semgrep rules.

## Rules for changes

- Write the test first. Every issue code needs a failing and a passing workbook in `xlsform/tests/unit/test_validator.py`. A test enforces this.
- A change to formula behavior needs a case in `xlsform/tests/conformance/cases/`. The case must pass in Python and in Frappe's JavaScript (Node, with `FRAPPE_APP_PATH` set).
- Every emitted rule must stay inside the expression subset the mForm SDK interpreter supports. `core/expr/profile.py` checks this at upload. `xlsform/tests/conformance/export.py` writes the cases for the SDK repository's own test run.
- JavaScript in DocFields comes only from `core/expr/emit_js.py`. User text appears only as an escaped string literal.
- Never drop a column or table. Never convert data in place.
- After you change the issue catalogue, run `python scripts/gen_error_docs.py`.
- Do not add pyxform as a dependency. It pins `xlrd==2.0.1` and Frappe v16 needs `~=2.0.2`. It runs in CI from its own virtualenv.
