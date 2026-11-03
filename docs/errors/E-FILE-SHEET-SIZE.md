# E-FILE-SHEET-SIZE

**Error: blocks publishing** · stage 1, File

## What it means

The "‹sheet_name›" sheet has data outside the first ‹max_rows› rows and ‹max_columns› columns (A to ‹column_name›).

## How to fix it

Delete everything after the form's last row and column, or split the form.

## Example

An upload that triggers it reports at `survey!GS1`:

> survey!GS1: The "survey" sheet has data outside the first 30,000 rows and 200 columns (A to GR).
>
> → Delete everything after the form's last row and column, or split the form.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
