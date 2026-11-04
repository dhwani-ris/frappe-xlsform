#!/usr/bin/env python3
"""Set __version__ in xlsform/__init__.py. Run by semantic-release: update-version.py <version>."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INIT_FILE = ROOT / "xlsform" / "__init__.py"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
ASSIGNMENT_RE = re.compile(r"""__version__\s*=\s*["'][^"']*["']""")


def update_version(new_version: str) -> None:
	if not VERSION_RE.match(new_version):
		sys.exit(f"Not a version number: {new_version!r}")
	content = INIT_FILE.read_text(encoding="utf-8")
	if not ASSIGNMENT_RE.search(content):
		sys.exit(f"No __version__ found in {INIT_FILE.relative_to(ROOT)}")
	INIT_FILE.write_text(ASSIGNMENT_RE.sub(f'__version__ = "{new_version}"', content, count=1), encoding="utf-8")
	print(f"Updated {INIT_FILE.relative_to(ROOT)} to {new_version}")


if __name__ == "__main__":
	if len(sys.argv) != 2:
		sys.exit("Usage: update-version.py <new_version>")
	update_version(sys.argv[1])
