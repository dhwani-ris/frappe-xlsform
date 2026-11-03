"""Deterministic DocType names and fieldnames (REQUIREMENTS.md section 5).

Fieldnames are chosen once, at the first publish that introduces a question, and stored in
``compiled_meta.fields``; later versions reuse them, so a column never moves.
"""

import hashlib
import re

MAX_FIELDNAME = 58
TRUNCATE_TO = 51
MAX_DOCTYPE = 61

FRAPPE_COLUMNS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
	"_seen",
	"doctype",
	"amended_from",
	"naming_series",
	"mobile_uuid",
	"server_name",
	"title",
	"status",
	"flags",
	"meta",
}

JS_RESERVED = {
	"break",
	"case",
	"catch",
	"class",
	"const",
	"continue",
	"debugger",
	"default",
	"delete",
	"do",
	"else",
	"enum",
	"export",
	"extends",
	"false",
	"finally",
	"for",
	"function",
	"if",
	"import",
	"in",
	"instanceof",
	"new",
	"null",
	"return",
	"super",
	"switch",
	"this",
	"throw",
	"true",
	"try",
	"typeof",
	"var",
	"void",
	"while",
	"with",
	"yield",
	"let",
	"static",
	"await",
	"implements",
	"package",
	"protected",
	"interface",
	"private",
	"public",
	"undefined",
	"nan",
	"infinity",
	"arguments",
	"eval",
	"constructor",
	"prototype",
	"__proto__",
}

MARIADB_RESERVED = set(
	"""
accessible add all alter analyze and as asc asensitive before between bigint binary blob both by call
cascade case change char character check collate column condition constraint continue convert create
cross current_date current_role current_time current_timestamp current_user cursor database databases
day_hour day_microsecond day_minute day_second dec decimal declare default delayed delete delete_domain_id
desc describe deterministic distinct distinctrow div do_domain_ids double drop dual each else elseif
enclosed escaped except exists exit explain false fetch float float4 float8 for force foreign from
fulltext general group having high_priority hour_microsecond hour_minute hour_second if ignore
ignore_domain_ids ignore_server_ids in index infile inner inout insensitive insert int int1 int2 int3
int4 int8 integer intersect interval into is iterate join key keys kill leading leave left like limit
linear lines load localtime localtimestamp lock long longblob longtext loop low_priority
master_heartbeat_period master_ssl_verify_server_cert match maxvalue mediumblob mediumint mediumtext
middleint minute_microsecond minute_second mod modifies natural not no_write_to_binlog null numeric
offset on optimize option optionally or order out outer outfile over page_checksum parse_vcol_expr
partition position precision primary procedure purge range read reads read_write real recursive
ref_system_id references regexp release rename repeat replace require resignal restrict return returning
revoke right rlike rows row_number schema schemas second_microsecond select sensitive separator set
show signal slow smallint spatial specific sql sqlexception sqlstate sqlwarning sql_big_result
sql_calc_found_rows sql_small_result ssl starting stats_auto_recalc stats_persistent stats_sample_pages
straight_join table terminated then tinyblob tinyint tinytext to trailing trigger true undo union unique
unlock unsigned update usage use using utc_date utc_time utc_timestamp values varbinary varchar
varcharacter varying when where while window with write xor year_month zerofill
""".split()
)

RESERVED = FRAPPE_COLUMNS | JS_RESERVED | MARIADB_RESERVED


def path_hash(path: str) -> str:
	return hashlib.sha1(path.encode()).hexdigest()[:6]


def sanitize(name: str, path: str, taken: set[str], reserved_extra: set[str] = frozenset()) -> str:
	"""Turn an XLSForm name into a unique Frappe fieldname (rules 1–5 of section 5)."""
	s = name.lower().replace("-", "_").replace(".", "_")
	s = re.sub(r"[^a-z0-9_]", "", s)
	if not s:
		s = "q"
	if s[0].isdigit():
		s = "f_" + s
	if s in RESERVED or s in reserved_extra or s.startswith("xf_") or s.startswith("_"):
		s = (s.lstrip("_") or "q") + "_q"
	if len(s) > MAX_FIELDNAME:
		s = s[:TRUNCATE_TO] + "_" + path_hash(path)
	base = s
	n = 2
	while s in taken:
		suffix = f"_{n}"
		s = base[: MAX_FIELDNAME - len(suffix)] + suffix
		n += 1
	taken.add(s)
	return s


SAFE_TITLE = re.compile(r"^[A-Za-z0-9 _\-]+$")


def doctype_name(prefix: str, label: str, taken: set[str]) -> str:
	"""``XF Household Survey``; trimmed to 61 characters and de-duplicated with `` 2``."""
	label = " ".join(label.split())
	base = f"{prefix} {label}".strip()[:MAX_DOCTYPE].rstrip()
	name = base
	n = 2
	lowered = {t.lower() for t in taken}
	while name.lower() in lowered:
		suffix = f" {n}"
		name = base[: MAX_DOCTYPE - len(suffix)].rstrip() + suffix
		n += 1
	taken.add(name)
	return name


def parent_label(title: str, form_id: str) -> str:
	title = " ".join((title or "").split())
	return title if title and SAFE_TITLE.match(title) else form_id


def child_label(form_id: str, name: str) -> str:
	return f"{form_id} {re.sub(r'[^A-Za-z0-9_\-]', '_', name)}"
