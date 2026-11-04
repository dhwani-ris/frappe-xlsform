# E-LIST-MISSING

**Error: blocks publishing** · stage 3, Meaning

## What it means

Row ‹row› uses choice list "‹list›", but the choices sheet has no list with that name.

## How to fix it

Add it to the choices sheet, or fix the list name after select_one.

## Example

An upload that triggers it reports at `survey!A2`:

> survey!A2: Row 2 uses choice list "district", but the choices sheet has no list with that name.
>
> → Add it to the choices sheet, or fix the list name after select_one.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
