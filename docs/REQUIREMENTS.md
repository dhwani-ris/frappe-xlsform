# XLSForm for Frappe — Requirements

Revision 3 · 3 Nov 2026 · supersedes `docs/original/REQUIREMENTS-2026-11-03.md` (revision 1). Revision 3 adds what building and testing v1 settled (section 16).

Revision 2 records three decisions taken with the product owner on 3 Nov 2026 (section 16 has the full log):

1. **Native Frappe meta is the only client runtime.** XLSForm logic is compiled into standard DocType properties (`depends_on`, `mandatory_depends_on`, `read_only_depends_on`, `link_filters`, `default`, …). Desk, Web Forms and the mForm SDK evaluate it with the code they already have. There are no TypeScript or Dart evaluators, no client scripts and no SDK changes. What Frappe cannot express is checked on the server, or rejected at upload with a named error.
2. **Per-form access is standard role permissions on the generated DocType.** The form's designer picks roles in an Access table; there are no User Permission tricks and no permission query hooks.
3. **Frappe v16 only.**

## 1. Overview

**XLSForm for Frappe** (app `xlsform`) lets non-technical client users design data-collection forms in Excel using the XLSForm standard, upload them, and collect data into native Frappe DocTypes — on Desk, on the web, and offline on mobile through mForm. It is a standard Frappe app, AGPL-3.0, intended for the Frappe Cloud Marketplace.

**Problem.** NGO, CSR, government and cooperative clients need forms they can build and change themselves, as in ODK or KoboToolbox. Today every new form on Frappe needs a developer to create a DocType. Their M&E teams already write XLSForms, but nothing in the Frappe ecosystem can read one.

**Goals (v1)**

1. A client user uploads an `.xlsx` XLSForm and gets a working form, without developer help, in under 5 minutes.
2. Every authoring mistake is reported with the sheet, row, column, a plain-language reason and a suggested fix — never a Python traceback.
3. Submissions land in real Frappe DocTypes, so reports, permissions, workflows, the REST API and Insights work unchanged.
4. Skip logic, required and read-only rules behave identically on Desk, web and mForm offline, because all three read the same DocType meta. Constraints and calculations are enforced identically on the server for every channel.
5. Published form versions are immutable; every submission records the version it was collected on.

**Non-goals (v1)**

- Full ODK parity. v1 supports a documented subset (section 2); anything else is rejected at upload with a clear message, never silently ignored.
- Any client-side runtime of our own (JavaScript bindings, Dart evaluators, SDK patches).
- A drag-and-drop builder, XForm XML export, ODK Collect/Enketo compatibility, analytics dashboards.

**Users**

| Role | What they do |
| --- | --- |
| Form Designer (`XLSForm Designer`) | Client M&E or programme staff. Uploads XLSForms, previews, publishes, retires forms, and decides which roles may collect or review each form. Never gets DocType, Customize Form, script or user-management rights. |
| Collector / Reviewer | Any existing role the designer grants on a form (for example "Field Officer"). No app-specific roles are shipped for them. |
| System Manager | Installs the app, sets limits in XLSForm Settings, assigns roles to users. |

## 2. v1 scope and compatibility matrix

Every XLSForm feature falls in exactly one of three tiers. This matrix is the validator's allow-list and is published as `docs/compatibility.md`.

| Tier | Meaning |
| --- | --- |
| **Live** | Compiled into DocType meta. Desk, Web Forms and mForm apply it while the user fills the form, offline included. The server re-checks it on save. |
| **Server** | Frappe meta has no place for it. The server's `validate` hook enforces it on every save from every channel. On mForm offline, a failure appears when the record syncs. |
| **Rejected** | Upload fails with a named error (section 7). |

**Question types**

| XLSForm type | Tier | Frappe field | Notes |
| --- | --- | --- | --- |
| text | Live | Small Text | No 140-char limit, off-page storage. `max_height` 4.5rem (one-line look) unless appearance is `multiline` |
| integer / decimal | Live | Int / Float | A blank number is stored as 0 after save (Frappe behaviour, see 6.3) |
| range | Live + Server | Int or Float | `start`/`end`/`step` checked on the server |
| select_one | Live | Link → generated choice DocType | Shows the choice label (`show_title_field_in_link`); stores the choice name |
| select_multiple | Live | Table MultiSelect → generated pick table | Exported as space-separated names, as ODK stores them |
| select_one_from_file / select_multiple_from_file | Live | as above | CSV with `name`,`label` columns attached to the upload |
| rank, loop (`begin loop over`), osm, select_one_external | Rejected | | |
| note | Live | HTML | Display only, no column |
| acknowledge | Live | Check | `required` on an acknowledge is enforced by the server (Frappe cannot make a Check mandatory) |
| date / time / dateTime | Live | Date / Time / Datetime | |
| geopoint / geotrace / geoshape | Live | Geolocation | GeoJSON. Not on Web Forms (Frappe v16 Web Form fields have no Geolocation): `W-WEB-FIELD` |
| image | Live | Attach Image | |
| audio / video / file | Live | Attach | |
| barcode | Live | Data | Typed on all channels in v1 |
| calculate | Server | Small Text, read-only | Recomputed on every save; hidden when it has no label |
| hidden | Live | Small Text, hidden | |
| start / end / today / username | Server | Datetime / Datetime / Date / Data, read-only, hidden | Filled by the server: start and today on insert, end on every save, username = session user |
| deviceid, phonenumber, email, audit, simserial, subscriberid | — | none | Warning `W-META-IGNORED`; no column |
| begin_group / end_group | Live | Section Break (Tab Break when > 3 top-level groups) | |
| begin_repeat / end_repeat | Live | Table → child DocType | One level only |
| repeat_count | Server | | Row count must equal the expression |
| nested repeats, trigger, background-audio, xml-external, csv-external | Rejected | | |

**Survey sheet columns**

| Column | Tier | Notes |
| --- | --- | --- |
| type, name, label, hint | Live | `label::<lang>` and `hint::<lang>` become Translation records |
| required | Live | `yes` → `reqd`; an expression → `mandatory_depends_on` |
| required_message | Server | Used in the server message |
| relevant | Live | `depends_on`; ANDed with enclosing groups. Non-relevant values are cleared on save (Server) |
| read_only | Live | `yes` → `read_only`; expression → `read_only_depends_on` |
| constraint, constraint_message | Server | |
| calculation | Server | When a Live expression refers to a calculate, the calculation is inlined if it is itself Live-expressible; otherwise `E-CALC-NOT-LIVE` |
| default | Live | Literals; `today()` → `Today`, `now()` → `now`. Other expressions: `E-DEFAULT-DYNAMIC` |
| choice_filter | Live (Desk, mForm) | `link_filters`. Only `column = ${question}` / `column = 'literal'` joined by `and`; anything else `E-FILTER-UNSUPPORTED`. Web Forms have no `link_filters` (Frappe v16), so on the web all choices are offered and the server rejects invalid ones (`W-WEB-FILTER`) |
| appearance | — | `minimal`, `field-list`, `multiline`, `horizontal`, `horizontal-compact`, `likert`, `quick`, `numbers`, `no-calendar`, `signature` accepted with no effect; others `W-APPEARANCE` |
| parameters | Live/Server | `start`, `end`, `step` (range). Others `W-PARAMETER` |
| repeat_count | Server | |
| media::*, guidance_hint, body::* | — | `W-COL-IGNORED` |
| trigger, bind::*, instance::* | Rejected | `E-COL-UNSUPPORTED` |

**Choices sheet**: `list_name`, `name`, `label`, `label::<lang>`, and any extra columns used by `choice_filter`. Choice names must be unique within a list and may not contain spaces or `< > % " # * ? \ /` (each choice becomes a record).

**pyxform compatibility**: every type spelling pyxform 4.5 accepts (112, e.g. `phone number`, `select one from <list>`, `begin looped group`), any letter case in sheet names and headers, `label:English` (single colon), a workbook whose only sheet is the survey, an empty choices sheet, and notes without a name. Extra sheets are ignored; one named like a known sheet (`stettings`) gets `W-SHEET-UNKNOWN`; an `entities` sheet with rows is `E-SHEET-UNSUPPORTED`.

**Settings sheet**: `form_title`, `form_id` (a value that isn't a valid Frappe-safe ID, such as `Flat test`, is normalised to `flat_test` with `W-FORM-ID`), `version`, `default_language`. `instance_name` becomes the DocType's `autoname` when it is a `concat()` of question references and literals (`W-INSTANCE-NAME` otherwise). `public_key` (encryption) is rejected. `submission_url`, `style`, `allow_choice_duplicates` are ignored with `W-SETTING-IGNORED`.

**Expression functions**

All v1 functions are evaluated on the server. Only the Live subset can appear in `relevant`, `required`, `read_only` and `choice_filter`, because it must compile into the JavaScript that both Frappe Desk and the mForm SDK interpreter (`frappe-mobile-sdk/lib/src/utils/js_expression.dart`) evaluate.

| Group | Server (all) | Live subset |
| --- | --- | --- |
| Logic | `if`, `and`, `or`, `not`, `true`, `false`, `coalesce`, `boolean` | all |
| Comparison & arithmetic | `= != < <= > >= + - * div mod`, unary `-` | all |
| Choices | `selected`, `count-selected`, `selected-at`, `jr:choice-name` | `selected`, `count-selected` |
| Text | `concat`, `substr`, `string-length`, `contains`, `starts-with`, `ends-with`, `normalize-space`, `regex`, `string` | `concat`, `string-length`, `contains`, `starts-with`, `ends-with`, `string` |
| Numbers | `int`, `number`, `round`, `abs`, `pow`, `floor`, `ceiling`, `min`, `max` | `int`, `number` |
| Dates | `today`, `now`, `date`, `decimal-date-time`, `format-date`, `format-date-time` | none |
| Repeats | `count`, `sum`, `position(..)` | `count` |
| Other | `once`, `uuid` | none |

Rejected everywhere: `pulldata`, `indexed-repeat`, `instance()`, `search()`, entities, `last-saved`, `area`, `distance`, `digest`, `randomize`, `jr:itext`.

## 3. Architecture and data flow

```text
 Excel ──upload──▶ Reader ─▶ Validator (5 stages) ─▶ XLSForm Version (report, annotated xlsx)
                                     │ valid + publish
                                     ▼
                     compile(parsed, previous_meta) ─▶ plan ─▶ apply(plan)   [background job, site lock]
                                     │
           ┌─────────────────────────┼──────────────────────────────┐
           ▼                         ▼                              ▼
  Generated DocTypes        Choice DocTypes + records      Translation, Web Form,
  (parent, repeats,         (one per choice list)          Mobile Configuration entry
   pick tables)
           │
  Desk · Web Form · mForm SDK  ──all read the same DocType meta──▶  save ──▶ server validate hook
                                                                          (Python evaluator, every channel)
```

There is one expression parser (Python). Its AST feeds two consumers: the Python evaluator on the server and the JavaScript emitter that writes Live expressions into DocType meta.

## 4. DocType specifications

The app ships four DocTypes in module **XLSForm**: XLSForm, XLSForm Access (child), XLSForm Version and XLSForm Settings. Data DocTypes are generated per form in module **XLSForm Data** (4.5).

**What is deliberately not a DocType**

| Need | Handled by |
| --- | --- |
| Per-form access | Role permissions on the generated DocTypes, written from the XLSForm Access table |
| Original name ↔ fieldname map, expressions, layout | `compiled_meta` JSON on the version |
| Media and CSV files | File attachments on the XLSForm Version |
| Audit | `track_changes` and the Version log |
| Test answers in preview | `test_results` JSON on the version |

### 4.1 XLSForm — master, `autoname: field:form_id`, `track_changes`

| Fieldname | Fieldtype | Notes |
| --- | --- | --- |
| form_id | Data, reqd, unique | `^[a-z][a-z0-9_]{2,40}$`, from settings |
| title | Data, reqd | From `form_title`; editable |
| status | Select: Draft, Published, Retired | Read-only |
| current_version | Link XLSForm Version | Read-only |
| data_doctype | Link DocType | Read-only, frozen at first publish |
| default_language | Link Language | |
| allow_web | Check, default 1 | Generate a Web Form |
| allow_mobile | Check, default 1 | Register with `mobile_control` when installed |
| retired_on | Datetime | Read-only |
| access | Table XLSForm Access | Who may use the form's data |

Saving the form re-applies `access` to the generated DocTypes immediately (no re-publish).

### 4.2 XLSForm Access — child table

| Fieldname | Fieldtype | Notes |
| --- | --- | --- |
| role | Link Role, reqd | `Guest`, `All`, `Administrator` are rejected |
| can_read, can_write, can_create, can_delete, can_export, can_report, can_print | Check | |
| only_own | Check | Frappe `if_owner`: the role sees only records its users created |

Default on a new form: no rows. System Manager always has full access; the XLSForm Designer role always gets read.

### 4.3 XLSForm Version — submittable, `autoname: format:{form}-v{version}`

| Fieldname | Fieldtype | Notes |
| --- | --- | --- |
| form | Link XLSForm, reqd | Created on first upload of a new `form_id` |
| version | Data, reqd | From settings; must sort above the published version |
| source_file | Attach, reqd | `.xlsx` |
| state | Select: Uploaded, Invalid, Valid, Published, Superseded | Read-only |
| error_count, warning_count | Int | Read-only |
| warnings_accepted | Check | Required to publish when warnings exist |
| validation_report | JSON | Issue objects (section 11) |
| report_html, change_html | Long Text | Rendered report and change summary (HTML fields have no column, so the HTML is stored here) |
| report_view, change_view | HTML | Display of the two fields above |
| change_summary | JSON | vs the published version |
| publish_status | Select: queued, compiling, migrating, done, failed | Read-only |
| publish_error | Small Text | Read-only |
| parsed_json | JSON | Normalised form tree |
| compiled_meta | JSON | See below |
| test_results | JSON | Last 20 preview test submissions |
| source_hash | Data | SHA-256; a duplicate of a published file is rejected |

Uploading a workbook whose `version` matches an unpublished (draft) version of the same form replaces that draft. Published versions are immutable; cancel is disallowed.

`compiled_meta` shape:

```json
{"metaVersion": 2, "astVersion": 1, "form_id": "hh_survey", "version": "2026110301",
 "doctypes": {"parent": "XF Household Survey",
              "repeats": {"/member": "XF hh_survey member"},
              "lists": {"yes_no": "XF hh_survey yes_no"},
              "picks": {"services": "XF hh_survey services pick"}},
 "fields": [{"path": "/member/age", "name": "age", "fieldname": "age", "doctype": "XF hh_survey member",
             "type": "integer", "fieldtype": "Int", "introduced_in": "2026100101", "retired_in": null}],
 "expressions": {"/member/age": {"relevant": {"op": "..."}, "constraint": {}, "required": {}}},
 "calc_order": ["/total_members"],
 "labels": {"/member/age": {"English": "Age", "Hindi": "उम्र"}},
 "messages": {"/member/age": {"constraint": {"English": "Age must be 0–120"}}}}
```

### 4.4 XLSForm Settings — single

| Fieldname | Fieldtype | Default |
| --- | --- | --- |
| max_upload_mb | Int | 5 |
| max_questions | Int | 400 |
| max_choices_per_list | Int | 20000 |
| max_expression_length | Int | 2000 |
| row_budget_bytes | Int | 60000 |
| doctype_prefix | Data | XF |
| designers_can_publish | Check | 1 |
| default_language | Link Language | en |
| allow_data_removal_on_uninstall | Check | 0 |

### 4.5 Generated DocTypes (`custom = 1`, never shipped as app files)

Parents, repeats and pick tables are in module **XLSForm Data**; choice lists are in module **XLSForm Choices**, so the computed module sidebar (which lists at most 15 DocTypes) shows forms only. Every generated DocType's description carries `[xlsform:<form>]`, which identifies its form: `apply()` refuses a DocType of another form, and a failed publish's leftovers (DDL can't be rolled back) are reused by the next publish of the same form.

| Kind | Name | Notes |
| --- | --- | --- |
| Parent | `{prefix} {Form Title}` | Reserved fields below; `track_changes` |
| Repeat | `{prefix} {form_id} {repeat}` | `istable` |
| Choice list | `{prefix} {form_id} {list_name}` | Fields `choice_name` (unique, autoname), `label` (title field), `xf_order`, `xf_retired`, plus one Data column per extra choices-sheet column used by a filter. `show_title_field_in_link = 1`, `translated_doctype = 1`, sorted by `xf_order` |
| Pick table | `{prefix} {form_id} {list_name} pick` | `istable`, one Link field `choice` |

Reserved fields on every parent (questions may not use the `xf_` prefix):

| Fieldname | Fieldtype | Notes |
| --- | --- | --- |
| xf_form | Link XLSForm | Set on insert |
| xf_version | Link XLSForm Version | Version the record was collected on; defaults to the current version |
| xf_channel | Select: Desk, Web, mForm, API | Best-effort, set on insert |

Offline idempotency uses `mobile_uuid`, which `mobile_control` adds (unique) to every DocType in Mobile Configuration.

**Permissions**

| Role | XLSForm | XLSForm Version | Settings | Generated data and choice lists |
| --- | --- | --- | --- | --- |
| System Manager | All | All | All | All |
| XLSForm Designer | Create, read, write | Create, read, write, submit | Read | Read |
| Roles in a form's Access table | — | — | — | As ticked (choice lists and child tables: read for every listed role) |

## 5. Compiler rules

`compile(parsed, previous_meta, settings) -> plan` is pure (no database access) and fully unit-tested. `apply(plan)` performs inserts and schema changes in a background job holding a site-level lock, and only touches DocTypes in module `XLSForm Data` whose name starts with `doctype_prefix`.

**Naming**

- Parent `{prefix} {Form Title}`; repeats, lists and pick tables `{prefix} {form_id} {name}`. Trimmed to 61 characters (MariaDB's 64 minus `tab`), de-duplicated with ` 2`, ` 3`. A title that is not plain ASCII letters, digits, spaces, `-` and `_` uses `form_id` instead.
- DocType names are frozen at first publish.

**Fieldname sanitisation** (deterministic; stored in `compiled_meta.fields`)

1. Lower-case; `-` and `.` → `_`; strip anything outside `[a-z0-9_]`.
2. Prefix `f_` if it starts with a digit.
3. Suffix `_q` for Frappe standard columns, MariaDB reserved words, JavaScript reserved words, and the `xf_` prefix.
4. Longer than 58 characters: truncate to 51 and add `_` plus 6 hex characters of a hash of the path.
5. Collisions: `_2`, `_3`.

Exports always use the original XLSForm names.

**Layout**: top-level groups → Section Breaks (Tab Breaks when there are more than 3); nested groups → Section Breaks labelled "Outer › Inner"; group `relevant` is ANDed into every descendant's `depends_on` and set on its section.

**Selects**: `select_one` → Link with `length` = longest choice name rounded up to 20 (min 20), `link_filters` = the compiled `choice_filter` plus `xf_retired = 0`. `select_multiple` → Table MultiSelect to the list's pick table. A choice list is loaded into its DocType as records; removed choices get `xf_retired = 1` and stay valid for old records.

**Live expressions**: `depends_on`, `mandatory_depends_on`, `read_only_depends_on` are `eval:` strings produced by the emitter (section 6). User text appears in them only as JSON-escaped string literals.

**Row-size budget** (fails with `E-ROW-BUDGET` over `row_budget_bytes`)

| Fieldtype | Bytes |
| --- | --- |
| Small Text, Text, Attach, Attach Image, Geolocation, HTML | 12 |
| Data, Link | 4 × length + 2 (Data 140) |
| Int, Check | 4 |
| Float | 9 |
| Date / Time / Datetime | 3 / 6 / 8 |
| Table, Table MultiSelect, Section/Tab/Column Break | 0 |
| Standard and reserved columns | 3,500 fixed |

**Schema evolution**

| Change | Action |
| --- | --- |
| Question added | New column |
| Question removed | Column kept, field hidden, not required, read-only; `retired_in` set |
| Label, hint, relevance, constraint, choices changed | Metadata and choice records only |
| Longer choice names | Link `length` widened (never narrowed) |
| Type or choice list changed | New column `<name>_v<n>`; old one retired; data never cast in place (`W-TYPE-CHANGE`) |
| Name changed / moved in or out of a repeat | Remove + add (`W-RENAME`, `W-MOVE-REPEAT`) |

The compiler never drops a column or a table.

## 6. Expression engine

### 6.1 Pipeline

1. Tokenise and parse every `relevant`, `constraint`, `calculation`, `required`, `read_only`, `choice_filter`, `repeat_count` and `default` cell into an AST.
2. Resolve `${name}` to absolute paths (`E-REF-UNKNOWN` with an edit-distance ≤ 2 suggestion).
3. Check functions against the v1 allow-list and their arity.
4. Build the dependency graph; cycles fail with `E-CALC-CYCLE`.
5. For Live columns, run the emitter; anything outside the Live subset fails with `E-EXPR-NOT-LIVE` naming the function.

AST shape (`astVersion: 1`):

```json
{"op": "and", "args": [
  {"op": "=", "args": [{"ref": "/consent"}, {"lit": "yes"}]},
  {"fn": "selected", "args": [{"ref": "/services"}, {"lit": "health"}]}]}
```

`{"ref": ".", "self": true}` is the current answer in a constraint.

### 6.2 JavaScript emitter (Live subset)

The target grammar is the intersection of JavaScript and the SDK interpreter: literals, `doc.x`, `parent.x`, `! && || ?:`, `=== !== < <= > >= + - * / %`, `.length`, `.includes`, `.startsWith`, `.endsWith`, `.some`, `.map`, `.join`, `.split`, arrow functions, and the Frappe globals `cint`, `flt`, `cstr`.

| XLSForm | Emitted (inside a row, own-row refs use `doc`, outer refs use `parent`) |
| --- | --- |
| `${a} = 'x'` | `(cstr(doc.a) === "x")` |
| `${n} > 5` | `(cstr(doc.n) !== "" && flt(doc.n) > 5)` |
| `${n} != 5` | `(cstr(doc.n) === "" \|\| flt(doc.n) !== 5)` |
| `selected(${m}, 'x')` | `(doc.m \|\| []).some(r => r.choice === "x")` |
| `count-selected(${m})` | `(doc.m \|\| []).length` |
| `count(${rep})` | `(doc.rep \|\| []).length` |
| `if(c, a, b)` | `(c ? a : b)` |
| `int(x)` / `number(x)` | `cint(x)` / `flt(x)` |

### 6.3 Semantics (each is a conformance fixture group)

- An unanswered question is `""`. Frappe stores a blank Int/Float as 0 after save; the conformance suite covers both states and the docs say so.
- If either side of a comparison is numeric, both are converted to numbers; `""` becomes NaN. Every comparison with NaN is false except `!=`, which is true (IEEE 754, as JavaRosa).
- Booleans: `""` and `0` are false; any other string is true.
- Dates are days since 1970-01-01 (server only).
- `select_multiple` values are space-separated strings on the server and pick rows in meta.
- `int()` truncates toward zero; `round(x, n)` rounds half away from zero.
- `sum()` and `count()` over an empty repeat return 0.
- Values of non-relevant questions are `""` in other expressions and cleared on save.

### 6.4 Conformance

`xlsform/tests/fixtures/expr/*.json` holds cases of `{expr, context, expected}`. Each case is checked three ways: the Python evaluator; the emitted JavaScript run in Node (as Desk runs it); and, for Live cases, the emitted JavaScript run through the SDK's own `js_expression.dart` at a pinned commit. Target 300+ cases.

## 7. Validation and user-friendly errors

Rules for every issue: located (sheet, Excel row, column, cell), plain language, one suggested fix, a stable code with a docs page, all issues in a stage collected, translatable, and a severity (Error blocks publish; Warning needs "I understand"; Info is advice).

| Stage | Checks | Stops later stages? |
| --- | --- | --- |
| 1. File | `.xlsx` only, size, readable, not password-protected, required sheets | Yes |
| 2. Structure | Columns, names, duplicates, `begin_`/`end_` matching | Yes |
| 3. Meaning | Types, choice lists, expressions, references, cycles, Live-ability, settings | No |
| 4. Frappe limits | Question count, row budget, name length | No |
| 5. Version diff | Renames, removals, type changes vs the published version | No (warnings) |

pyxform is **not** run on sites: every pyxform release pins `xlrd==2.0.1`, which conflicts with Frappe v16's `xlrd~=2.0.2`, so it can't be an app dependency (`E-PYXFORM` is dropped). Instead CI runs `scripts/pyxform_crosscheck.py`: every workbook in `xlsform/tests/fixtures/corpus` is checked by our validator and by pyxform (own virtualenv); a disagreement that isn't a documented v1 limitation, or reviewed in `corpus/expected.json` with a reason, fails the build.

Designers see issues on the XLSForm Version form (summary bar + table grouped by sheet), as a downloadable **annotated copy of their workbook** (cells filled red/amber with the message as a comment), and in the API.

**Issue catalogue** — the source of truth is `xlsform/core/issues.py` (62 codes). `scripts/gen_error_docs.py` writes `docs/errors/<CODE>.md` and the public page `/xlsform-docs/errors#CODE` (each `docs_url`), with a worked example taken from that code's failing test fixture. Codes added during the build: `E-FILE-UNREADABLE`, `E-GROUP-EXTRA-END`, `E-REPEAT-EMPTY`, `E-EXPR-TOO-LONG`, `E-FILTER-COLUMN`, `E-PARAMETER-INVALID`, `E-VERSION-PUBLISHED`, `W-REMOVED`, `W-WEB-FIELD`, `W-FORM-ID`, `W-SHEET-UNKNOWN`, `E-SHEET-UNSUPPORTED`.

| Code | Sev | Example message |
| --- | --- | --- |
| E-FILE-TYPE | E | This file is not an Excel workbook (.xlsx). |
| E-FILE-SIZE | E | The file is 9 MB; the limit is 5 MB. |
| E-FILE-PROTECTED | E | The workbook is password-protected, so it can't be read. |
| E-FILE-UNREADABLE | E | The workbook can't be opened; it may be damaged. |
| E-SHEET-MISSING | E | The workbook has no "survey" sheet. |
| E-COL-MISSING | E | The survey sheet has no "type" column. |
| W-COL-UNKNOWN | W | Column "lable" isn't recognised and will be ignored. Did you mean "label"? |
| W-COL-IGNORED | W | Column "media::image" is not supported yet and will be ignored. |
| E-COL-UNSUPPORTED | E | Column "trigger" isn't supported. |
| E-NAME-MISSING | E | Row 14 has a question type but no name. |
| E-NAME-INVALID | E | "Household size" can't be used as a name. Use `household_size`. |
| E-NAME-DUPLICATE | E | The name `age` is used in rows 9 and 31. |
| E-TYPE-UNKNOWN | E | "select one" isn't a question type. Did you mean `select_one`? |
| E-TYPE-UNSUPPORTED | E | "rank" questions aren't supported yet. |
| W-META-IGNORED | W | "deviceid" can't be collected and will be ignored. |
| E-LIST-MISSING | E | Row 18 uses choice list "districts", which isn't on the choices sheet. |
| E-LIST-EMPTY | E | Choice list "districts" has no choices. |
| E-CHOICE-DUPLICATE | E | Choice "yes" appears twice in list "yes_no". |
| E-CHOICE-NAME | E | Choice name "not sure" contains a space. |
| E-LIST-TOO-LARGE | E | Choice list "villages" has 25,000 choices; the limit is 20,000. |
| E-FILE-CSV-MISSING | E | Row 7 uses villages.csv, which wasn't uploaded with the form. |
| E-GROUP-UNCLOSED | E | The group started in row 12 is never closed. |
| E-GROUP-MISMATCH | E | Row 40 closes a repeat, but the open block is a group. |
| E-GROUP-EXTRA-END | E | Row 40 closes a group that was never opened. |
| E-REPEAT-NESTED | E | Repeat `member` is inside repeat `household`. |
| E-REPEAT-EMPTY | E | Repeat `member` has no questions. |
| E-REF-UNKNOWN | E | `${hh_sise}` isn't a question. Did you mean `${hh_size}`? |
| E-REF-SELF | E | The constraint refers to its own name; use `.`. |
| E-REF-REPEAT | E | `${member_age}` is used outside repeat `member` without `count()`/`sum()`. |
| E-EXPR-SYNTAX | E | The formula can't be read: a bracket is never closed. |
| E-EXPR-QUOTE | E | The formula uses curly quotes (‘ ’). |
| E-EXPR-TOO-LONG | E | The formula is 2,400 characters; the limit is 2,000. |
| E-FN-UNSUPPORTED | E | `pulldata()` isn't supported. |
| E-FN-ARGS | E | `selected()` needs 2 values but got 1. |
| E-EXPR-NOT-LIVE | E | `today()` can't be used in "relevant": forms check that while being filled, offline too. |
| E-CALC-NOT-LIVE | E | "relevant" uses `age_years`, whose calculation can only run on the server. |
| E-CALC-CYCLE | E | These calculations depend on each other in a loop: `total` → `share` → `total`. |
| E-FILTER-UNSUPPORTED | E | This choice_filter can't be applied; use `column = ${question}` joined by `and`. |
| E-FILTER-COLUMN | E | choice_filter uses column "district", which isn't on the choices sheet. |
| E-FILTER-MULTI | E | choice_filter on select_multiple isn't supported yet. |
| W-WEB-FILTER | W | On the web form all choices are listed; invalid combinations are rejected on save. |
| E-DEFAULT-DYNAMIC | E | Default `${x}` can't be used; defaults must be fixed values, today() or now(). |
| W-APPEARANCE | W | Appearance "quick-compact" isn't supported and will be ignored. |
| W-PARAMETER | W | Parameter "max-pixels" isn't supported and will be ignored. |
| E-SETTING-INVALID | E | form_id "Household Survey" isn't valid. Use `household_survey`. |
| E-SETTING-ENCRYPTED | E | Encrypted forms (public_key) aren't supported. |
| W-SETTING-IGNORED | W | Setting "submission_url" is ignored. |
| W-INSTANCE-NAME | W | instance_name can only combine questions and fixed text; it will be ignored. |
| E-VERSION-ORDER | E | Version "2024-01" is not newer than the published "2025-03". |
| E-VERSION-PUBLISHED | E | Version "2025-03" is already published; set a new version. |
| E-LIMIT-QUESTIONS | E | The form has 512 questions; the limit is 400. |
| E-ROW-BUDGET | E | Too many short-answer questions outside repeats to store in one record. |
| W-RENAME | W | `village` was removed and `village_name` added; answers won't move. |
| W-MOVE-REPEAT | W | `age` moved into repeat `member`; answers won't move. |
| W-TYPE-CHANGE | W | `income` changed from integer to text; earlier answers stay in the old column. |
| I-NO-LABEL | I | Row 19 has no label. |

**Preview and test answers**: before publishing, the designer opens **Preview**, a Desk dialog built from the compiled fields that applies the same Live expressions as the real form. **Check answers** sends the answers to the server, which runs the full server validation and returns the issues. The last 20 results are kept in `test_results`. Nothing is written to data tables.

## 8. Runtime

- **Desk**: nothing beyond the generated meta and Translation records.
- **Web**: when `allow_web` is on, a login-required Web Form named `xf-<form-id>` at `/xf/<form-id>` is generated from the parent DocType with the same `depends_on` / `mandatory_depends_on` / `read_only_depends_on`. Web Form fields accept fewer types than DocFields: Table MultiSelect becomes a grid of the same pick rows (rules still work), Tab Breaks become Page Breaks, Geolocation is left out (`W-WEB-FIELD`); short text boxes come from generated `custom_css`.
- **mForm**: when `allow_mobile` is on and `mobile_control` is installed, the parent DocType is added to Mobile Configuration; `mobile_control` provisions `mobile_uuid` and the SDK renders the form from meta. Choice DocTypes sync as Link targets.
- **Server** (`doc_events["*"]["validate"]`, returns at once unless the DocType has `xf_form`), using the record's `xf_version` meta: reject inserts on a retired form; fill metadata questions; recompute calculations in order; clear non-relevant values; enforce required (including acknowledge); enforce constraints, ranges, `repeat_count` and choice filters. All failures are reported in one `ValidationError`, by question label.

## 9. Versioning lifecycle

Uploaded → Valid / Invalid (validation runs in a background job for files over 1 MB) → Published (submit) → Superseded (when a newer version is published). Re-uploading the same version string replaces an unpublished draft. Retiring a form blocks new records on every channel; publishing a new version re-opens it. A blank `version` is proposed as `YYYYMMDDNN` and written into the annotated workbook.

## 10. Permissions and security

- **Privilege boundary**: `apply(plan)` and access sync run with `ignore_permissions` only after checking the caller is a Designer or System Manager, and only on DocTypes in `XLSForm Data` with the configured prefix.
- **Per-form access**: role permission rows written from the Access table into the generated DocTypes' own permission table (they are custom DocTypes, so no Custom DocPerm is involved). A role with no row sees nothing. No `has_permission` or `permission_query_conditions` hooks.
- **Untrusted spreadsheets**: openpyxl with formulas as cached values, macros/external links ignored; labels and notes HTML-escaped; only escaped string literals from user text enter `eval:` strings.
- **No code from users**: expressions are parsed into an AST; never `eval`, `exec`, `safe_eval` or `render_template`.
- **Limits** (Settings): upload size, questions, choices per list, expression length; parsing in a background job with a 120 s timeout.
- **Multi-tenancy**: each site is a tenant; nothing is shared across sites.
- **Uninstall**: generated DocTypes and data are removed only when `allow_data_removal_on_uninstall` is ticked; otherwise uninstall stops with a message.

## 11. API surface

Whitelisted, permission-checked, rate-limited methods under `xlsform.api.forms` and `xlsform.api.data`. Generated DocTypes also work through standard REST.

| Method | Endpoint | Who | Purpose |
| --- | --- | --- | --- |
| POST | `forms.upload` | Designer | xlsx (+ CSVs) → `{form, version, state, issues[]}` |
| GET | `forms.validation_report` | Designer | JSON, or `format=xlsx` for the annotated workbook |
| GET | `forms.preview` | Designer | Preview field definitions |
| POST | `forms.check_answers` | Designer | Server validation of test answers |
| POST | `forms.publish` | Designer (or SM) | Publish a Valid version → job id |
| GET | `forms.publish_status` | Designer | `queued`, `compiling`, `migrating`, `done`, `failed` |
| POST | `forms.retire` | Designer | Close to new submissions |
| GET | `forms.template` | Logged in | Starter XLSForm |
| GET | `data.export` | Reader of the data | CSV/XLSX with original names, a sheet per repeat |

Issue object:

```json
{"code": "E-REF-UNKNOWN", "severity": "error", "sheet": "survey", "row": 25,
 "column": "relevant", "cell": "H25",
 "message": "survey!H25 refers to ${hh_sise}, which isn't a question in this form.",
 "suggestion": "Did you mean ${hh_size}?", "docs_url": "/xlsform-docs/errors#E-REF-UNKNOWN"}
```

## 12. Frappe standards and Marketplace readiness

- Frappe **v16 only** (`frappe~=16.0`, Python 3.14); branches `version-16` and `develop`. Desk routes are `/desk/...`; the workspace is **Excel Forms** (`/desk/excel-forms`) because a workspace named XLSForm would take the XLSForm list's route.
- Extends only through hooks: `doc_events`, `fixtures`, `after_install`, `before_uninstall`, `add_to_apps_screen`.
- Role fixture and standard Workspace; all strings in `_()` / `__()` (`N_()` markers in the framework-free core); Hindi in `xlsform/locale/hi.po` (all 343 strings; `scripts/generate_pot.py` regenerates `main.pot`).
- Dependencies: none beyond Frappe (openpyxl ships with it); no system packages, no Java, no Node at runtime. pyxform is used in CI only (section 7).
- Lint: ruff, ruff-format, prettier, Frappe semgrep rules in CI.
- Marketplace items needing people (logo, screenshots, video, privacy URL, listing, `frappe/marketplace` PR) are tracked in `docs/RELEASE.md`.

## 13. Testing strategy

| Layer | Tool | Proves |
| --- | --- | --- |
| Validator fixtures | pytest (no site) | Each code fires on a minimal bad workbook with the right location; good workbooks give zero issues |
| Expression conformance | pytest + Node + Dart (SDK interpreter) | Python, JavaScript and the SDK agree on every case |
| Compiler unit | pytest (no site) | Type mapping, sanitising, layout, selects, budget, diffs (snapshots) |
| Server integration | `bench run-tests --app xlsform` | Upload → publish → DocTypes → valid/invalid records → republish → old records still valid → access per role → retire |
| Desk/Web smoke | Playwright (`ui-tests/`, every PR and nightly) | Designer: upload a broken form, see the cell, download the highlighted workbook, upload the fix, preview with live skip logic, check answers, publish. Collector: skip logic and save on Desk; skip logic on the Web Form |
| Corpus | `scripts/pyxform_crosscheck.py` (nightly) | Agreement with pyxform on real workbooks |

Security tests: `<script>` in labels is inert; quotes and backslashes in literals can't break out of `eval:` strings; a non-designer gets 403 on upload/publish; `apply()` refuses a DocType outside `XLSForm Data`.

## 14. Milestones

1. Scaffold, CI, DocTypes, roles. 2. Reader + stages 1–2. 3. Expression parser, Python evaluator, JS emitter, conformance. 4. Stages 3–4 + pyxform. 5. Compiler + apply. 6. Versioning + stage 5. 7. Server runtime, Web Form, translations, mobile registration. 8. Designer UX: report, annotated workbook, preview, check answers, template, docs. 9. APIs + export. 10. Release docs.

## 15. Open items needing people

- Names (decided 3 Nov 2026): app `xlsform`, repo `dhwani-ris/frappe-xlsform`, listing title "XLSForm for Frappe". Confirm the app name in the Frappe Cloud publisher dashboard.
- 50 anonymised client forms for the regression corpus.
- Moderated test with 3 client M&E staff.
- Logo, screenshots, demo video, privacy policy URL, listing submission.

## 16. Decision log

| Date | Decision | Why |
| --- | --- | --- |
| 2026-11-03 | Native DocType meta is the only client runtime; constraints and calculations are server-checked | The SDK already evaluates Frappe meta offline; one source of truth; no SDK fork |
| 2026-11-03 | All selects are Links to generated choice DocTypes (Table MultiSelect for select_multiple) | Shows labels while storing names; supports cascades (`link_filters`), large lists and translations natively |
| 2026-11-03 | Per-form access = role permissions written from the XLSForm Access table | User Permissions leak when a user has none; role permissions deny by default and `mobile_control` already uses them |
| 2026-11-03 | No Collector/Reviewer roles shipped | Designers grant existing org roles |
| 2026-11-03 | `mobile_uuid` replaces `xf_instance_id`; mobile API endpoints dropped | `mobile_control` already provides idempotent offline sync |
| 2026-11-03 | Preview answers are checked server-side and kept as JSON | No data DocType exists before the first publish |
| 2026-11-03 | Same version string replaces an unpublished draft | Designers fix and re-upload without inventing versions |
| 2026-11-03 | Frappe v16 only | All Dhwani sites run v16 |
| 2026-11-03 | pyxform is CI-only; `E-PYXFORM` dropped | Every pyxform release pins xlrd==2.0.1; Frappe v16 needs ~=2.0.2 |
| 2026-11-03 | Date comparisons and date arithmetic are server-only | `flt("2026-01-05")` is 2026 in Frappe; ODK compares dates as dates |
| 2026-11-03 | Text-to-number guard `flt(x) == cstr(x)` in emitted rules | `flt("abc")` is 0 in Frappe but NaN in ODK; found by the generated comparison matrix |
| 2026-11-03 | Choice lists in their own module | The computed module sidebar lists at most 15 DocTypes |
| 2026-11-03 | Accept every pyxform spelling; normalise form_id with a warning | Real workbooks (pyxform's own examples) use them |
