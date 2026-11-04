# E-GROUP-MISMATCH

**Error: blocks publishing** · stage 2, Structure

## What it means

Row ‹row› closes a ‹closing›, but the open block is a ‹open_kind› started in row ‹open_row›.

## How to fix it

Change row ‹row› to ‹expected›, or add the missing ‹closing_end›.

## Example

An upload that triggers it reports at `survey!A4`:

> survey!A4: Row 4 closes a repeat, but the open block is a group started in row 2.
>
> → Change row 4 to end_group, or add the missing begin_repeat.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
