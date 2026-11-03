# Frappe XLSForm — Requirements & README

Nov 3, 2026 · @can you create a scraper and store data in db and show it into a

## 1. Overview

**XLSForm for Frappe** (app name `xlsform`, working title) lets non-technical client users design data-collection forms in Excel using the XLSForm standard, upload them, and collect data into native Frappe DocTypes — on Desk, on the web, and offline on mobile through mForm. It is built as a standard Frappe app, AGPL-3.0, publishable on the Frappe Cloud Marketplace, and developed with Claude Code against this document.

**Problem.** NGO, CSR, government and cooperative clients need forms they can build and change themselves, the way they do in ODK or KoboToolbox. Today every new form on Frappe needs a developer to create a DocType. Their M&E teams already write XLSForms, but nothing in the Frappe ecosystem can read one.

**Goals (v1)**

1. A client user uploads an `.xlsx` XLSForm and gets a working form, without developer help, in under 5 minutes.
2. Every authoring mistake is reported with the sheet, row, column, a plain-language reason and a suggested fix — never a Python traceback.
3. Submissions land in real Frappe DocTypes, so reports, permissions, workflows, the REST API and Insights work unchanged.
4. Skip logic, constraints, calculations and cascading choices behave identically on Desk, web and mForm offline.
5. Published form versions are immutable; every submission records the version it was collected on.

**Non-goals (v1)**

- Full ODK parity. v1 supports a documented subset (section 2); anything else is rejected at upload with a clear message, never silently ignored.
- A drag-and-drop visual builder. The internal JSON schema is designed so one can be added in v2 without changing storage.
- XForm XML export or ODK Collect/Enketo compatibility.
- Analytics dashboards. Frappe reports and Insights cover this.

**Users**

| Role | What they do |
| --- | --- |
| Form Designer | Client M&E or programme staff. Uploads XLSForms, previews, publishes, retires versions. Never gets DocType or System Manager rights. |
| Form Data Collector | Field staff. Fills forms on web or mForm, offline included. |
| Form Data Reviewer | Views, edits and exports submissions for forms they are permitted on. |
| System Manager | Installs the app, sets limits and defaults in XLSForm Settings. |

## 2. v1 scope and compatibility matrix

v1 supports the XLSForm features that cover most real NGO surveys; every unsupported feature is **rejected at upload with a named error** (section 7), never silently dropped. This matrix is published in the README as the public compatibility promise and is the source of truth for the validator's allow-list.

**Question types**

| XLSForm type | v1 | Frappe fieldtype | Notes |
| --- | --- | --- | --- |
| text | Yes | Small Text | Never `Data`: ODK text has no 140-char limit and TEXT columns don't count against the row budget |
| integer | Yes | Int |  |
| decimal | Yes | Float | precision from `parameters` if given, else 9 |
| range | Yes | Int or Float | `start`, `end`, `step` parameters enforced as constraints |
| select\_one | Yes | Select, or Autocomplete | Autocomplete when the list has a `choice_filter` or more than 50 choices (configurable) |
| select\_multiple | Yes | Small Text | Space-separated choice names, exactly as ODK stores them; rendered as checkboxes |
| select\_one\_from\_file / select\_multiple\_from\_file | Yes | Autocomplete | CSV attached to the version; loaded into `compiled_meta.choices` (up to 5,000 rows in v1) |
| rank | v2 |  | Rejected: "rank is not supported yet" |
| note | Yes | HTML | Display only, no column |
| acknowledge | Yes | Check |  |
| date / time / dateTime | Yes | Date / Time / Datetime |  |
| geopoint | Yes | Geolocation | Stored as GeoJSON; evaluator exposes ODK `lat lon alt acc` string |
| geotrace / geoshape | Yes | Geolocation |  |
| image | Yes | Attach Image | `max-pixels` parameter honoured on mForm |
| audio / video / file | Yes | Attach |  |
| barcode | Yes | Data | Scanned on mForm; typed on web |
| calculate | Yes | Small Text, read-only, hidden | Value recomputed server-side on save |
| hidden | Yes | Small Text, hidden |  |
| start / end / today / deviceid / username / phonenumber / email / audit | start, end, today, deviceid, username: Yes. Others: v2 | Datetime / Date / Data, read-only | Filled by the runtime, not the user |
| begin\_group / end\_group | Yes | Section Break | `field-list` appearance = one page on mForm |
| begin\_repeat / end\_repeat | Yes, one level | Table → child DocType | Nested repeats rejected in v1; `repeat_count` supported |
| trigger, background-audio, xml-external, csv-external | v2 |  | Rejected with a named error |

**Survey sheet columns**

| Column | v1 | Notes |
| --- | --- | --- |
| type, name, label, hint | Yes | `label::<lang>` and `hint::<lang>` for any language |
| required, required\_message | Yes | `required` may be `yes` or an expression |
| relevant | Yes | Non-relevant values are cleared on save, as in ODK |
| constraint, constraint\_message | Yes | Checked on client and re-checked on server |
| calculation, default, read\_only | Yes | `default` accepts a literal; dynamic defaults are v2 |
| choice\_filter | Yes | Expressions over the choices sheet's extra columns |
| appearance | Partial | `multiline`, `minimal`, `horizontal`, `field-list`, `numbers`, `likert`, `signature`. Others are accepted with a warning and ignored |
| repeat\_count, parameters | Yes |  |
| media::image, media::audio | v2 | Warning, ignored |
| guidance\_hint, trigger, bind::\* , body::*, instance::* | v2 | Rejected or warned per section 7 |

**Choices sheet**: `list_name`, `name`, `label`, `label::<lang>` and any extra columns used by `choice_filter`.

**Settings sheet**: `form_title`, `form_id`, `version`, `default_language`, `instance_name` (maps to the DocType's autoname/title). `public_key`, `submission_url`, `style` are ignored with a warning.

**Expression functions (v1)**

Logic and comparison: `if`, `and`, `or`, `not`, `true`, `false`, `coalesce`. Choices: `selected`, `count-selected`, `selected-at`, `jr:choice-name`. Text: `concat`, `substr`, `string-length`, `contains`, `starts-with`, `ends-with`, `normalize-space`, `regex`, `string`. Numbers: `int`, `number`, `round`, `abs`, `pow`, `floor`, `ceiling`, `min`, `max`. Dates: `today`, `now`, `date`, `decimal-date-time`, `format-date`, `format-date-time`. Repeats: `count`, `sum`, `position(..)`. Other: `once`, `uuid`, `boolean`.

**Out of scope for v1, rejected with a named error**: `pulldata`, `indexed-repeat`, `instance()` beyond choice filters, `search()`, entities, `last-saved`, `area`, `distance`, `digest`, `randomize`, `jr:itext`, nested repeats, encrypted forms.

## 3. Architecture and data flow

The app has four stages: authoring in Excel, validation, compilation into DocTypes, and collection through three channels. All of them share one parsed form and one expression engine, so behaviour can't drift between Desk, web and mobile.

&#91;embedded content: architecture · author, validate, compile, collect\]

The designer loops between Excel and the validator until the form is clean. Publishing compiles it into ordinary DocTypes. Every channel then saves through the same server hook, so a client that skips a check still can't store invalid data.

## 4. DocType specifications

The app ships **three DocTypes** — XLSForm, XLSForm Version and XLSForm Settings — in one module, **XLSForm**. The converter turns each published version straight into generated data DocTypes (4.4). Everything else uses standard Frappe features or JSON on the version, following the rule "standard features before custom DocTypes". Items marked \[ASSUMPTION — confirm\] are v1 defaults.

**What is deliberately not a DocType**

| Need | Handled by | Why |
| --- | --- | --- |
| Per-form access for collectors and reviewers | Standard **User Permissions** on XLSForm | Generated DocTypes link to XLSForm through `xf_form`, so Frappe applies the restriction automatically. No custom permission hooks |
| Original-name ↔ fieldname map | `compiled_meta.fields` (JSON) | Read whole by the compiler and exports; never edited or queried row by row |
| Choice lists, including `*_from_file` CSVs | `compiled_meta.choices` (JSON), up to 5,000 per list | A real `XLSForm Choice` DocType is deferred to v1.1, for clients who need larger lists |
| Media and CSV files for a version | Standard File attachments on the XLSForm Version | Frappe already stores, permissions and serves them |
| Audit of publishes and access changes | `track_changes` and the standard Version log | Built in |

**4.1 XLSForm** — Regular (master), one per form. It is the stable identity across versions and the permission anchor. Naming: `field:form_id`.

| # | Label | Fieldname | Fieldtype | Options | Reqd | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Form ID | form\_id | Data |  | Yes | From settings `form_id`; unique; `^[a-z][a-z0-9_]{2,40}$` |
| 2 | Title | title | Data |  | Yes | From `form_title`; editable |
| 3 | Status | status | Select | Draft, Published, Retired | Yes | Read-only; set by the version lifecycle and the Retire action |
| 4 | Current Version | current\_version | Link | XLSForm Version |  | Read-only |
| 5 | Data DocType | data\_doctype | Link | DocType |  | Read-only; the generated parent DocType |
| 6 | Default Language | default\_language | Data |  |  | From settings |
| 7 | Allow Web | allow\_web | Check |  |  | Default 1 |
| 8 | Allow mForm | allow\_mobile | Check |  |  | Default 1 |

List view: title, status, current\_version, modified. Filter: status. Sort: modified desc. `track_changes = 1`.

**4.2 XLSForm Version** — Submittable, one per upload. Submit = publish; Frappe's docstatus makes a published version immutable. Naming: `format:{form}-v{version}`.

| # | Label | Fieldname | Fieldtype | Options | Reqd | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Form | form | Link | XLSForm | Yes | Created automatically on the first upload of a new `form_id` |
| 2 | Version | version | Data |  | Yes | From settings `version`; must sort above the last published one |
| 3 | Source File | source\_file | Attach |  | Yes | `.xlsx` only; size limit from settings. CSVs for `*_from_file` are attached to this record by name |
| 4 | State | state | Select | Uploaded, Invalid, Valid, Published, Superseded | Yes | Read-only |
| 5 | Errors | error\_count | Int |  |  | Read-only |
| 6 | Warnings | warning\_count | Int |  |  | Read-only |
| 7 | Warnings Accepted | warnings\_accepted | Check |  |  | Must be ticked to publish when warnings exist |
| 8 | Validation Report | validation\_report | JSON |  |  | Hidden; issue objects (section 11) |
| 9 | Report | report\_html | HTML |  |  | Rendered issue table grouped by sheet |
| 10 | Change Summary | change\_summary | JSON |  |  | Added, retired and changed fields vs the published version |
| 11 | Parsed Form | parsed\_json | JSON |  |  | Hidden; normalised pyxform output |
| 12 | Compiled Meta | compiled\_meta | JSON |  |  | Hidden; see shape below |
| 13 | Source Hash | source\_hash | Data |  |  | SHA-256 of the xlsx; a duplicate upload is rejected |

Controller: `validate` runs the pipeline in section 7 (in a background job for large files) and `before_submit` blocks publish while `error_count > 0` or warnings are not accepted. `on_submit` enqueues the compile-and-migrate job and supersedes the previous version. Cancel is disallowed; use Retire on the form instead.

`compiled_meta` shape (versioned, read by the compiler, exports and all three runtimes):

```json
{"metaVersion": 1, "astVersion": 1, "form_id": "hh_survey", "version": "2026110301",
 "doctypes": {"parent": "XF Household Survey", "repeats": {"/member": "XF hh_survey member"}},
 "fields": [{"path": "/member/age", "name": "age", "fieldname": "age", "doctype": "XF hh_survey member",
             "fieldtype": "Int", "introduced_in": "2026100101", "retired_in": null}],
 "choices": {"yes_no": [{"name": "yes", "label": {"English": "Yes", "Hindi": "हाँ"}, "filters": {}}]},
 "expressions": {"/member/age": {"relevant": {}, "constraint": {}, "required": {}}},
 "calc_order": ["/total_members", "/share_children"],
 "labels": {"/member/age": {"English": "Age", "Hindi": "उम्र"}}}
```

**4.3 XLSForm Settings** — Single.

| Fieldname | Fieldtype | Default | Notes |
| --- | --- | --- | --- |
| max\_upload\_mb | Int | 5 |  |
| max\_questions | Int | 400 | Per form, repeats included |
| max\_choices\_per\_list | Int | 5000 | Ceiling while choices live in JSON |
| select\_threshold | Int | 50 | Lists above this render as Autocomplete instead of Select |
| row\_budget\_bytes | Int | 60000 | Safety margin under InnoDB's 65,535 |
| doctype\_prefix | Data | XF | Prefix of generated DocTypes |
| designers\_can\_publish | Check | 1 | 0 = only a System Manager can publish |
| default\_language | Data | English |  |

**4.4 Generated data DocTypes** — created by the compiler with `custom = 1` in module `XLSForm Data`, never shipped as app JSON, so each site (tenant) has its own. Every generated parent carries these reserved fields (prefix `xf_`, which questions may not use):

| Fieldname | Fieldtype | Notes |
| --- | --- | --- |
| xf\_form | Link XLSForm | `ignore_user_permissions = 0`, so User Permissions on XLSForm restrict the data |
| xf\_version | Link XLSForm Version | Version the record was collected on |
| xf\_instance\_id | Data, unique | `uuid:` instance ID; makes offline sync idempotent |
| xf\_channel | Select | Desk, Web, mForm, API, Test |
| xf\_device\_id | Data |  |
| xf\_started\_at / xf\_ended\_at | Datetime | From `start` / `end` metadata |

**Permissions**

| Role | XLSForm | XLSForm Version | Generated data | Scope |
| --- | --- | --- | --- | --- |
| System Manager | All | All | All | Whole site |
| XLSForm Designer | Create, read, write | Create, read, submit | Read | All forms on the site |
| XLSForm Reviewer | Read | Read | Read, write, export, report | Forms granted by User Permission on XLSForm |
| XLSForm Collector | Read | Read (published only) | Create; read and write if owner | Forms granted by User Permission on XLSForm |

Granting a collector or reviewer access to a form = one standard User Permission record (`allow = XLSForm`, `for_value = <form_id>`). The XLSForm form has a **Share with users** button that creates these records, so designers never open the User Permission list. The four roles ship as fixtures.

## 5. Compiler rules

The compiler turns one validated `parsed_json` into DocType definitions and a `compiled_meta` blob; it is a pure function (`compile(parsed, previous_meta) -> plan`) so it can be unit-tested without a database, and a separate `apply(plan)` performs the DocType inserts and schema changes. Type mapping follows the matrix in section 2.

**DocType naming**

- Parent: `{prefix} {Form Title}`, trimmed to 50 characters, de-duplicated with `  2 `, `  3 `. MariaDB table names cap at 64 characters and Frappe adds `tab`, so 61 is the hard limit.
- Child (repeat): `{prefix} {form_id} {repeat name}`, same limits, `istable = 1`.
- The DocType name is frozen at first publish; renaming the form changes only its title.

**Fieldname sanitisation** (deterministic, stored in compiled\_meta.fields so it never changes across versions)

1. Lower-case; replace `-` and `.` with `_`; strip anything outside `[a-z0-9_]`.
2. Prefix `f_` if it starts with a digit.
3. Reserved names get suffix `_q`: Frappe standard columns (`name`, `owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx`, `parent`, `parentfield`, `parenttype`, `_user_tags`, `_comments`, `_assign`, `_liked_by`, `_seen`), MariaDB reserved words, and the `xf_` prefix.
4. Longer than 58 characters: truncate to 51 and add `_` plus a 6-character hash of the full path.
5. Collision after steps 1–4: append `_2`, `_3`.

Exports always use the original XLSForm names, so data matches what the client sees in Excel.

**Layout**

- Each top-level `begin_group` becomes a Section Break labelled with the group label; a nested group becomes a Section Break with the parent label prefixed ("Household › Assets"). Frappe sections do not nest.
- `relevant` on a group is copied onto the Section Break and AND-ed into every child field's visibility.
- A form with more than 3 top-level groups uses Tab Breaks for top-level groups. \[ASSUMPTION — confirm\]
- `field-list` appearance has no Desk effect; mForm renders the group as one page.

**Repeats**

- `begin_repeat` becomes a `Table` field on the parent pointing to a generated child DocType.
- `repeat_count` becomes a constraint (row count must equal the expression) plus a runtime that adds rows automatically.
- A repeat inside a repeat is a validation error in v1 (`E-REPEAT-NESTED`).

**Select fields**

- `select_one` with no `choice_filter` and up to `select_threshold` choices becomes `Select`; its `options` hold choice names, and labels in every language live in `compiled_meta.choices` for the renderers.
- Otherwise it becomes `Autocomplete`. The runtime fills its options from `compiled_meta.choices`, applies the evaluated `choice_filter` on the client, and the server hook rejects any value not in the filtered list.
- `*_from_file` lists are read from the CSV attached to the version and stored in `compiled_meta.choices`; lists above `max_choices_per_list` fail validation with `E-LIST-TOO-LARGE` until the v1.1 `XLSForm Choice` DocType lands.
- `select_multiple` is always `Small Text` storing space-separated names. Choice names containing spaces are a validation error (`E-CHOICE-SPACE`), matching ODK.

**Expressions in DocField properties**

Frappe evaluates `depends_on`, `mandatory_depends_on` and `read_only_depends_on` itself. The compiler sets each to `eval:xlsform.relevant(doc, "<path>")` (and the equivalents), which calls the shared evaluator with the AST from `compiled_meta`. It never writes translated JavaScript strings into DocFields, so there is one evaluator and no drift.

**Row-size budget**

InnoDB rejects tables whose declared row size exceeds 65,535 bytes. The compiler sums the budget before any DDL and fails validation with `E-ROW-BUDGET` if it exceeds `row_budget_bytes`.

| Fieldtype | Bytes counted |
| --- | --- |
| Small Text, Long Text, Attach, JSON, Geolocation | 12 (stored off-page) |
| Select, Data, Autocomplete | 4 × `length` + 2; compiler sets `length` to the longest choice name rounded up to 20, minimum 20, and 140 for Autocomplete |
| Int, Check | 4 |
| Float | 10 |
| Date / Time / Datetime | 3 / 3 / 8 |
| Frappe standard columns | \~3,500 fixed |

**Schema evolution between versions** (computed as `change_summary` and shown to the designer before publish)

| Change in new version | Compiler action |
| --- | --- |
| Question added | New column |
| Question removed | Column kept, field hidden, `retired_in` set |
| Label, hint, relevance, constraint, choices changed | Metadata only; no DDL |
| Type changed compatibly (integer → decimal, text → select) | New column `<name>_v<version>`; old one retired. Data is never cast in place |
| Name changed | Treated as remove + add; warning `W-RENAME` explains data will not carry over |
| Moved into or out of a repeat | Treated as remove + add; warning `W-MOVE-REPEAT` |

The compiler never drops a column or a table. Schema changes run through `frappe.get_doc("DocType").save()` inside a background job with a site-level lock, so two publishes cannot race.

## 6. Expression engine

Expressions are parsed once, in Python, at upload; every runtime only evaluates the resulting JSON AST. This keeps one parser and three small evaluators — Python (server re-validation), TypeScript (Desk and web) and Dart (mForm) — that must all pass one shared conformance suite.

**Pipeline**

1. Tokenise and parse each `relevant`, `constraint`, `calculation`, `required`, `choice_filter`, `repeat_count` and `default` cell into an AST.
2. Resolve every `${name}` to an absolute path; unknown names fail with `E-REF-UNKNOWN` and a "did you mean" suggestion (edit distance ≤ 2).
3. Check each function against the v1 allow-list and its arity.
4. Build the dependency graph of calculations and relevances; a cycle fails with `E-CALC-CYCLE` naming every field in the loop.
5. Store the ASTs plus a topological evaluation order in `compiled_meta`.

**AST shape** (stable, versioned with `"astVersion": 1`)

```json
{"op": "and", "args": [
  {"op": "=", "args": [{"ref": "/consent"}, {"lit": "yes"}]},
  {"op": ">", "args": [{"ref": "/age"}, {"lit": 17}]},
  {"fn": "selected", "args": [{"ref": "/services"}, {"lit": "health"}]}
]}
```

Refs inside a repeat carry `"ctx": "current"` (same row) or `"ctx": "all"` (a node-set across rows, for `sum`, `count`); `position(..)` compiles to `{"fn": "position"}`.

**Semantics the evaluators must match ODK on** (each is a fixture group in the conformance suite)

- An unanswered question is the empty string `""`, not null.
- Comparisons: if either side is a number, both are converted to numbers; `""` converts to NaN, and any comparison with NaN is false.
- Booleans: `""` and `0` are false; any other string is true.
- Dates are days since 1970-01-01; date minus date gives days; `today()` uses the device's local date.
- `select_multiple` values are space-separated strings; `selected()` splits on whitespace.
- `int()` truncates toward zero; `round(x, n)` rounds half away from zero.
- `sum()` and `count()` over an empty repeat return 0.
- `once(x)` keeps the first non-empty value across later evaluations of the same record.
- Calculations re-run in topological order after any change, until stable (max one pass, since cycles are rejected).
- Values of non-relevant fields are treated as `""` in other expressions and cleared on save.

**Packages** (all MIT, so other projects can use them outside Frappe)

| Package | Language | Contains | Published to |
| --- | --- | --- | --- |
| `xlsform-expr` | Python | Parser + evaluator | Inside the Frappe app; also PyPI |
| `@xlsform/expr` | TypeScript | Evaluator only | npm; bundled into the app's Desk assets |
| `xlsform_expr` | Dart | Evaluator only | pub.dev; consumed by mForm |
| `xlsform-expr-fixtures` | JSON | Conformance cases: AST + context + expected result | Git submodule used by all three CI pipelines |

Target: 300+ fixtures before v1, including fixtures generated from 50 anonymised real client forms.

## 7. Validation and user-friendly errors

A designer fixes every problem in one round: the validator reports all issues at once, each pinned to an Excel cell, written in plain language with a suggested fix, and it never shows a stack trace. Validation runs on upload and again on publish.

**Rules every issue follows**

1. **Located**: sheet, row number as Excel shows it, column header and cell reference (`survey!F14`).
2. **Plain language**: says what is wrong in the designer's terms ("question", "choice list"), never Frappe or Python terms ("DocField", "KeyError").
3. **Fixable**: one suggested fix, with the corrected value when it can be computed ("Did you mean `${hh_size}`?").
4. **Coded**: a stable code (`E-REF-UNKNOWN`) linking to a docs page with a worked example.
5. **Complete**: all issues in a stage are collected; a later stage is skipped only when it cannot run on broken input, and the report says so.
6. **Translatable**: every message goes through `frappe._()`; codes stay in English.
7. **Severity**: Error blocks publish; Warning allows publish after the designer ticks "I understand"; Info is advice only.

**Five stages, in order**

| Stage | Checks | Stops later stages if it fails? |
| --- | --- | --- |
| 1. File | `.xlsx` only (`.xls`, `.xlsm` and password-protected files rejected), size limit, readable, required sheets present | Yes |
| 2. Structure | Required columns, unknown columns, duplicate names, unmatched `begin_`/`end_`, empty rows inside groups | Yes |
| 3. Meaning | Types, choice lists, expressions, references, cycles, settings values | No |
| 4. Frappe limits | Question count, row budget, name length after sanitising | No |
| 5. Version diff | Renames, removals, type changes vs the published version | No (warnings only) |

**Where designers see issues**

- On the XLSForm Version form: a summary bar ("3 errors, 2 warnings") and a table grouped by sheet, sorted by row, with each cell reference clickable to copy.
- As a downloadable **annotated copy of their own workbook**: offending cells filled red (errors) or amber (warnings) with the message as an Excel cell comment. This is the main fixing workflow, since designers live in Excel.
- In the API response (section 11) as structured JSON for integrations.
- pyxform's own errors are caught, mapped to a code where the pattern is known, and the row number is parsed out of its message; unmapped ones appear as `E-PYXFORM` with the cleaned message, and are logged so the mapping can grow.

**Issue catalogue (v1)**

| Code | Severity | Message shown to the designer | Suggested fix |
| --- | --- | --- | --- |
| E-FILE-TYPE | Error | This file is not an Excel workbook (.xlsx). | Save it as .xlsx from Excel or Google Sheets and upload again. |
| E-FILE-SIZE | Error | The file is 9 MB; the limit is 5 MB. | Remove embedded images or unused sheets. |
| E-FILE-PROTECTED | Error | The workbook is password-protected, so it can't be read. | Remove the password and upload again. |
| E-SHEET-MISSING | Error | The workbook has no "survey" sheet. | Rename your questions sheet to "survey" (lower case). |
| E-COL-MISSING | Error | The survey sheet has no "type" column. | Add columns named type, name and label in row 1. |
| W-COL-UNKNOWN | Warning | Column "lable" on the survey sheet isn't recognised and will be ignored. | Did you mean "label"? |
| E-NAME-MISSING | Error | Row 14 has a question type but no name. | Add a short name, e.g. `hh_size`. |
| E-NAME-INVALID | Error | "Household size" in survey!B14 can't be used as a name: names can't contain spaces. | Use `household_size`. |
| E-NAME-DUPLICATE | Error | The name `age` is used in rows 9 and 31. | Rename one, e.g. `child_age`. |
| E-TYPE-UNKNOWN | Error | "select one" in survey!A20 isn't a question type. | Did you mean `select_one`? |
| E-TYPE-UNSUPPORTED | Error | "rank" questions aren't supported yet (row 22). | See the supported list in the docs, or use select\_multiple. |
| E-LIST-MISSING | Error | Row 18 uses choice list "districts", but the choices sheet has no list with that name. | Add it to the choices sheet, or fix the spelling (found: "district"). |
| E-CHOICE-DUPLICATE | Error | Choice "yes" appears twice in list "yes\_no" (choices rows 4 and 6). | Remove or rename one. |
| E-CHOICE-SPACE | Error | Choice name "not sure" (choices!B9) contains a space. | Use `not_sure`; the label can keep the space. |
| E-LIST-TOO-LARGE | Error | Choice list "villages" has 12,400 choices; the limit is 5,000. | Split it with a cascading filter (district, then village), or ask your administrator about larger lists. |
| E-GROUP-UNCLOSED | Error | The group started in row 12 (`household`) is never closed. | Add an `end_group` row where the group should end. |
| E-GROUP-MISMATCH | Error | Row 40 closes a repeat, but the open block is a group started in row 33. | Change row 40 to `end_group`, or add the missing `end_repeat`. |
| E-REPEAT-NESTED | Error | Repeat `member` (row 30) is inside repeat `household` (row 12); repeats inside repeats aren't supported yet. | Move `member` out, or flatten it into the outer repeat. |
| E-REF-UNKNOWN | Error | survey!H25 refers to `${hh_sise}`, which isn't a question in this form. | Did you mean `${hh_size}`? |
| E-REF-SELF | Error | Row 25's constraint refers to its own name; use `.` for "this answer". | Replace `${age}` with `.` |
| E-EXPR-SYNTAX | Error | The formula in survey!H25 can't be read: a bracket opened at character 12 is never closed. | Check the brackets in: `if(${a} > 3, 'x'` |
| E-EXPR-QUOTE | Error | survey!H25 uses curly quotes (‘ ’), which formulas don't accept. | Replace them with straight quotes ('). |
| E-FN-UNSUPPORTED | Error | `pulldata()` in survey!J8 isn't supported yet. | See the supported function list in the docs. |
| E-FN-ARGS | Error | `selected()` in survey!H12 needs 2 values but got 1. | Example: `selected(${services}, 'health')` |
| E-CALC-CYCLE | Error | These calculations depend on each other in a loop: `total` → `share` → `total`. | Break the loop so one of them doesn't use the other. |
| E-REPEAT-SCOPE | Error | Row 50 (outside repeat `member`) uses `${member_age}` without `sum()` or `count()`. | Wrap it, e.g. `sum(${member_age})`. |
| E-VERSION-ORDER | Error | Version "2024-01" is not newer than the published version "2025-03". | Set a higher value in settings!C2. |
| E-LIMIT-QUESTIONS | Error | The form has 512 questions; the limit is 400. | Split it into two forms, or ask your administrator to raise the limit. |
| E-ROW-BUDGET | Error | The form has too many short-answer questions outside repeats to store in one record. | Move some into a repeat, or change select\_one lists over 50 choices to use a choice file. |
| W-APPEARANCE | Warning | Appearance "quick" (row 11) isn't supported and will be ignored. | Remove it, or keep it for use in ODK. |
| W-RENAME | Warning | `village` was removed and `village_name` added; existing answers to `village` won't move to the new question. | Keep the old name if it's the same question. |
| W-TYPE-CHANGE | Warning | `income` changed from integer to text; earlier answers stay in the old column. | Confirm this is intended. |
| I-NO-LABEL | Info | Row 19 has no label, so collectors will see only its name. | Add a label. |
| E-PYXFORM | Error | (cleaned message from the XLSForm converter, with row if known) | Linked to the XLSForm.org reference. |

**Before publish**: designers get a **Preview** that renders the version as a web form with live skip logic, plus **Test submission**, which saves into a sandbox (records flagged `xf_channel = Test`, excluded from reports and deleted on publish).

## 8. Runtime: Desk, web and mForm

All three runtimes read the same `compiled_meta` and use the shared evaluators; the server re-checks everything on save, so a client that skips validation can't store bad data.

**Desk**

- On publish the compiler creates a standard **Client Script** record for each generated DocType whose body is one line, `xlsform.bind(frm)`. The `xlsform.bind` bundle ships via `app_include_js` and wires relevance, constraints, calculations, cascading choice lists (Autocomplete options from `compiled_meta.choices`), `repeat_count` and select\_multiple checkboxes.
- Constraint failures show inline under the field with the designer's `constraint_message`, or a generated sentence ("Must be between 0 and 120") when none is given.
- Labels and hints in other languages are written as standard **Translation** records, so Desk follows the user's language setting.

**Web**

- When `allow_web` is on, the compiler creates a standard **Web Form** for the parent DocType (login required) and attaches the same binding in its client script.
- Repeats render as Web Form tables. \[ASSUMPTION — confirm\] If Web Form tables prove too limited for repeat UX, v1.1 replaces the Web Form with a Frappe UI page at `/xf/<form_id>` using the same API.

**Server (every channel)**

A `doc_events["*"]["validate"]` hook returns at once unless the DocType has `xf_form`, then, in order: recompute calculations, clear non-relevant values, enforce `required`, enforce constraints, check `xf_instance_id` uniqueness. Failures raise one `frappe.ValidationError` listing every failed question by label, not fieldname.

**mForm (offline)**

- `frappe-mobile-control` exposes published versions and their `compiled_meta` through `xlsform.api.mobile.forms` (section 11); mForm caches them per device.
- Each submission carries `xf_instance_id` (a UUID made on the device) and `xf_version`. Re-sending the same instance is a no-op that returns the existing record, so retries after a bad network are safe.
- A record collected on a superseded version is accepted, because columns are never dropped. A record for a retired form is rejected with a message the collector can understand: "This form was closed on 12 Mar 2027; contact your supervisor."
- Attachments upload first, then the record references the returned file URLs.

## 9. Versioning and publishing lifecycle

A version is published only with zero errors, is never edited after that, and stays readable after it is superseded. Every change goes through a new upload.

&#91;embedded content: XLSForm Version states · 5 states, 1 check\]

- **Uploaded → Valid or Invalid**: validation runs automatically in a background job. An Invalid version keeps its report; the designer fixes the workbook in Excel and uploads it as a new version.
- **Valid → Published**: the designer reviews the change summary (section 5) and the preview, ticks any warnings as understood, and publishes. If `designers_can_publish` is off, a System Manager publishes.
- **Published → Superseded**: happens automatically when a newer version is published. Records collected on it stay valid and mForm devices can still submit it until they sync the newer version.
- **Retiring a form** (on XLSForm, not a version) closes it to new submissions on every channel; existing data, reports and exports are unaffected. A retired form can be reopened by publishing a new version.
- **Version string**: taken from the settings sheet, compared as a date-like or numeric string; if `version` is blank, the app proposes `YYYYMMDDNN` and writes it into the annotated workbook so the designer's file stays in sync.

## 10. Permissions, security and multi-tenancy

Designers change schema only through the compiler, which runs with elevated rights inside narrow, audited code paths; no client user ever holds DocType, Customize Form, Client Script or Server Script permissions.

- **Privilege boundary**: `apply(plan)` checks the caller's role and XLSForm access, then saves with `ignore_permissions` inside a background job (never via `frappe.set_user`). It only touches DocTypes whose module is `XLSForm Data` and whose name starts with `doctype_prefix`; any other target aborts the job.
- **Per-form access with standard User Permissions**: every generated DocType has `xf_form` (Link to XLSForm, `ignore_user_permissions = 0`), so a collector or reviewer with a User Permission on XLSForm sees and creates records only for those forms, across list views, reports, exports and the REST API. No custom `has_permission` or `permission_query_conditions` hooks. The **Share with users** action (`xlsform.api.forms.share`) creates and removes these User Permission records after checking that the caller is a Designer, so designers never need User Permission rights themselves.
- **Untrusted spreadsheets**: workbooks are read with `openpyxl` in read-only mode with formulas off; macros, external links and embedded objects are ignored. Cell text is HTML-escaped wherever it is rendered (labels, hints, notes), so a label can't inject script into Desk or Web Forms. Markdown in labels is rendered with a safe allow-list.
- **No code from users**: expressions are parsed into an AST and evaluated by the app's evaluators. They are never passed to `eval`, `frappe.safe_eval`, or written as JavaScript.
- **Resource limits**: upload size, question count, choices per list (default 5,000) and expression length (default 2,000 characters) are capped in XLSForm Settings. Parsing runs in a background job with a 120-second timeout.
- **Audit**: XLSForm, XLSForm Version and every generated DocType have `track_changes = 1`; publishing is recorded by the version's docstatus, and User Permission changes appear in Frappe's standard logs.
- **Multi-tenancy**: each Frappe site is a tenant, so forms, generated DocTypes and data are isolated by the site's own database. Nothing is shared across sites, and the app works unchanged on Frappe Cloud multi-site benches.
- **Uninstall**: `before_uninstall` warns that generated DocTypes and their data will be removed and requires a confirmed setting; it never runs silently.

## 11. API surface

All endpoints are whitelisted methods under `xlsform.api.*`, return JSON, enforce the permissions in section 10, and are rate-limited with Frappe's `@rate_limit`. Standard REST (`/api/resource/<generated DocType>`) also works for data, because generated DocTypes are ordinary DocTypes.

| Method | Endpoint | Who | Purpose |
| --- | --- | --- | --- |
| POST | `xlsform.api.forms.upload` | Designer | Upload an xlsx (+ CSV attachments); creates the XLSForm on first upload and an XLSForm Version; returns `{form, version, state, issues[]}` |
| GET | `xlsform.api.forms.validation_report` | Designer | Issues for a version, as JSON or `?format=xlsx` for the annotated workbook |
| GET | `xlsform.api.forms.preview` | Designer | Rendered preview payload for a version |
| POST | `xlsform.api.forms.publish` | Designer | Submit a Valid version (accepting warnings if any); returns a background job id |
| GET | `xlsform.api.forms.publish_status` | Designer | Job progress: `queued`, `compiling`, `migrating`, `done`, `failed` (with issues) |
| POST | `xlsform.api.forms.retire` | Designer | Close a form to new submissions |
| POST | `xlsform.api.forms.share` | Designer | Grant or revoke a user's access to a form: creates or deletes the standard User Permission (`allow = XLSForm`) and adds the Collector or Reviewer role if missing |
| GET | `xlsform.api.forms.template` | Anyone logged in | Download a starter XLSForm with all three sheets and examples |
| GET | `xlsform.api.mobile.forms` | Collector | Forms the user's User Permissions allow, with the published version's `compiled_meta`; supports `If-None-Match` |
| POST | `xlsform.api.mobile.submit` | Collector | Idempotent submit keyed on `xf_instance_id`; returns the record name |
| GET | `xlsform.api.data.export` | Reviewer | CSV or XLSX of a form's data with original XLSForm column names (from `compiled_meta.fields`), one sheet per repeat |

**Issue object** (used by upload, validation\_report and failed publishes):

```json
{"code": "E-REF-UNKNOWN", "severity": "error",
 "sheet": "survey", "row": 25, "column": "relevant", "cell": "H25",
 "message": "survey!H25 refers to ${hh_sise}, which isn't a question in this form.",
 "suggestion": "Did you mean ${hh_size}?",
 "docs_url": "/xlsform-docs/errors#E-REF-UNKNOWN"}
```

## 12. Frappe standards and Marketplace readiness

The app targets Frappe v15 and v16, is scaffolded with `bench new-app`, and is listed through both the Frappe Cloud dashboard (v1 marketplace) and a pull request to the `frappe/marketplace` registry (Cloud v2), with every listing requirement below tracked as a release gate.

**Frappe app conventions**

- [ ] Scaffolded with `bench new-app xlsform`; `pyproject.toml` (flit), `hooks.py`, `modules.txt` (XLSForm, XLSForm Data), `patches.txt`.
- [ ] Branches `version-15`, `version-16`, `develop`; CI matrix runs on both versions. Version-specific code is gated on `frappe.__version__`.
- [ ] Extend only through hooks (`doc_events`, `app_include_js`, `fixtures`, `after_install`, `before_uninstall`); no monkey-patching or overriding core pages.
- [ ] A Settings DocType for global behaviour (XLSForm Settings, 4.7), as the authoring guidelines recommend.
- [ ] Roles, Workspace and a starter XLSForm template shipped as fixtures; `after_install` creates the `XLSForm Data` module and default settings.
- [ ] All user-facing strings wrapped in `_()` / `__()`; Hindi translation file shipped in v1. \[ASSUMPTION — confirm language list\]
- [ ] v16 sidebar: `add_to_apps_screen` entry with lower-case `name`, Workspace, Workspace Sidebar and Desktop Icon records.
- [ ] Python dependencies pinned in `pyproject.toml`: `pyxform` (4.x), `openpyxl`. No system packages or Java (ODK Validate is not used), so the app installs on Frappe Cloud.
- [ ] Formatting and lint via pre-commit: ruff, ruff-format, eslint, prettier; Frappe's semgrep rules clean.

**Marketplace listing requirements**

The Frappe Cloud guidelines require [a publicly open-source app hosted on GitHub that you own, reviewed before publishing](https://docs.frappe.io/cloud/marketplace.md); [support for the current stable Frappe version, a logo, description and screenshots, a unique app name, a Support URL and a Privacy Policy URL](https://docs.frappe.io/cloud/marketplace/marketplace-guidelines.md); and [a passing GitHub Actions CI for linters and server tests](https://docs.frappe.io/cloud/marketplace/app-authoring-guidelines.md). Under Frappe Cloud v2, [listings move to pull requests against the `frappe/marketplace` registry on GitHub](https://discuss.frappe.io/t/the-new-marketplace/164661).

| Requirement | Plan | Owner |
| --- | --- | --- |
| Open source on GitHub, owned by publisher | `dhwani-ris/xlsform` (AGPL-3.0); expression packages MIT |  |
| Unique app name | Check `xlsform` is free on the marketplace before the first tag; fallback `xlsform_frappe` |  |
| Supports current stable Frappe | v16 primary, v15 supported |  |
| CI: linters + server tests passing | `.github/workflows/ci.yml`, `linters.yml`, `ui-tests.yml` |  |
| Semgrep (Frappe rules) clean | Runs in `linters.yml` |  |
| Logo | Square, ≥ 200 × 200 px, no text in it |  |
| Short description | One sentence, 40–80 chars, e.g. "Build data-collection forms in Excel and collect into DocTypes" |  |
| Long description | Features + compatibility matrix link; no install steps |  |
| Screenshots | Upload + error report, annotated workbook, preview, Desk form, mForm |  |
| Support URL, Privacy Policy URL | GitHub Issues; Dhwani privacy page |  |
| Demo video | 3–4 minutes: upload → fix errors → publish → collect offline → report |  |
| Category | Utilities (or Data Collection if available) |  |
| Cloud v2 registry entry | PR adding the app to `apps.json` in `frappe/marketplace` |  |

## 13. Testing strategy

Every merge to `develop` must pass five test layers on both Frappe v15 and v16; a validator or compiler change without a fixture that exercises it is rejected in review.

| Layer | Tool | What it proves | Gate |
| --- | --- | --- | --- |
| Validator fixtures | pytest (no site) | Each issue code fires on a minimal bad workbook, with the right sheet, row, column and message; good workbooks produce zero issues | 1 failing and 1 passing fixture per code in section 7 |
| Compiler unit | pytest (no site) | `compile()` output for type mapping, sanitising, layout, repeats, row budget and version diffs, as snapshot tests | 95% line coverage on `compiler/` |
| Expression conformance | pytest, vitest, `dart test` | Python, TypeScript and Dart evaluators give identical results on the shared fixtures | 300+ fixtures, 100% pass in all three |
| Server integration | `bench run-tests --app xlsform` (FrappeTestCase) | Upload → publish → DocType exists → insert valid and invalid records → republish with changes → old records still valid → permissions per role | All section 7, 8 and 10 rules covered |
| UI end-to-end | Playwright against a real bench | Designer uploads a broken form, sees issues, downloads the annotated workbook, fixes it, previews, publishes; collector submits on Desk and web | Smoke suite on every PR, full suite nightly |

**Real-world corpus**: 50 anonymised production XLSForms from client projects (plus public samples from XLSForm.org) run end to end nightly. A regression in any one of them blocks release.

**Performance budgets** (measured in CI on a standard runner): validating a 400-question form < 5 s; compile + migrate < 30 s; server-side `validate` hook < 150 ms per record; evaluating all expressions of a 400-question form in the browser < 50 ms.

**Security tests**: label containing `<script>` renders inert; workbook with external links and macros is read safely; a Collector calling publish or upload gets 403; a designer cannot touch a DocType outside the `XLSForm Data` module.

## 14. Repo layout, CLAUDE.md and Claude Code build plan

Claude Code builds the app milestone by milestone, test-first, from this document committed as `docs/REQUIREMENTS.md`; `CLAUDE.md` holds the rules it must follow in every session.

**Repository layout**

```text
xlsform/
├── CLAUDE.md
├── README.md
├── license.txt                      # AGPL-3.0
├── pyproject.toml
├── docs/
│   ├── REQUIREMENTS.md              # this document
│   ├── compatibility.md             # section 2, public
│   └── errors/                      # one page per issue code
├── .github/workflows/               # ci.yml, linters.yml, ui-tests.yml, expr.yml
├── packages/
│   ├── expr-fixtures/               # shared JSON conformance cases
│   ├── expr-ts/                     # @xlsform/expr
│   └── expr-dart/                   # xlsform_expr
├── tests/fixtures/workbooks/        # good/ and bad/<ISSUE-CODE>.xlsx
└── xlsform/
    ├── hooks.py
    ├── modules.txt
    ├── patches.txt
    ├── fixtures/                    # roles, workspace, template
    ├── xlsform/doctype/             # the three DocTypes in section 4
    ├── parser/                      # openpyxl reading + pyxform wrapper
    ├── validator/                   # stages, issue catalogue, annotated xlsx
    ├── expr/                        # Python parser + evaluator
    ├── compiler/                    # compile() pure, apply() side-effects
    ├── runtime/                     # server validate hook, permissions
    ├── api/                         # forms.py, mobile.py, data.py
    ├── public/js/xlsform.bundle.js  # Desk + web binding
    └── translations/hi.csv
```

**CLAUDE.md** (commit verbatim, then refine)

```markdown
# CLAUDE.md — xlsform

Spec: docs/REQUIREMENTS.md is the source of truth. If code and spec disagree, stop and ask.

## Commands
- Python tests (no site): pytest xlsform/tests/unit
- Frappe tests: bench --site test.localhost run-tests --app xlsform
- TS evaluator: cd packages/expr-ts && npm test
- Dart evaluator: cd packages/expr-dart && dart test
- Lint: pre-commit run --all-files

## Rules
- Test first. Every issue code needs one failing and one passing workbook in tests/fixtures/workbooks.
- compiler/compile() stays pure: no frappe.db, no frappe.get_doc. Side effects only in compiler/apply.py.
- Never write JavaScript strings into DocField properties. Use eval:xlsform.* calls that read ASTs.
- Never drop a column or table. Never cast data in place.
- Never pass user text to eval, exec, safe_eval or frappe.render_template.
- Every user-facing message: _() / __(), plain language, no stack traces, with sheet/row/column.
- Expression semantics change = new fixture in packages/expr-fixtures, passing in Python, TS and Dart.
- Support Frappe v15 and v16; gate version-specific code on frappe.__version__.
- Per-form access = standard User Permissions on XLSForm via the xf_form link. Do not add has_permission or permission_query_conditions hooks.
- Do not add DocTypes beyond XLSForm, XLSForm Version and XLSForm Settings without updating section 4 first; prefer JSON on the version or a standard Frappe feature.
- Run pre-commit before finishing a task.

## Do not
- Do not add Java, Node at runtime, or system packages (Frappe Cloud must install it).
- Do not touch DocTypes outside module "XLSForm Data" from the compiler.
- Do not grant designers DocType, Customize Form or script permissions.
```

**Milestones** (each one is a Claude Code working session or a few; merge only when its done-criteria pass in CI)

1. **Scaffold** — `bench new-app`, CI on v15 + v16, pre-commit, semgrep, the three DocTypes (XLSForm, XLSForm Version, XLSForm Settings), roles as fixtures. *Done:* empty app installs and uninstalls cleanly on both versions; CI green.
2. **Reader + structure validation** — openpyxl reading, stages 1–2, issue object, catalogue entries for those stages. *Done:* every stage 1–2 code has passing fixtures; report renders on XLSForm Version.
3. **pyxform integration + meaning validation** — stage 3, pyxform error mapping, "did you mean" suggestions. *Done:* all stage 3 codes covered; 50-form corpus produces no unmapped `E-PYXFORM` without a logged pattern.
4. **Expression engine (Python)** — parser, AST, evaluator, dependency graph, cycle detection; fixtures package. *Done:* 300 fixtures pass.
5. **Compiler** — `compile()` + `apply()`, naming, sanitising, layout, repeats, selects, row budget, compiled\_meta. *Done:* snapshot tests pass; publishing 10 sample forms creates working DocTypes.
6. **Versioning** — change summary, republish, retire, stage 5 warnings. *Done:* a form republished 5 times with adds, removes and type changes keeps all old records readable and valid.
7. **Runtime** — server validate hook, TS evaluator, Desk binding via Client Script, Web Form generation, translations. *Done:* TS passes all fixtures; Playwright smoke suite green.
8. **Designer UX** — annotated workbook download, preview, test submissions, starter template, Share with users (User Permissions), docs pages per issue code. *Done:* a first-time user fixes a broken sample form using only the app's messages, in a moderated test with 3 client M&E staff.
9. **APIs + mForm** — `xlsform.api.*`, Dart evaluator, mForm integration in `frappe-mobile-control`, idempotent offline submit. *Done:* Dart passes all fixtures; offline round trip with retries creates exactly one record.
10. **Release** — README, compatibility page, screenshots, demo video, marketplace listing, `frappe/marketplace` PR, tag `v1.0.0`. *Done:* listing submitted; every section 12 checkbox ticked.

**Working with Claude Code**

- Start each milestone with: "Read CLAUDE.md and docs/REQUIREMENTS.md section N. Write the failing tests first, show them, then implement."
- Keep one milestone per branch and pull request; ask Claude Code for a PR description that maps changes to section numbers.
- When the spec is wrong or silent, update `docs/REQUIREMENTS.md` in the same PR, so the doc stays the source of truth.

## 15. Public README

This is the GitHub `README.md` for v1; the marketplace long description reuses the first four sections without the install steps, which Frappe Cloud handles itself.

```markdown
# XLSForm for Frappe

Build data-collection forms in Excel and collect straight into Frappe DocTypes — on Desk, on the web, and offline on mobile.

XLSForm is the spreadsheet standard used by ODK, KoboToolbox, SurveyCTO and Ona.
If your team already writes XLSForms, upload them here and get a working form in minutes,
with every answer stored as a normal Frappe document you can report on, link and automate.

## Features
- Upload an .xlsx XLSForm; no developer needed to create or change forms
- Clear, cell-level error messages, plus a downloadable copy of your workbook with problems highlighted
- Skip logic, constraints, calculations, cascading choices and repeats
- Versioned forms: republish safely, earlier records stay valid
- Multilingual labels (label::Hindi, label::English, …)
- Offline collection on Android and iOS through mForm
- Data lives in real DocTypes: reports, permissions, workflows, REST API and Insights all work
- Per-form access for designers, collectors and reviewers

## Compatibility
Supports a documented subset of XLSForm: see docs/compatibility.md.
Anything unsupported is rejected at upload with a clear message, never silently ignored.
Frappe v15 and v16.

## How it works
1. A Form Designer uploads an XLSForm.
2. The app checks it and lists any problems by sheet, row and column.
3. On publish, the form becomes a DocType (repeats become child tables).
4. Collectors fill it on Desk, the web, or mForm, online or offline.

## Installation (self-hosted)
    bench get-app https://github.com/dhwani-ris/xlsform --branch version-16
    bench --site your.site install-app xlsform

## Roles
- XLSForm Designer: uploads, previews and publishes forms
- XLSForm Collector: fills forms
- XLSForm Reviewer: views, edits and exports data

## Contributing
Read CLAUDE.md and docs/REQUIREMENTS.md. Every change needs tests;
expression changes need a new fixture in packages/expr-fixtures that passes in Python, TypeScript and Dart.
Run `pre-commit run --all-files` before opening a pull request.

## Related
- @xlsform/expr (npm) and xlsform_expr (pub.dev): standalone MIT evaluators for XLSForm expressions
- mForm: offline mobile client for Frappe (frappe-mobile-sdk)

## License
AGPL-3.0. Expression packages are MIT.
```

**Open questions**

- [ ] Final app name: `xlsform` vs a brand name; confirm it is unused on the marketplace.
- [ ] Publishing GitHub org and repo (`dhwani-ris/xlsform` assumed).
- [ ] Web runtime: generated Web Forms (v1 plan) or a Frappe UI page from day one.
- [ ] Languages to ship translations for in v1 beyond Hindi.
- [ ] Whether designers publish directly or need System Manager approval by default.
