# pyxform example workbooks

Copied unchanged from [XLSForm/pyxform](https://github.com/XLSForm/pyxform) `tests/fixtures`
(BSD 2-Clause, see `LICENSE.pyxform`). They are the first part of the real-world corpus that
`scripts/pyxform_crosscheck.py` runs on pull requests that change the validator: every workbook is checked by xlsform and by pyxform,
and any disagreement that isn't a documented v1 limitation fails the build.

Anonymised client forms go in `../clients/` (REQUIREMENTS.md section 13).
