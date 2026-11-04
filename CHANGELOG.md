# Changelog

## Unreleased — v1.0.0 candidate

First release. See docs/REQUIREMENTS.md (revision 3) for the full specification.

- Upload XLSForm workbooks; five-stage validation with 62 coded, located, translatable issues and a highlighted copy of the workbook
- Formula engine: one parser; an ODK-faithful server evaluator; a JavaScript emitter whose rules run identically in Frappe Desk, Web Forms and the mForm SDK (1,187 conformance cases)
- Publishing compiles forms into DocTypes (choice lists as linked DocTypes, repeats as child tables), Web Forms and mForm registration; schema changes never drop or cast data
- Server rules on every channel: calculations, relevance clearing, required, constraints, ranges, repeat counts, choice filters
- Preview with live skip logic and server-checked test answers; retire and re-open forms; per-form role access; export with original names
- Hindi translation; pyxform-compatible spellings; Frappe v16
