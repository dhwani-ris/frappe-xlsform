"""Stage 1: read an uploaded workbook safely into plain rows (REQUIREMENTS.md sections 7, 10).

Workbooks are untrusted. openpyxl is used with ``data_only=True`` (cached values, never
formulas), and macros, external links and embedded objects are never touched. Each
cell keeps its Excel location so every later issue can point at it.
"""

import datetime
import io
import zipfile
from dataclasses import dataclass, field

from xlsform.core.issues import Issue, issue

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MACRO_CONTENT_TYPE = b"macroEnabled"


@dataclass
class Cell:
	value: str
	col: int  # 1-based column index


@dataclass
class Row:
	number: int  # Excel row number
	cells: dict[str, Cell]  # normalised header -> cell

	def get(self, key: str) -> str:
		cell = self.cells.get(key)
		return cell.value if cell else ""

	def col(self, key: str) -> int | None:
		cell = self.cells.get(key)
		return cell.col if cell else None


@dataclass
class Sheet:
	name: str  # name as written in the workbook
	headers: list[tuple[int, str, str]]  # (col index, raw header, normalised header)
	rows: list[Row] = field(default_factory=list)

	def has_column(self, key: str) -> bool:
		return any(h[2] == key for h in self.headers)

	def column_index(self, key: str) -> int | None:
		for col, _raw, norm in self.headers:
			if norm == key:
				return col
		return None


@dataclass
class Workbook:
	sheets: dict[str, Sheet]  # keyed by lower-case sheet name

	def sheet(self, name: str) -> Sheet | None:
		return self.sheets.get(name)


def read_workbook(content: bytes, filename: str, max_mb: int | float) -> tuple[Workbook | None, list[Issue]]:
	"""Return the workbook, or ``None`` with stage 1 issues when it can't be read."""
	issues: list[Issue] = []
	size_mb = len(content) / (1024 * 1024)
	lower = (filename or "").lower()

	if content.startswith(OLE_MAGIC):
		# Either a legacy .xls or an encrypted (password-protected) .xlsx container.
		if b"E\x00n\x00c\x00r\x00y\x00p\x00t\x00e\x00d\x00P\x00a\x00c\x00k\x00a\x00g\x00e" in content:
			return None, [issue("E-FILE-PROTECTED")]
		return None, [issue("E-FILE-TYPE")]
	if not lower.endswith(".xlsx") or not zipfile.is_zipfile(io.BytesIO(content)):
		return None, [issue("E-FILE-TYPE")]
	try:
		with zipfile.ZipFile(io.BytesIO(content)) as zf:
			names = set(zf.namelist())
			content_types = zf.read("[Content_Types].xml") if "[Content_Types].xml" in names else b""
	except zipfile.BadZipFile:
		return None, [issue("E-FILE-UNREADABLE")]
	if "xl/vbaProject.bin" in names or MACRO_CONTENT_TYPE in content_types:
		return None, [issue("E-FILE-TYPE")]
	if size_mb > max_mb:
		return None, [issue("E-FILE-SIZE", size_mb=_round_mb(size_mb), limit_mb=max_mb)]

	try:
		import openpyxl

		wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
	except Exception:
		return None, [issue("E-FILE-UNREADABLE")]

	sheets: dict[str, Sheet] = {}
	try:
		for ws in wb.worksheets:
			key = ws.title.strip().lower()
			if key in sheets:
				continue
			sheets[key] = _read_sheet(ws)
	except Exception:
		return None, [issue("E-FILE-UNREADABLE")]
	finally:
		wb.close()
	return Workbook(sheets), issues


def _round_mb(size_mb: float) -> float | int:
	rounded = round(size_mb, 1)
	return int(rounded) if rounded == int(rounded) else rounded


def _read_sheet(ws) -> Sheet:
	headers: list[tuple[int, str, str]] = []
	sheet = Sheet(name=ws.title, headers=headers)
	header_seen = False
	for row_number, values in enumerate(ws.iter_rows(values_only=True), start=1):
		if not header_seen:
			if all(_to_text(v) == "" for v in values):
				continue
			for col, value in enumerate(values, start=1):
				raw = _to_text(value)
				if raw:
					headers.append((col, raw, normalise_header(raw)))
			header_seen = True
			continue
		cells: dict[str, Cell] = {}
		for col, _raw, norm in headers:
			if col - 1 < len(values):
				text = _to_text(values[col - 1])
				if text != "" and norm not in cells:
					cells[norm] = Cell(text, col)
		if cells:
			sheet.rows.append(Row(row_number, cells))
	return sheet


def _to_text(value) -> str:
	if value is None:
		return ""
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, float):
		return str(int(value)) if value.is_integer() else repr(value)
	if isinstance(value, datetime.datetime):
		if value.time() == datetime.time():
			return value.date().isoformat()
		return value.isoformat()
	if isinstance(value, datetime.date | datetime.time):
		return value.isoformat()
	return str(value).strip()


# Header aliases accepted by pyxform, mapped to the canonical name.
HEADER_ALIASES = {
	"list name": "list_name",
	"listname": "list_name",
	"constraint message": "constraint_message",
	"required message": "required_message",
	"choice filter": "choice_filter",
	"repeat count": "repeat_count",
	"read only": "read_only",
	"readonly": "read_only",
	"mandatory": "required",
	"caption": "label",
	"value": "name",
	"calculate": "calculation",
	"guidance hint": "guidance_hint",
	"form title": "form_title",
	"form id": "form_id",
	"default language": "default_language",
	"instance name": "instance_name",
	"image": "media::image",
	"audio": "media::audio",
	"video": "media::video",
	"big-image": "media::big-image",
}


SINGLE_COLON_BASES = {
	"label",
	"hint",
	"constraint_message",
	"constraint message",
	"required_message",
	"required message",
	"guidance_hint",
	"media",
	"image",
	"audio",
	"video",
	"bind",
	"body",
	"instance",
}


def normalise_header(raw: str) -> str:
	"""Lower-case the column name but keep the language part of ``label::Hindi (hi)``."""
	text = " ".join(raw.strip().split())
	if "::" not in text and ":" in text:
		# old pyxform spelling: label:English, hint:Hindi, bind:jr:constraintMsg
		base, _, rest = text.partition(":")
		if base.strip().lower() in SINGLE_COLON_BASES:
			text = f"{base}::{rest}"
	if "::" in text:
		base, _, rest = text.partition("::")
		base = base.strip().lower()
		base = HEADER_ALIASES.get(base, base)
		rest = rest.strip()
		if base in ("media", "bind", "body", "instance"):
			rest = rest.lower()
		return f"{base}::{rest}"
	lowered = text.lower()
	return HEADER_ALIASES.get(lowered, lowered)
