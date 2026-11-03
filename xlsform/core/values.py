"""Turn a Frappe document into the answers an XLSForm formula sees.

Used by the server validate hook and by the conformance suite, so both evaluate exactly the
same values. ``meta`` is a version's ``compiled_meta``; ``doc`` is ``Document.as_dict()``
(child tables as lists of dicts).
"""

import datetime
import json

from xlsform.core.expr.evaluate import Context

NUMERIC = {"integer", "decimal", "range"}
MULTI = {"select_multiple", "select_multiple_from_file"}


def answer(qtype: str, value):
	"""The ODK value of one stored answer."""
	if value is None:
		return ""
	if qtype in NUMERIC:
		if value == "":
			return ""
		try:
			return float(value)
		except (TypeError, ValueError):
			return str(value)
	if qtype in MULTI:
		if isinstance(value, list):
			return " ".join(str(_row_get(r, "choice")) for r in value if _row_get(r, "choice"))
		return str(value)
	if qtype == "acknowledge":
		return "OK" if value in (1, "1", True) else ""
	if qtype in ("geopoint", "geotrace", "geoshape"):
		return _odk_geo(value)
	if isinstance(value, datetime.datetime):
		return value.isoformat()
	if isinstance(value, datetime.date | datetime.time):
		return value.isoformat()
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value)


def _row_get(row, key):
	return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _odk_geo(value) -> str:
	"""GeoJSON (Frappe Geolocation) -> ODK ``lat lon alt acc`` (points joined by ``;``)."""
	try:
		data = json.loads(value) if isinstance(value, str) else value
	except (TypeError, ValueError):
		return str(value)
	coords = []
	for feature in (data or {}).get("features", []) if isinstance(data, dict) else []:
		geometry = feature.get("geometry") or {}
		c = geometry.get("coordinates")
		if geometry.get("type") == "Point" and c:
			coords.append([c])
		elif geometry.get("type") == "LineString" and c:
			coords.append(c)
		elif geometry.get("type") == "Polygon" and c:
			coords.append(c[0])
	points = [p for group in coords for p in group]
	return ";".join(f"{p[1]} {p[0]} {p[2] if len(p) > 2 else 0} 0" for p in points)


class MetaIndex:
	"""Lookups over ``compiled_meta`` used by every evaluation of one version."""

	def __init__(self, meta: dict):
		self.meta = meta
		self.fields = [f for f in meta.get("fields", []) if not f.get("retired_in")]
		self.by_path = {f["path"]: f for f in self.fields}
		self.repeats = set(meta.get("doctypes", {}).get("repeats", {}))
		self.repeat_of = {}
		for f in self.fields:
			for r in self.repeats:
				if f["path"].startswith(r + "/"):
					self.repeat_of[f["path"]] = r
		labels = meta.get("choice_labels", {})
		lang = meta.get("default_language")
		self.choice_labels = {}
		for f in self.fields:
			if f.get("list") in labels:
				self.choice_labels[f["path"]] = {
					name: (lbl.get(lang) or next(iter(lbl.values()), name))
					for name, lbl in labels[f["list"]].items()
				}

	def questions(self, repeat: str | None):
		return [
			f
			for f in self.fields
			if f.get("kind", "question") == "question" and self.repeat_of.get(f["path"]) == repeat
		]

	def data(self, doc: dict) -> dict:
		data = {}
		for f in self.questions(None):
			data[f["path"]] = answer(f["type"], doc.get(f["fieldname"]))
		for r in self.repeats:
			table = self.by_path.get(r)
			if table is None:
				continue
			rows = []
			for row in doc.get(table["fieldname"]) or []:
				row = row if isinstance(row, dict) else row.as_dict()
				rows.append(
					{f["path"]: answer(f["type"], row.get(f["fieldname"])) for f in self.questions(r)}
				)
			data[r] = rows
		return data

	def context(
		self, data: dict, scope_repeat: str | None = None, row: int | None = None, self_path=None, **kw
	):
		return Context(
			data=data,
			repeat_of=self.repeat_of,
			repeats=self.repeats,
			scope_repeat=scope_repeat,
			row=row,
			self_path=self_path,
			choice_labels=self.choice_labels,
			**kw,
		)
