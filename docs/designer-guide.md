# Designer guide

This guide is for users with the **XLSForm Designer** role.

## Make a form

1. Open **Excel Forms** on the desk.
2. Download the starter workbook, or use your own XLSForm.
3. Set `form_id`, `form_title` and `version` in the `settings` sheet. Leave `version` empty to get a version such as `2026110301`.
4. Click **Upload** and select the `.xlsx` file. If the form uses `select_one_from_file`, add the CSV files too.

The app makes the XLSForm from `form_id` and stores the file as a new version.

## Fix problems

The version page lists every problem by sheet. Each row shows the cell, the problem, a suggested fix and a code. The code links to its page in [Issue codes](errors/README.md).

| Severity | Effect |
|---|---|
| Error | Blocks publish |
| Warning | Tick **I understand the warnings** before you publish |
| Advice | No effect |

To fix the workbook:

1. Click **Download highlighted workbook**. Problem cells are red or amber, with the message as a cell comment.
2. Fix the cells in Excel.
3. Click **Upload a corrected workbook**. The same version string replaces the draft.

## Preview and test

1. Click **Preview**. Skip logic works while you type.
2. Fill in test answers.
3. Click **Check answers**. The server runs constraints, calculations and required checks. Nothing is saved to the data tables.

The last 20 test runs are kept on the version.

## Publish

1. Click **Publish**.
2. Read the list of changes to the data table.
3. Confirm.

Publishing runs in the background. The page shows its progress. If publishing fails, the page shows the reason and the form stays on its earlier version.

If **Designers can publish** is off in the settings, ask a System Manager to publish.

## Change a published form

Click **Upload new version** on the XLSForm and select a workbook with a higher `version`. The report lists the changes against the published version:

| Change | What happens to earlier answers |
|---|---|
| New question | New column |
| Removed question | Kept, hidden |
| Renamed question | Kept in the old column. The new name starts empty |
| Question moved into or out of a repeat | Kept in the old place |
| Type changed | Kept in the old column. The new type gets a new column |

Records keep the version they were collected on. mForm can sync a record collected on an older version, and the server checks it with that version's rules.

## Retire a form

Click **Retire form** on the XLSForm. New records are refused on every channel. Existing records do not change. The Web Form is unpublished and mForm stops syncing the form. Publish a new version to open the form again.

## Export data

Click **Export Excel** on the XLSForm. The export uses your workbook's column names, not Frappe field names:

- One sheet for each repeat, linked to the parent by `PARENT_KEY`.
- `select_multiple` answers are choice names separated by spaces.
- Columns of retired questions are marked "(retired *version*)".

Users need the Export permission on the form's data. Designers too: add the XLSForm Designer role to the form's Access table to read or export its data.

Up to 5,000 records, the file downloads at once. A larger export runs in the background, and a link appears when it is ready. Export files are deleted after one day.
