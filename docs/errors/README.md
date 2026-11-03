# Issue codes

Every problem the validator reports has a stable code. Errors block publishing; warnings need “I understand the warnings”; advice is optional.

| Code | Severity | Stage | Meaning |
| --- | --- | --- | --- |
| [E-FILE-PROTECTED](E-FILE-PROTECTED.md) | error | 1 | The workbook is password-protected, so it can't be read. |
| [E-FILE-SHEET-SIZE](E-FILE-SHEET-SIZE.md) | error | 1 | The "‹sheet_name›" sheet has data outside the first ‹max_rows› rows and ‹max_columns› columns (A to ‹column_name›). |
| [E-FILE-SIZE](E-FILE-SIZE.md) | error | 1 | The file is ‹size_mb› MB; the limit is ‹limit_mb› MB. |
| [E-FILE-TYPE](E-FILE-TYPE.md) | error | 1 | This file is not an Excel workbook (.xlsx). |
| [E-FILE-UNPACKED](E-FILE-UNPACKED.md) | error | 1 | The workbook unpacks to ‹size_mb› MB of data; the limit is ‹limit_mb› MB. |
| [E-FILE-UNREADABLE](E-FILE-UNREADABLE.md) | error | 1 | The workbook can't be opened; it may be damaged. |
| [E-SHEET-MISSING](E-SHEET-MISSING.md) | error | 1 | The workbook has no "‹sheet_name›" sheet. |
| [E-SHEET-UNSUPPORTED](E-SHEET-UNSUPPORTED.md) | error | 1 | The "‹sheet_name›" sheet (entities) isn't supported yet. |
| [W-SHEET-UNKNOWN](W-SHEET-UNKNOWN.md) | warning | 1 | The sheet "‹sheet_name›" isn't used, so anything on it will be ignored. |
| [E-COL-MISSING](E-COL-MISSING.md) | error | 2 | The ‹sheet_name› sheet has no "‹column›" column. |
| [E-COL-UNSUPPORTED](E-COL-UNSUPPORTED.md) | error | 2 | Column "‹column›" isn't supported. |
| [E-FORM-TOO-COMPLEX](E-FORM-TOO-COMPLEX.md) | error | 2 | The form couldn't be checked completely: it is nested too deeply for the ‹stage› checks. |
| [E-GROUP-EXTRA-END](E-GROUP-EXTRA-END.md) | error | 2 | Row ‹row› closes a ‹kind› that was never opened. |
| [E-GROUP-MISMATCH](E-GROUP-MISMATCH.md) | error | 2 | Row ‹row› closes a ‹closing›, but the open block is a ‹open_kind› started in row ‹open_row›. |
| [E-GROUP-TOO-DEEP](E-GROUP-TOO-DEEP.md) | error | 2 | Row ‹row› opens a ‹kind› inside ‹depth› other groups or repeats; the limit is ‹limit›. |
| [E-GROUP-UNCLOSED](E-GROUP-UNCLOSED.md) | error | 2 | The ‹kind› started in row ‹row› (‹name›) is never closed. |
| [E-NAME-DUPLICATE](E-NAME-DUPLICATE.md) | error | 2 | The name ‹name› is used in rows ‹rows›. |
| [E-NAME-INVALID](E-NAME-INVALID.md) | error | 2 | "‹name›" can't be used as a name: ‹reason›. |
| [E-NAME-MISSING](E-NAME-MISSING.md) | error | 2 | Row ‹row› has a question type but no name. |
| [W-COL-IGNORED](W-COL-IGNORED.md) | warning | 2 | Column "‹column›" isn't supported yet and will be ignored. |
| [W-COL-UNKNOWN](W-COL-UNKNOWN.md) | warning | 2 | Column "‹column›" isn't recognised and will be ignored. |
| [E-CALC-CYCLE](E-CALC-CYCLE.md) | error | 3 | These calculations depend on each other in a loop: ‹cycle›. |
| [E-CALC-NOT-LIVE](E-CALC-NOT-LIVE.md) | error | 3 | "‹column›" uses ‹name›, whose calculation can only run when the form is saved. |
| [E-CHOICE-DUPLICATE](E-CHOICE-DUPLICATE.md) | error | 3 | Choice "‹choice›" appears twice in list "‹list›" (choices rows ‹rows›). |
| [E-CHOICE-NAME](E-CHOICE-NAME.md) | error | 3 | Choice name "‹choice›" in list "‹list›" ‹reason›. |
| [E-DEFAULT-DYNAMIC](E-DEFAULT-DYNAMIC.md) | error | 3 | The default "‹value›" can't be used; defaults must be fixed values, today() or now(). |
| [E-EXPR-NOT-LIVE](E-EXPR-NOT-LIVE.md) | error | 3 | ‹what› can't be used in "‹column›": this rule is checked while the form is being filled, offline too. |
| [E-EXPR-QUOTE](E-EXPR-QUOTE.md) | error | 3 | The formula uses curly quotes (‘ ’ or “ ”), which formulas don't accept. |
| [E-EXPR-SYNTAX](E-EXPR-SYNTAX.md) | error | 3 | The formula can't be read: ‹reason›. |
| [E-EXPR-TOO-COMPLEX](E-EXPR-TOO-COMPLEX.md) | error | 3 | The formula in "‹column›" is too complex to check while the form is being filled: written out with the calculations it uses, it is longer than ‹limit› characters or too deeply nested. |
| [E-EXPR-TOO-LONG](E-EXPR-TOO-LONG.md) | error | 3 | The formula is ‹length› characters long; the limit is ‹limit›. |
| [E-FILE-CSV-MISSING](E-FILE-CSV-MISSING.md) | error | 3 | Row ‹row› uses ‹file›, which wasn't uploaded with the form. |
| [E-FILTER-COLUMN](E-FILTER-COLUMN.md) | error | 3 | choice_filter uses column "‹choice_column›", which isn't on the choices sheet for list "‹list›". |
| [E-FILTER-MULTI](E-FILTER-MULTI.md) | error | 3 | choice_filter on select_multiple questions isn't supported yet (row ‹row›). |
| [E-FILTER-UNSUPPORTED](E-FILTER-UNSUPPORTED.md) | error | 3 | This choice_filter can't be applied: ‹reason›. |
| [E-FN-ARGS](E-FN-ARGS.md) | error | 3 | ‹fn›() needs ‹expected› but got ‹got›. |
| [E-FN-UNSUPPORTED](E-FN-UNSUPPORTED.md) | error | 3 | ‹fn›() isn't supported yet. |
| [E-LIST-EMPTY](E-LIST-EMPTY.md) | error | 3 | Choice list "‹list›" has no choices. |
| [E-LIST-MISSING](E-LIST-MISSING.md) | error | 3 | Row ‹row› uses choice list "‹list›", but the choices sheet has no list with that name. |
| [E-LIST-TOO-LARGE](E-LIST-TOO-LARGE.md) | error | 3 | Choice list "‹list›" has ‹count› choices; the limit is ‹limit›. |
| [E-PARAMETER-INVALID](E-PARAMETER-INVALID.md) | error | 3 | Parameter "‹parameter›" (row ‹row›) has the value "‹value›", which isn't a number. |
| [E-REF-REPEAT](E-REF-REPEAT.md) | error | 3 | Row ‹row› (outside repeat ‹repeat›) uses ${‹name›} without count() or sum(). |
| [E-REF-SELF](E-REF-SELF.md) | error | 3 | The ‹column› of ‹name› refers to its own name; use . for "this answer". |
| [E-REF-UNKNOWN](E-REF-UNKNOWN.md) | error | 3 | The formula refers to ${‹name›}, which isn't a question in this form. |
| [E-REPEAT-EMPTY](E-REPEAT-EMPTY.md) | error | 3 | Repeat ‹name› (row ‹row›) has no questions. |
| [E-REPEAT-NESTED](E-REPEAT-NESTED.md) | error | 3 | Repeat ‹inner› (row ‹inner_row›) is inside repeat ‹outer› (row ‹outer_row›); repeats inside repeats aren't supported yet. |
| [E-SETTING-ENCRYPTED](E-SETTING-ENCRYPTED.md) | error | 3 | Encrypted forms (public_key) aren't supported. |
| [E-SETTING-INVALID](E-SETTING-INVALID.md) | error | 3 | The setting ‹setting› = "‹value›" isn't valid: ‹reason›. |
| [E-TYPE-UNKNOWN](E-TYPE-UNKNOWN.md) | error | 3 | "‹type›" isn't a question type. |
| [E-TYPE-UNSUPPORTED](E-TYPE-UNSUPPORTED.md) | error | 3 | "‹type›" questions aren't supported yet (row ‹row›). |
| [E-VERSION-ORDER](E-VERSION-ORDER.md) | error | 3 | Version "‹version›" is not newer than the published version "‹published›". |
| [E-VERSION-PUBLISHED](E-VERSION-PUBLISHED.md) | error | 3 | Version "‹version›" of this form is already published. |
| [I-NO-LABEL](I-NO-LABEL.md) | info | 3 | Row ‹row› (‹name›) has no label, so collectors will see only its name. |
| [W-APPEARANCE](W-APPEARANCE.md) | warning | 3 | Appearance "‹appearance›" (row ‹row›) isn't supported and will be ignored. |
| [W-FORM-ID](W-FORM-ID.md) | warning | 3 | The form ID "‹value›" will be used as ‹fixed›, because form IDs may only use a-z, 0-9 and _. |
| [W-INSTANCE-NAME](W-INSTANCE-NAME.md) | warning | 3 | instance_name can only combine questions and fixed text with concat(); it will be ignored. |
| [W-META-IGNORED](W-META-IGNORED.md) | warning | 3 | "‹type›" (row ‹row›) can't be collected in this app and will be ignored. |
| [W-PARAMETER](W-PARAMETER.md) | warning | 3 | Parameter "‹parameter›" (row ‹row›) isn't supported and will be ignored. |
| [W-SETTING-IGNORED](W-SETTING-IGNORED.md) | warning | 3 | The setting "‹setting›" is ignored by this app. |
| [W-WEB-FIELD](W-WEB-FIELD.md) | warning | 3 | ‹name› (‹type›) can't be shown on the web form; it can be answered on Desk and mForm. |
| [W-WEB-FILTER](W-WEB-FILTER.md) | warning | 3 | On the web form, ‹name› will list all choices of "‹list›"; answers that don't match the filter are rejected when saved. |
| [E-LIMIT-QUESTIONS](E-LIMIT-QUESTIONS.md) | error | 4 | The form has ‹count› questions; the limit is ‹limit›. |
| [E-ROW-BUDGET](E-ROW-BUDGET.md) | error | 4 | The form has too many short-answer questions outside repeats to store in one record (‹bytes› of ‹limit› bytes). |
| [W-MOVE-REPEAT](W-MOVE-REPEAT.md) | warning | 5 | ‹name› moved ‹direction› repeat ‹repeat›; existing answers won't move. |
| [W-REMOVED](W-REMOVED.md) | warning | 5 | ‹name› was removed; its earlier answers are kept but no longer shown on the form. |
| [W-RENAME](W-RENAME.md) | warning | 5 | ‹old› was removed and ‹new› added; existing answers to ‹old› won't move to the new question. |
| [W-TYPE-CHANGE](W-TYPE-CHANGE.md) | warning | 5 | ‹name› changed from ‹old› to ‹new›; earlier answers stay in the old column. |
