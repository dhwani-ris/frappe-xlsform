# Developer guide

## Code layout

| Path | Contents |
|---|---|
| `xlsform/core/` | Reader, validator, compiler, diff, server engine and the formula parser, evaluator and JavaScript emitter. Never imports frappe. Tested without a site |
| `xlsform/runtime/` | Frappe side: validation storage, publish job, `apply()`, access sync, document hooks |
| `xlsform/api/` | Whitelisted endpoints |
| `xlsform/xlsform/doctype/` | XLSForm, XLSForm Access, XLSForm Version, XLSForm Settings |

`compile_form()` is pure: it has no database access. `runtime/apply.py` is the only code that changes a site's schema. [REQUIREMENTS.md](REQUIREMENTS.md) is the source of truth. [CLAUDE.md](../CLAUDE.md) lists the rules for changes.

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
| GET | `xlsform.api.data.export` | Users with Export on the form's data | CSV, ZIP or XLSX with the original column names |

An issue looks like this:

```json
{"code": "E-REF-UNKNOWN", "severity": "error", "sheet": "survey", "row": 25,
 "column": "relevant", "cell": "H25",
 "message": "survey!H25 refers to ${hh_sise}, which isn't a question in this form.",
 "suggestion": "Did you mean ${hh_size}?", "docs_url": "/xlsform-docs/errors#E-REF-UNKNOWN"}
```

Records of generated DocTypes use the standard REST API. The server rules run on every save.

## Development setup

1. Start the dev container:

   ```bash
   docker compose -f .devcontainer/docker-compose.yml -p xlsform-dev up -d
   docker compose -f .devcontainer/docker-compose.yml -p xlsform-dev exec frappe /workspace/xlsform/.devcontainer/setup-bench.sh
   ```

2. Install the pre-commit hooks. The hooks run ruff, ruff-format, prettier and eslint.

   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Tests

Run these inside the container:

| What | Command |
|---|---|
| Unit and conformance (no site) | `~/bench/frappe-bench/env/bin/python -m pytest xlsform/tests/unit xlsform/tests/conformance` |
| Server integration | `bench --site test.localhost run-tests --app xlsform` |
| mForm SDK conformance | `scripts/conformance-dart.sh ~/bench/frappe-bench/env/bin/python` |
| pyxform cross-check | `python scripts/pyxform_crosscheck.py ~/pyxform-venv/bin/python xlsform/tests/fixtures/corpus` |
| Browser | `cd ui-tests && npx playwright test` |
| Lint | `pre-commit run --all-files` |

CI also runs the Frappe Semgrep rules.

## Rules for changes

- Write the test first. Every issue code needs a failing and a passing workbook in `xlsform/tests/unit/test_validator.py`. A test enforces this.
- A change to formula behavior needs a case in `xlsform/tests/conformance/cases/`. The case must pass in Python, Frappe's JavaScript and the mForm SDK.
- JavaScript in DocFields comes only from `core/expr/emit_js.py`. User text appears only as an escaped string literal.
- Never drop a column or table. Never convert data in place.
- After you change the issue catalogue, run `python scripts/gen_error_docs.py`.
- Do not add pyxform as a dependency. It pins `xlrd==2.0.1` and Frappe v16 needs `~=2.0.2`. It runs in CI from its own virtualenv.
