# Marketplace listing copy

## Short description (62 characters)

Build data-collection forms in Excel and collect into DocTypes

## Long description

**XLSForm for Frappe** lets your M&E and programme teams build data-collection forms in Excel — using XLSForm, the standard behind ODK, KoboToolbox and SurveyCTO — and collect straight into Frappe DocTypes, on Desk, on the web and offline on mobile.

- **No developer needed.** Upload an `.xlsx`; publishing creates the DocTypes.
- **Every problem at once, at its cell.** Plain-language messages with a suggested fix, and a downloadable copy of your workbook with each problem highlighted and explained.
- **Skip logic that works everywhere.** Relevance, required and read-only rules become standard Frappe rules, so they work the same on Desk, Web Forms and offline in mForm. Constraints and calculations are checked on every save.
- **Cascading choices, repeats, many languages.** District → village filters, repeat groups as child tables, `label::Hindi` translations.
- **Safe versioning.** Republish any time; earlier records stay valid and no column is ever dropped.
- **Your data, your tools.** Records are ordinary DocTypes: reports, permissions, workflows, REST API and Insights just work. Export with your original XLSForm column names.
- **Per-form access.** Choose which roles may create, read, edit or export each form's data.

Compatibility: a documented subset of XLSForm (see the compatibility page); anything outside it is reported at upload by name, never silently ignored.

## Screenshots to take

1. Version page with the issue table (a workbook with one error and one warning)
2. The highlighted workbook open in Excel, showing a red cell with its comment
3. Preview dialog with the household section appearing after "Yes"
4. A published form being filled on Desk (cascading district → village)
5. The same form in mForm

## Demo video script (3–4 minutes)

1. Download the starter workbook from the Excel Forms workspace; open it in Excel.
2. Break one formula (`${hh_sise}`); upload; show the message and the highlighted workbook.
3. Fix it in Excel; upload again; read the warning; preview — answer "Yes" and watch the section appear; "Check answers" with an age of 200.
4. Publish; grant the "Field Officer" role create access on the form.
5. Fill the form on Desk; then on mForm offline; sync; show the record and a report.
6. Change a question type in Excel; upload v2; show the change summary; publish; show old records still open.
