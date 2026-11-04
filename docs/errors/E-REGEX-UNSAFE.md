# E-REGEX-UNSAFE

**Error: blocks publishing** · stage 3, Meaning

## What it means

The pattern in regex() can't be used: ‹reason›.

## How to fix it

Use a simpler pattern, e.g. ^[0-9]{10}$. Answers longer than ‹input_limit› characters never match a regex.

## Example

An upload that triggers it reports at `survey!D2`:

> survey!D2: The pattern in regex() can't be used: a repeated part contains another repeat, as in (a+)*.
>
> → Use a simpler pattern, e.g. ^[0-9]{10}$. Answers longer than 1,000 characters never match a regex.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
