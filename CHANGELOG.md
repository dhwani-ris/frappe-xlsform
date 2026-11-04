# Changelog

## v1.0.0 — 2026-11-04

First release. See docs/REQUIREMENTS.md (revision 3) for the full specification.

- Upload XLSForm workbooks; five-stage validation with 68 coded, located, translatable issues and a highlighted copy of the workbook
- Formula engine: one parser; an ODK-faithful server evaluator; a JavaScript emitter whose rules run identically in Frappe Desk, Web Forms and the mForm SDK (1,187 conformance cases), each checked against the SDK expression subset
- Publishing compiles forms into DocTypes (choice lists as linked DocTypes, repeats as child tables), Web Forms and mForm registration; schema changes never drop or cast data; Frappe's DocType checks run before any schema change
- Server rules on every channel: calculations, relevance clearing, required, constraints, ranges, repeat counts, choice filters; a record's form and version come from the server
- Preview with live skip logic and server-checked test answers; retire and re-open forms; per-form role access, with no data access for designers unless granted
- Three-column form layout by default (XLSForm Settings › Columns per section)
- Private, audited exports with the original column names; large exports run in the background
- Limits against hostile workbooks: unpacked size, rows and columns, formula depth and size, safe regular expressions
- Hindi translation (386 strings); pyxform-compatible spellings; Frappe v16, MariaDB
