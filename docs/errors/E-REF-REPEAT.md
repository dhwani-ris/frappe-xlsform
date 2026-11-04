# E-REF-REPEAT

**Error: blocks publishing** · stage 3, Meaning

## What it means

Row ‹row› (outside repeat ‹repeat›) uses ${‹name›} without count() or sum().

## How to fix it

Wrap it, e.g. sum(${‹name›}).

## Example

An upload that triggers it reports at `survey!D5`:

> survey!D5: Row 5 (outside repeat member) uses ${age} without count() or sum().
>
> → Wrap it, e.g. sum(${age}).

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
