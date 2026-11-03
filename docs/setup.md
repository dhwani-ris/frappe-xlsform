# Setup

## Installation

You can install this app with the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/dhwani-ris/frappe-xlsform --branch develop
bench --site <site> install-app xlsform
```

Then do these steps once per site:

1. Make sure a worker serves the `long` queue. Publishing and the check of large workbooks run there.
2. Give the **XLSForm Designer** role to the people who build forms.
3. Open **XLSForm Settings** and check the limits (see [Settings](#settings)).
4. If collectors use mForm, install [`mobile_control`](https://github.com/dhwani-ris/frappe-mobile-control) before the first publish.
5. Open **Excel Forms** on the desk and download the starter workbook.

## Roles

| Role | Can do |
|---|---|
| System Manager | Everything, including XLSForm Settings |
| XLSForm Designer | Upload, preview, publish and retire forms. Choose which roles use each form's data. Read the data of every form |
| Roles in a form's Access table | What the table allows on that form's data |

The XLSForm Designer role never gets DocType, Customize Form or script permissions.

The app does not ship collector or reviewer roles. Use the roles you already have, for example "Field Officer".

## Who can use a form's data

Each XLSForm has a table called **Who can use the data**. Add one row for each role:

| Column | Gives |
|---|---|
| Read, Create, Edit, Delete, Export, Report, Print | The same Frappe permission on the form's DocType |
| Only their own records | The permission applies only to records the user created |

A role without a row sees nothing, because Frappe denies by default. Choice lists get read access for every listed role. The table writes standard role permissions on the generated DocType. The app has no permission hooks and does not use User Permissions.

You cannot give access to Guest, All or Administrator.

## Settings

**XLSForm Settings** is for System Managers. Designers can read it.

| Setting | Default | Notes |
|---|---|---|
| Largest workbook (MB) | 5 | |
| Most questions per form | 400 | |
| Most choices per list | 20,000 | |
| Longest formula (characters) | 2,000 | |
| Row size budget (bytes) | 60,000 | Must stay under the MariaDB row limit of 65,535 |
| Prefix of generated DocTypes | `XF` | Cannot change after the first publish |
| Default language | `en` | |
| Designers can publish | On | Turn off to let only System Managers publish |
| Allow uninstall to delete form data | Off | See [Uninstall](#uninstall) |

## Channels

| Channel | How to turn it on | Notes |
|---|---|---|
| Desk | Always on | Records open from the **Form Data** workspace or the **Open records** button on the form |
| Web | Tick **Allow Web Form** on the XLSForm | Login required. Route `/xf/<form-id>`. Geolocation questions are left out |
| mForm | Tick **Allow mForm** and install `mobile_control` | The parent DocType is added to Mobile Configuration |

A channel change takes effect when you publish the next version.

## Uninstall

Uninstall deletes every generated DocType. To protect the data, `before_uninstall` stops while generated DocTypes exist.

Frappe does not drop the database table of a deleted DocType. The `tabXF …` tables and their records stay in the database after uninstall.

To uninstall:

1. Export the data you want to keep.
2. Tick **Allow uninstall to delete form data** in XLSForm Settings.
3. Run `bench --site <site> uninstall-app xlsform`.
4. Run `bench --site <site> trim-database --dry-run` and check the list of tables.
5. Run `bench --site <site> trim-database` to remove the tables of deleted DocTypes. It takes a backup first.
