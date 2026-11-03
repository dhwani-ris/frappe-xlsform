# E-FILTER-UNSUPPORTED

**Error: blocks publishing** · stage 3, Meaning

## What it means

This choice_filter can't be applied: ‹reason›.

## How to fix it

Use conditions like district = ${district}, joined by and.

## Example

An upload that triggers it reports at `survey!D3`:

> survey!D3: This choice_filter can't be applied: only conditions of the form column = ${question} joined by and can be used.
>
> → Use conditions like district = ${district}, joined by and.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
