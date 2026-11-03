# Security

## Permission model

- **Per-form access is role permissions.** The Access table on each XLSForm writes permission rows on the generated DocType. Frappe denies a role without a row, designers included. Role Permission Manager rows on a generated DocType are removed when the Access table syncs. The app has no `has_permission` or `permission_query_conditions` hooks and does not use User Permissions.
- **System fields are protected.** Form status, versions, reports and compiled rules are at permlevel 1. Designers can read them. Only the app writes them.
- **Records keep their form and version.** The server sets the form of a record from its DocType. A record can name an older published version of the same form, which mForm needs offline, and cannot change it later.
- **Schema changes stay inside the form.** `apply()` runs with `ignore_permissions` only after the caller is checked as a Designer or System Manager. It changes only the DocTypes recorded on that form, in the XLSForm Data and XLSForm Choices modules, with the configured prefix.
- **Designers are not developers.** The XLSForm Designer role has no DocType, Customize Form or script permission. Rules come from parsed formulas, not from code the designer writes.
- **Publishing can be limited.** Turn off **Designers can publish** to let only System Managers publish. `bench migrate` keeps this setting.
- **Files.** The upload API reads a file URL only when the caller can download that file.

## Untrusted workbooks

A workbook is untrusted input:

- openpyxl reads formulas as their cached values. Macros and external links are ignored.
- Labels, hints, notes and choice labels are HTML-escaped.
- Formulas are parsed into a tree. The app never uses `eval`, `exec`, `safe_eval` or `render_template` on user text.
- User text enters emitted JavaScript only as an escaped string literal.
- Limits in XLSForm Settings bound the upload size, question count, choices per list and formula length.

## Server rules on every channel

Desk, Web Form, mForm sync and REST all save through the same `validate` hook. A client that skips a check cannot store a record that breaks a constraint, a required rule or a calculation.

## Exports

The export reads records with `frappe.get_list`, so role permissions and "Only their own records" apply. Text that starts with `=`, `+`, `-`, `@`, tab or carriage return gets a leading `'`, so a spreadsheet does not run it as a formula.

Every export is saved as a private File on the XLSForm and recorded in the Access Log (who, which form, when, which format). Export files are deleted after one day.

## Limits

- **`xf_channel` is best-effort.** It comes from the request path and the record. Do not use it as an audit record.
- **Failed publishes leave DDL behind.** MariaDB cannot roll back DDL. The next publish of the same form uses those DocTypes again. Nothing else uses them.
- **MariaDB only.** The row size budget and table options are MariaDB features. PostgreSQL is not supported.
