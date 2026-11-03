# E-EXPR-NOT-LIVE

**Error: blocks publishing** · stage 3, Meaning

## What it means

‹what› can't be used in "‹column›": this rule is checked while the form is being filled, offline too.

## How to fix it

Use a simpler condition here, or move the check into a constraint, which is checked on save.

## Example

An upload that triggers it reports at `survey!D3`:

> survey!D3: today() can't be used in "relevant": this rule is checked while the form is being filled, offline too.
>
> → Use a simpler condition here, or move the check into a constraint, which is checked on save.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
