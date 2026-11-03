# Contributing to XLSForm for Frappe

This document tells you how to set up a development environment, run the checks and send a change.

## Code of conduct

Participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By contributing, you agree to uphold it.

## What to contribute

- Bug fixes with regression tests
- Documentation improvements (`README.md` and the `docs` folder)
- Support for more XLSForm features (see [Compatibility](docs/compatibility.md))
- Test coverage, conformance cases and corpus workbooks

For large or API-breaking changes, open an issue first to agree on direction. Read [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and the [developer guide](docs/developer-guide.md) before you start. If the code and the specification disagree, raise it in the issue.

## Development setup

Follow [Development setup](docs/developer-guide.md#development-setup) in the developer guide.

## Quality checks before you push

```bash
pre-commit run --all-files
../../env/bin/python -m pytest xlsform/tests/unit xlsform/tests/conformance
bench --site <site> run-tests --app xlsform
```

A change to formula behavior also needs `scripts/conformance-dart.sh`. See [Rules for changes](docs/developer-guide.md#rules-for-changes).

## Pull requests

- Use lowercase conventional commit subjects, for example `fix: reject eval prefix in choice filters`.
- Keep one topic per pull request.
- Update the specification in the same pull request when behavior changes.
