# E-REPEAT-NESTED

**Error: blocks publishing** · stage 3, Meaning

## What it means

Repeat ‹inner› (row ‹inner_row›) is inside repeat ‹outer› (row ‹outer_row›); repeats inside repeats aren't supported yet.

## How to fix it

Move ‹inner› out, or flatten it into the outer repeat.

## Example

An upload that triggers it reports at `survey!A3`:

> survey!A3: Repeat m (row 3) is inside repeat hh (row 2); repeats inside repeats aren't supported yet.
>
> → Move m out, or flatten it into the outer repeat.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
