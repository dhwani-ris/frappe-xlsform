# CLAUDE.md — xlsform

Spec: docs/REQUIREMENTS.md is the source of truth. If code and spec disagree, stop and ask; when the spec is wrong or silent, update it in the same change.

## Layout
- `xlsform/core/` — framework-free (never imports frappe): reader, structure, meaning, compiler, diff, engine, expr/ (parser, evaluator, JS emitter), annotate, preview, template. Unit-tested without a site.
- `xlsform/runtime/` — Frappe side: validation storage, publish job, apply (the only schema-changing code), access sync, doc hooks.
- `xlsform/api/` — whitelisted endpoints (section 11). `xlsform/xlsform/doctype/` — the four app DocTypes.

## Commands (inside the dev container, see README)
- Unit + conformance: `~/bench/frappe-bench/env/bin/python -m pytest xlsform/tests/unit xlsform/tests/conformance`
- Frappe tests: `bench --site test.localhost run-tests --app xlsform`
- SDK conformance: `scripts/conformance-dart.sh ~/bench/frappe-bench/env/bin/python`
- Corpus cross-check: `python scripts/pyxform_crosscheck.py ~/pyxform-venv/bin/python xlsform/tests/fixtures/corpus`
- Browser: `cd ui-tests && npx playwright test`
- Lint: `pre-commit run --all-files` (+ Frappe semgrep rules in CI)
- After changing the issue catalogue: `python scripts/gen_error_docs.py`

## Rules
- Test first. Every issue code needs a failing and a passing workbook in tests/unit/test_validator.py (a test enforces it).
- core/ never imports frappe. compile_form() stays pure: no frappe.db, no frappe.get_doc. Side effects only in runtime/apply.py.
- The only client runtime is native Frappe meta. JavaScript in DocFields comes only from core/expr/emit_js.py, built from the parsed formula; user text appears only as escaped string literals.
- Emitted JS must run in both Frappe Desk and the mForm SDK interpreter (frappe-mobile-sdk lib/src/utils/js_expression.dart). New emitted syntax = new conformance cases passing in Python, Node (Frappe's real cint/flt/cstr) and Dart.
- What Frappe meta can't express is checked on the server (core/engine.py) or rejected at upload with a named code. Never silently ignore.
- Never drop a column or table. Never cast data in place: a changed question gets a new column.
- Never pass user text to eval, exec, safe_eval or frappe.render_template.
- Every user-facing message: translatable (N_ in core, _() / __() elsewhere), plain language, no stack traces, with sheet/row/column.
- Frappe v16 only.
- Per-form access = role permissions on generated DocTypes from the XLSForm Access table. No has_permission or permission_query_conditions hooks, no User Permission tricks.
- Do not add DocTypes beyond XLSForm, XLSForm Access, XLSForm Version and XLSForm Settings without updating section 4 first.
- Run pre-commit before finishing a task.

## Do not
- Do not add pyxform as a dependency (it pins xlrd==2.0.1; Frappe v16 needs ~=2.0.2). It runs in CI from its own venv only.
- Do not add Java, Node at runtime, or system packages (Frappe Cloud must install it).
- Do not touch DocTypes outside modules "XLSForm Data" / "XLSForm Choices", or another form's DocTypes, from apply().
- Do not grant designers DocType, Customize Form or script permissions.
