"""The parsed form: a tree of groups, repeats and questions plus choice lists and settings.

This is the normalised representation every later stage works on (``parsed_json`` on the
XLSForm Version is :meth:`Form.as_dict`). It never holds Frappe-specific names; those are
assigned by the compiler.
"""

from dataclasses import dataclass, field

from xlsform.core.reader import Row

GROUP = "group"
REPEAT = "repeat"
QUESTION = "question"

# Canonical XLSForm question types and how v1 treats them (REQUIREMENTS.md section 2).
SUPPORTED_TYPES = {
	"text",
	"integer",
	"decimal",
	"range",
	"select_one",
	"select_multiple",
	"select_one_from_file",
	"select_multiple_from_file",
	"note",
	"acknowledge",
	"date",
	"time",
	"datetime",
	"geopoint",
	"geotrace",
	"geoshape",
	"image",
	"audio",
	"video",
	"file",
	"barcode",
	"calculate",
	"hidden",
	"start",
	"end",
	"today",
	"username",
}
META_IGNORED_TYPES = {"deviceid", "phonenumber", "email", "audit", "simserial", "subscriberid"}
UNSUPPORTED_TYPES = {
	"rank": "",
	"trigger": "",
	"background-audio": "",
	"background_audio": "",
	"xml-external": "",
	"csv-external": "",
	"select_one_external": "",
	"start-geopoint": "",
	"start_geopoint": "",
}
STRUCTURE_TYPES = {"begin_group", "end_group", "begin_repeat", "end_repeat"}
SELECT_TYPES = {"select_one", "select_multiple", "select_one_from_file", "select_multiple_from_file"}
META_TYPES = {"start", "end", "today", "username"}
NO_LABEL_OK = {"calculate", "hidden", "start", "end", "today", "username", *META_IGNORED_TYPES}

# pyxform-compatible spellings, after lower-casing and replacing spaces with underscores.
TYPE_ALIASES = {
	"string": "text",
	"int": "integer",
	"float": "decimal",
	"select_all_that_apply": "select_multiple",
	"select_one_from_file": "select_one_from_file",
	"location": "geopoint",
	"gps": "geopoint",
	"date_time": "datetime",
	"datetime": "datetime",
	"photo": "image",
	"q_picture": "image",
	"q_image": "image",
	"q_audio": "audio",
	"q_video": "video",
	"imei": "deviceid",
	"begin_loop": "begin_repeat",
	"end_loop": "end_repeat",
	"start_time": "start",
	"end_time": "end",
}

ALL_KNOWN_TYPES = SUPPORTED_TYPES | META_IGNORED_TYPES | set(UNSUPPORTED_TYPES) | STRUCTURE_TYPES


@dataclass
class TypeInfo:
	base: str  # canonical type, e.g. select_one
	list_name: str = ""  # select_one <list_name>
	file_name: str = ""  # select_one_from_file <file>
	raw: str = ""


def parse_type(raw: str) -> TypeInfo:
	"""Split ``select_one yes_no`` / ``select one from file x.csv`` into a :class:`TypeInfo`."""
	text = " ".join(raw.strip().split())
	lowered = text.lower()
	for prefix, canonical in (
		("select_one_from_file ", "select_one_from_file"),
		("select one from file ", "select_one_from_file"),
		("select_multiple_from_file ", "select_multiple_from_file"),
		("select multiple from file ", "select_multiple_from_file"),
		("select_one ", "select_one"),
		("select one ", "select_one"),
		("select_multiple ", "select_multiple"),
		("select multiple ", "select_multiple"),
		("select all that apply ", "select_multiple"),
		("rank ", "rank"),
		("select_one_external ", "select_one_external"),
	):
		if lowered.startswith(prefix):
			arg = text[len(prefix) :].strip()
			if canonical.endswith("_from_file"):
				return TypeInfo(canonical, file_name=arg, raw=text)
			if " or_other" in arg:
				arg = arg.replace(" or_other", "").strip()
			return TypeInfo(canonical, list_name=arg, raw=text)
	key = lowered.replace(" ", "_")
	key = TYPE_ALIASES.get(key, key)
	return TypeInfo(key, raw=text)


@dataclass
class Node:
	kind: str  # group / repeat / question
	name: str
	type: TypeInfo
	row: Row | None
	parent: "Node | None" = None
	children: list["Node"] = field(default_factory=list)
	end_row: int | None = None

	@property
	def path(self) -> str:
		if self.parent is None:
			return ""
		return f"{self.parent.path}/{self.name}"

	@property
	def base_type(self) -> str:
		return self.type.base

	def cell(self, key: str) -> str:
		return self.row.get(key) if self.row else ""

	def col(self, key: str) -> int | None:
		return self.row.col(key) if self.row else None

	@property
	def row_number(self) -> int | None:
		return self.row.number if self.row else None

	def localized(self, base: str, default_language: str) -> dict[str, str]:
		"""``{language: text}`` for label / hint / constraint_message / required_message."""
		out: dict[str, str] = {}
		if not self.row:
			return out
		for key, cell in self.row.cells.items():
			if key == base:
				out[default_language] = cell.value
			elif key.startswith(base + "::"):
				out[language_name(key.split("::", 1)[1])] = cell.value
		return out

	@property
	def enclosing_repeat(self) -> "Node | None":
		node = self.parent
		while node is not None:
			if node.kind == REPEAT:
				return node
			node = node.parent
		return None

	def walk(self):
		yield self
		for child in self.children:
			yield from child.walk()

	def as_dict(self, default_language: str) -> dict:
		data = {
			"kind": self.kind,
			"name": self.name,
			"path": self.path,
			"type": self.base_type,
			"row": self.row_number,
		}
		if self.type.list_name:
			data["list_name"] = self.type.list_name
		if self.type.file_name:
			data["file_name"] = self.type.file_name
		if self.row:
			for key in BIND_COLUMNS:
				if self.cell(key):
					data[key] = self.cell(key)
			for base in ("label", "hint", "constraint_message", "required_message"):
				loc = self.localized(base, default_language)
				if loc:
					data[base] = loc
		if self.children:
			data["children"] = [c.as_dict(default_language) for c in self.children]
		return data


BIND_COLUMNS = (
	"relevant",
	"required",
	"constraint",
	"calculation",
	"default",
	"read_only",
	"choice_filter",
	"appearance",
	"repeat_count",
	"parameters",
)


@dataclass
class Choice:
	name: str
	labels: dict[str, str]
	extra: dict[str, str]
	row: Row


@dataclass
class ChoiceList:
	name: str
	choices: list[Choice] = field(default_factory=list)
	row: int = 0  # first row on the choices sheet
	from_file: str = ""


@dataclass
class Form:
	root: Node
	lists: dict[str, ChoiceList]
	settings: dict[str, str]
	settings_cols: dict[str, int]
	default_language: str
	languages: list[str]
	choice_columns: set[str] = field(default_factory=set)

	@property
	def form_id(self) -> str:
		return self.settings.get("form_id", "")

	@property
	def title(self) -> str:
		return self.settings.get("form_title") or self.form_id

	@property
	def version(self) -> str:
		return self.settings.get("version", "")

	def nodes(self):
		for child in self.root.children:
			yield from child.walk()

	def questions(self):
		return [n for n in self.nodes() if n.kind == QUESTION]

	def by_name(self) -> dict[str, Node]:
		return {n.name: n for n in self.nodes()}

	def by_path(self) -> dict[str, Node]:
		return {n.path: n for n in self.nodes()}

	def as_dict(self) -> dict:
		return {
			"form_id": self.form_id,
			"title": self.title,
			"version": self.version,
			"default_language": self.default_language,
			"languages": self.languages,
			"settings": self.settings,
			"children": [c.as_dict(self.default_language) for c in self.root.children],
			"choices": {
				name: [
					{"name": c.name, "label": c.labels, **({"filters": c.extra} if c.extra else {})}
					for c in lst.choices
				]
				for name, lst in self.lists.items()
			},
		}


def language_name(spec: str) -> str:
	"""``Hindi (hi)`` -> ``Hindi (hi)`` normalised; the code is extracted by :func:`language_code`."""
	return " ".join(spec.split())


def language_code(spec: str) -> str | None:
	"""Return ``hi`` from ``Hindi (hi)``; ``None`` when no code is given."""
	spec = spec.strip()
	if spec.endswith(")") and "(" in spec:
		return spec[spec.rindex("(") + 1 : -1].strip() or None
	return None


DEFAULT_LANGUAGE = "default"
