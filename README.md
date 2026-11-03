# XLSForm for Frappe

Build data-collection forms in Excel and collect straight into Frappe DocTypes — on Desk, on the web, and offline on mobile.

XLSForm is the spreadsheet standard used by ODK, KoboToolbox, SurveyCTO and Ona. If your team already writes XLSForms, upload them here and get a working form in minutes, with every answer stored as a normal Frappe document you can report on, link and automate.

## Features

- Upload an `.xlsx` XLSForm; no developer needed to create or change forms
- Clear, cell-level messages for every problem at once, plus a downloadable copy of your workbook with the problems highlighted and explained in cell comments
- Skip logic, required and read-only rules that work live on Desk, the web and offline in mForm — compiled into standard Frappe `depends_on` rules, so nothing extra runs on the client
- Constraints, calculations, ranges and repeat counts checked on save, from every channel
- Cascading choice lists (`choice_filter`), repeats, multilingual labels (`label::Hindi (hi)`)
- Versioned forms: republish safely; earlier records stay valid and columns are never dropped
- Preview with live skip logic and "Check answers" before publishing
- Per-form access: pick which roles may create, read, edit or export each form's data
- Data lives in real DocTypes: reports, permissions, workflows, REST API and Insights all work
- Export with your original XLSForm column names, one sheet per repeat

## Compatibility

Supports a documented subset of XLSForm — see [docs/compatibility.md](docs/compatibility.md). Anything unsupported is rejected at upload with a clear, named message, never silently ignored. Frappe v16.

## How it works

1. A Form Designer uploads an XLSForm.
2. The app checks it and lists any problems by sheet, row and cell.
3. The designer previews it, then publishes: the form becomes a DocType (repeats become child tables, choice lists become linked DocTypes).
4. Collectors fill it on Desk, the web form at `/xf/<form-id>`, or mForm, online or offline.

## Installation (self-hosted)

```bash
bench get-app https://github.com/dhwani-ris/frappe-xlsform --branch version-16
bench --site your.site install-app xlsform
```

Then give your form designers the **XLSForm Designer** role and open **Excel Forms** in the desk.

## Roles

- **XLSForm Designer** — uploads, previews, publishes and retires forms, and chooses which roles may use each form's data. Never gets DocType, Customize Form or script rights.
- **Collectors and reviewers** — any role you already use (for example "Field Officer"), granted per form in the form's *Who can use the data* table.

## Development

```bash
docker compose -f .devcontainer/docker-compose.yml -p xlsform-dev up -d
docker compose -f .devcontainer/docker-compose.yml -p xlsform-dev exec frappe /workspace/xlsform/.devcontainer/setup-bench.sh
```

| What | Command (inside the container) |
| --- | --- |
| Unit + conformance tests (no site) | `~/bench/frappe-bench/env/bin/python -m pytest xlsform/tests/unit xlsform/tests/conformance` |
| Server integration tests | `bench --site test.localhost run-tests --app xlsform` |
| mForm SDK conformance | `scripts/conformance-dart.sh ~/bench/frappe-bench/env/bin/python` |
| pyxform cross-check on the corpus | `python scripts/pyxform_crosscheck.py ~/pyxform-venv/bin/python xlsform/tests/fixtures/corpus` |
| Browser smoke tests | `cd ui-tests && npx playwright test` |
| Lint | `pre-commit run --all-files` |

## Contributing

Read [CLAUDE.md](CLAUDE.md) and [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md). Every change needs tests; every issue code has a failing and a passing workbook in `xlsform/tests/unit/test_validator.py`; formula semantics changes need a case in `xlsform/tests/conformance/cases/` that passes in Python, Frappe's JavaScript and the mForm SDK. Run `pre-commit run --all-files` before opening a pull request.

## Related

- [mForm](https://github.com/dhwani-ris/frappe-mobile-sdk): offline mobile client for Frappe
- [mobile_control](https://github.com/dhwani-ris/frappe-mobile-control): the Frappe side of mForm

## License

AGPL-3.0. The pyxform example workbooks under `xlsform/tests/fixtures/corpus/pyxform` are BSD 2-Clause (see the licence file there).
