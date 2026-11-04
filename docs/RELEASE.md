# Release checklist — v1.0.0

REQUIREMENTS.md section 12. Items marked **(people)** can't be done by code and are owned by the product team.

## Code gates (automated, all green on `develop` as of 3 Nov 2026)

- [x] Frappe v16 app scaffolded with `bench new-app`; hooks only (no monkey-patching)
- [x] CI: `ci.yml` (core unit + conformance with the 95% compiler coverage gate; server tests on v16; clean uninstall)
- [x] CI: `linters.yml` (pre-commit: ruff, ruff-format, prettier, eslint; Frappe semgrep rules)
- [x] Every emitted rule checked against the mForm SDK expression subset (`core/expr/profile.py`)
- [x] CI: `corpus.yml` (pyxform cross-check on the real-world corpus)
- [x] Settings DocType (XLSForm Settings); role and workspace shipped
- [x] All user-facing strings translatable; Hindi `xlsform/locale/hi.po` complete (386/386). The 47 strings added on 4 Nov 2026 need a review by a native speaker
- [x] v16 apps screen entry (`add_to_apps_screen`, lower-case name), workspace, logo
- [x] No system packages, Java or runtime Node; no Python dependencies beyond Frappe
- [x] README, compatibility page, issue-code pages (`docs/errors`, `/xlsform-docs/errors`)

## Marketplace listing

| Requirement | Status | Owner |
| --- | --- | --- |
| Public GitHub repo owned by the publisher | `dhwani-ris/frappe-xlsform` (app name `xlsform`); push `develop`, then branch `version-16` | done when pushed |
| Unique app name | `xlsform`: free on PyPI and in the `frappe/marketplace` registry (checked 3 Nov 2026); confirm in the Frappe Cloud publisher dashboard | **(people)** |
| Supports current stable Frappe | v16 | done |
| CI passing (linters + server tests) | Workflows in `.github/workflows` — first run happens on the first push | **(people)**: push |
| Logo | `xlsform/public/images/logo.svg` (square, no text). Export a 512×512 PNG for the listing | **(people)**: approve |
| Short description | "Build data-collection forms in Excel and collect into DocTypes" (62 chars) | done |
| Long description | `docs/marketplace.md` | done (review) |
| Screenshots | Take the five screens listed in `docs/marketplace.md` on a demo site | **(people)** |
| Support URL / Privacy Policy URL | GitHub Issues; Dhwani privacy page URL | **(people)** |
| Demo video (3–4 min) | Script in `docs/marketplace.md` | **(people)** |
| Category | Utilities (or Data Collection) | **(people)** |
| Cloud v2 registry | PR adding the app to `apps.json` in `frappe/marketplace` | **(people)** |

## Before tagging

- [ ] **(people)** Moderated test with 3 client M&E staff: each fixes a broken sample form using only the app's messages (milestone 8 done-criterion)
- [ ] **(people)** Add 50 anonymised client workbooks to `xlsform/tests/fixtures/corpus/clients/` and get `corpus.yml` green
- [ ] Create the `version-16` branch from `develop`; tag `v1.0.0`
