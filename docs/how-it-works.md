# How it works

## From workbook to DocType

```text
 Excel ──upload──▶ Reader ─▶ Validator (5 stages) ─▶ XLSForm Version (report, marked workbook)
                                    │ valid + publish
                                    ▼
                    compile_form(...) ─▶ plan ─▶ apply(plan)   [background job, site lock]
                                    │
          ┌─────────────────────────┼──────────────────────────────┐
          ▼                         ▼                              ▼
 Generated DocTypes        Choice DocTypes + records      Translation, Web Form,
 (parent, repeats,         (one per choice list)          Mobile Configuration entry
  pick tables)
          │
 Desk · Web Form · mForm  ──all read the same DocType meta──▶  save ──▶ server validate hook
```

1. The designer uploads a workbook. The app stores it as an **XLSForm Version** of the form named in the `settings` sheet.
2. The validator checks the workbook in five stages: file, structure, meaning, Frappe limits and the difference from the published version. A workbook over 1 MB is checked in a background job.
3. The designer reads the report, previews the form and publishes.
4. A background job compiles the workbook to a plan and applies it. The version is submitted only after the schema changes succeed.
5. Collectors fill the form. On every save the server runs the rules that DocType meta cannot express.

## Rules: live or on save

Formulas are parsed once, in Python. The parse tree goes to two places:

| Where | What it does | Applies to |
|---|---|---|
| JavaScript emitter | Writes `depends_on`, `mandatory_depends_on`, `read_only_depends_on` and `link_filters` | `relevant`, `required`, `read_only`, `choice_filter` that Frappe can evaluate in the form |
| Python evaluator | Runs in the `validate` hook | Constraints, calculations, ranges, `repeat_count`, and every live rule again |

A formula that Frappe meta cannot express is checked on save only, or is rejected at upload with a named code. It is never ignored. [Compatibility](compatibility.md) lists each feature and its tier.

Every live rule is tested three ways: the Python evaluator, Frappe's own JavaScript and the mForm SDK interpreter must give the same answer (1,187 cases).

## Generated DocTypes

Generated DocTypes are custom (`custom = 1`). They are not shipped as app files.

| Kind | Name | Module |
|---|---|---|
| Parent | `XF {Form Title}` | XLSForm Data |
| Repeat | `XF {form_id} {repeat}` (child table) | XLSForm Data |
| Choice list | `XF {form_id} {list_name}` | XLSForm Choices |
| Pick table | `XF {form_id} {list_name} pick` (child table for `select_multiple`) | XLSForm Data |

`XF` is the prefix in XLSForm Settings. Every parent has three extra fields: `xf_form`, `xf_version` (the version the record was collected on) and `xf_channel` (Desk, Web, mForm or API).

The DocTypes of a form are recorded in its `generated_doctypes` field before any schema change. `apply()` changes only those DocTypes. MariaDB cannot roll back DDL, so a failed publish can leave DocTypes behind. The next publish of the same form uses them again.

## Versions

| State | Meaning |
|---|---|
| Uploaded | Waiting for the background check |
| Invalid | Has errors. Cannot be published |
| Valid | No errors. Can be previewed and published |
| Published | Submitted. The generated DocTypes match this version |
| Superseded | A newer version is published. Records collected on it stay valid |

When a question changes type, the new version gets a new column. The old column is kept and hidden with its answers. Removed questions are hidden, not dropped. A rename is a new question: earlier answers stay in the old column.

Upload the same version string again to replace a draft. A published version cannot be replaced, cancelled or deleted.

## Extension points

| Extension point | What it does |
|---|---|
| `doc_events["*"].validate` | Runs the server rules on records of generated parents. For every other DocType it returns after one cached meta check |
| `after_install` | Makes the two generated modules and fills the default settings |
| `after_migrate` | Makes sure the two generated modules exist. Never changes settings |
| `before_uninstall` | Stops uninstall while form data exists, unless the settings allow removal. Then deletes the generated DocTypes and drops their tables |
| `scheduler_events` (daily) | Deletes export files older than one day |
| `fixtures` | The XLSForm Designer role |
| `add_to_apps_screen` | The XLSForm tile for designers and System Managers |
| Web Form (core) | One login-required Web Form per form, at `/xf/<form-id>` |
| Mobile Configuration (`mobile_control`) | Adds the parent DocType so mForm syncs it. `mobile_control` adds `mobile_uuid` for offline idempotency |
| Translation (core) | Labels from `label::Hindi (hi)` columns |
| Workspace (core) | **Form Data** lists every published form. It is rebuilt on publish, retire and rename |

## Performance

- The save hook costs one cached meta lookup for DocTypes that are not generated by this app.
- A published version's rules are cached in Redis for good, because a published version does not change.
- Publishing runs on the `long` queue, one publish at a time per site (a Redis lock shared by every worker).
- Before the first schema change, Frappe's DocType field and permission checks run on the whole plan inside a savepoint. A problem stops the publish while the site is still unchanged.
