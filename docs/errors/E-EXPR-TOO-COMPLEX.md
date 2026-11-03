# E-EXPR-TOO-COMPLEX

**Error: blocks publishing** · stage 3, Meaning

## What it means

The formula in "‹column›" is too complex to check while the form is being filled: written out with the calculations it uses, it is longer than ‹limit› characters or too deeply nested.

## How to fix it

Simplify it, or use fewer calculations that build on each other. A constraint has no such limit, because it is checked when the form is saved.

## Example

An upload that triggers it reports at `survey!E21`:

> survey!E21: The formula in "relevant" is too complex to check while the form is being filled: written out with the calculations it uses, it is longer than 4,000 characters or too deeply nested.
>
> → Simplify it, or use fewer calculations that build on each other. A constraint has no such limit, because it is checked when the form is saved.

Words in ‹angle quotes› above are filled in with your form's own names, rows and values.
