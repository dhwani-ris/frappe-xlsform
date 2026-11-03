### XLSForm for Frappe

Build data-collection forms in Excel and collect the answers into normal Frappe DocTypes. Collectors use Desk, the web or mForm offline.

- Upload an `.xlsx` XLSForm, the standard of ODK, KoboToolbox and SurveyCTO. No developer is needed to make or change a form.
- Every problem is listed with its sheet, row and cell, and a suggested fix. You can download your workbook with the problems marked in the cells.
- Skip logic, required and read-only rules become standard `depends_on` properties. Desk, Web Forms and mForm apply them with no extra client code, offline too.
- Constraints, calculations and repeat counts are checked on the server on every save, from every channel.
- Published versions do not change. A new version adds columns and never drops or converts one, so earlier records stay valid.
- Each form's data is a real DocType: reports, workflows, the REST API and Insights work on it.
- Uses only official Frappe extension points. No fork, no monkey patching. Runs on Frappe Cloud.

### Installation

```bash
bench get-app https://github.com/dhwani-ris/frappe-xlsform --branch develop
bench --site <site> install-app xlsform
```

Then give your form designers the **XLSForm Designer** role and open **Excel Forms** on the desk. Complete the checklist in [Setup](docs/setup.md#installation).

> **Frappe v16 only.** The app uses v16 Desk routes and field properties. It does not install on v15.

> **Uninstall keeps your data.** Uninstall stops while generated DocTypes exist, unless a System Manager ticks **Allow uninstall to delete form data** in XLSForm Settings. See [Setup](docs/setup.md#uninstall).

> **MariaDB only.** PostgreSQL is not supported.

### Documentation

| Document | Contents |
|---|---|
| [How it works](docs/how-it-works.md) | Upload to publish pipeline, generated DocTypes, extension points, versions |
| [Setup](docs/setup.md) | Installation checklist, roles, settings, Web Form and mForm channels |
| [Designer guide](docs/designer-guide.md) | Upload, fix, preview, publish, retire and export a form |
| [Compatibility](docs/compatibility.md) | Supported XLSForm features and how each one behaves |
| [Issue codes](docs/errors/README.md) | Every upload error and warning, with an example and a fix |
| [Developer guide](docs/developer-guide.md) | API, dev container, tests, conformance, code layout |
| [Security](docs/security.md) | Permission model, untrusted workbooks, known limits |
| [Requirements](docs/REQUIREMENTS.md) | The full specification and the decision log |

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

### License

AGPL-3.0. The pyxform example workbooks under `xlsform/tests/fixtures/corpus/pyxform` are BSD 2-Clause (see the license file there).

<p align="center">
  <img src="xlsform/public/images/logo.svg" alt="XLSForm for Frappe logo" width="120" />
</p>
