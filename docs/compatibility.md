# XLSForm compatibility (v1)

This is the public promise: what XLSForm for Frappe supports, how each feature behaves, and what is rejected. Anything not listed as supported is reported at upload with a named code ([issue codes](errors/README.md)) — never silently ignored.

Three tiers:

| Tier | Meaning |
| --- | --- |
| **Live** | Becomes standard DocType rules. Desk, Web Forms and mForm apply it while the form is being filled, offline included. Checked again on save. |
| **On save** | Frappe has no place for it in the form itself, so the server checks it on every save from every channel. On mForm offline it is checked when the record syncs. |
| **Not yet** | Rejected at upload with a named code. |

## Question types

| Type | Tier | Stored as |
| --- | --- | --- |
| text (also: string, phone number) | Live | Small Text (shown as a short box unless `appearance: multiline`) |
| integer, decimal (also: int, percentage, number of days in …) | Live | Int / Float — a blank number is stored as 0 after saving |
| range | Live + on save | Int or Float; `start`, `end`, `step` checked on save |
| select_one, select_multiple (also: select one from, select all that apply, select1 …) | Live | Link to a choice list / multi-select table; stores choice names, shows labels |
| select_one_from_file, select_multiple_from_file | Live | as above; upload the CSV (`name`, `label` columns) with the workbook |
| note | Live | Display only |
| acknowledge | Live | Check; "required" checked on save |
| date, time, dateTime | Live | Date / Time / Datetime |
| geopoint, geotrace, geoshape | Live | Geolocation (not shown on the web form; Desk and mForm only) |
| image, audio, video, file | Live | Attach Image / Attach |
| barcode | Live | Data (typed) |
| calculate | On save | Read-only; recomputed on every save |
| hidden | Live | Hidden field |
| start, end, today, username | On save | Filled by the server, hidden |
| begin_group / end_group | Live | Section (tabs when there are more than 3 top-level groups); web form pages |
| begin_repeat / end_repeat | Live | Child table; `repeat_count` checked on save |
| deviceid, phonenumber, email, audit, simserial, subscriberid | — | Ignored with a warning (no column) |
| rank, loops, osm, select_one_external, nested repeats, trigger, background-audio/geopoint, csv-external, xml-external, entities | Not yet | |

## Columns

| Column | Tier | Notes |
| --- | --- | --- |
| type, name, label, hint, `label::Language (code)` | Live | Languages become Frappe translations; `label:English` also accepted |
| relevant | Live | Answers to questions that aren't relevant are cleared on save, as in ODK |
| required | Live | `yes` or a formula; `required_message` used on save |
| read_only | Live | `yes` or a formula |
| constraint, constraint_message | On save | `.` means "this answer" |
| calculation | On save | A Live rule may use a calculate whose formula is itself Live; it is inlined |
| default | Live | Fixed values, `today()`, `now()` |
| choice_filter | Live (Desk, mForm) | `column = ${question}` joined by `and`. On the web form all choices are listed and wrong combinations are refused on save |
| appearance | — | Common appearances accepted (they don't change Frappe's layout); unknown ones warned |
| parameters | Live / on save | `start`, `end`, `step` for range; others warned |
| media::*, guidance_hint, body::* | — | Ignored with a warning |
| trigger, bind::*, instance::* | Not yet | |

Settings sheet: `form_title`, `form_id` (made Frappe-safe automatically, with a warning), `version`, `default_language`, `instance_name` (`concat()` of questions and text). `public_key` (encryption) is rejected; `submission_url`, `style` and similar are ignored with a warning.

## Formulas

Every function below works on save. Only the **Live** ones can be used in `relevant`, `required`, `read_only` and `choice_filter`, because those are evaluated while the form is being filled — in Frappe Desk and in the mForm app.

| Group | Functions | Live |
| --- | --- | --- |
| Logic | `if`, `and`, `or`, `not`, `true`, `false`, `coalesce`, `boolean` | all |
| Comparison & arithmetic | `= != < <= > >= + - * div mod`, unary `-` | all (but not on dates) |
| Choices | `selected`, `count-selected`, `selected-at`, `jr:choice-name` | `selected`, `count-selected` |
| Text | `concat`, `substr`, `string-length`, `contains`, `starts-with`, `ends-with`, `normalize-space`, `regex`, `string` | `concat`, `string-length`, `contains`, `starts-with`, `ends-with`, `string` |
| Numbers | `int`, `number`, `round`, `abs`, `pow`, `floor`, `ceiling`, `min`, `max` | `int`, `number` |
| Dates | `today`, `now`, `date`, `decimal-date-time`, `format-date`, `format-date-time` | — |
| Repeats | `count`, `sum`, `position(..)` | `count` |
| Other | `once`, `uuid` | — |

Not yet: `pulldata`, `indexed-repeat`, `instance()`, `search()`, `last-saved`, `area`, `distance`, `digest`, `randomize`, `jr:itext`.

## Behaviour that differs from ODK

- A blank integer or decimal is stored as **0** once saved (Frappe stores numbers as numbers). While the form is open it is blank, as in ODK.
- Formulas compare text answers to numbers the ODK way, except where Frappe's number format uses `.` as a thousands separator (for example `#.###,##`): there, text like `2.5` in a text question is not read as a number.
- Choice names must be unique within a list and can't contain spaces or `< > % " # * ? \ /`, because each choice becomes a record.
- Constraints and calculations are checked on save; on mForm offline that is when the record syncs.

## Checked against

Python (the server), Frappe's own JavaScript, and the mForm SDK's interpreter agree on 1,187 formula cases (`xlsform/tests/conformance`). Every pyxform example workbook is cross-checked against pyxform itself (`scripts/pyxform_crosscheck.py`) on each pull request that changes the validator.
