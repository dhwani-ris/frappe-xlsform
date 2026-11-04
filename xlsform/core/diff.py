"""Stage 5: what changes for existing data when this version replaces the published one.

Warnings only (REQUIREMENTS.md sections 5 and 7). The same comparison is stored as the
version's ``change_summary`` and shown to the designer before publishing.
"""

from xlsform.core.compiler import fieldtype_for
from xlsform.core.form import QUESTION, REPEAT, SELECT_TYPES, SUPPORTED_TYPES, Form, Node
from xlsform.core.issues import Issue, issue
from xlsform.core.meaning import Analysis


def diff(form: Form, analysis: Analysis, prev_meta: dict | None) -> tuple[dict, list[Issue]]:
	summary = {"added": [], "removed": [], "renamed": [], "moved": [], "type_changed": []}
	if not prev_meta:
		summary["added"] = [n.name for n in form.questions() if n.base_type in SUPPORTED_TYPES]
		return summary, []
	issues: list[Issue] = []
	prev = {
		f["path"]: f
		for f in prev_meta.get("fields", [])
		if f.get("kind", "question") in (QUESTION, REPEAT) and not f.get("retired_in")
	}
	cur = {
		n.path: n
		for n in form.nodes()
		if (n.kind == QUESTION and n.base_type in SUPPORTED_TYPES) or n.kind == REPEAT
	}
	added = [p for p in cur if p not in prev]
	removed = [p for p in prev if p not in cur]

	def where(node: Node, column: str = "name") -> dict:
		return dict(sheet="survey", row=node.row_number, column=column, col_index=node.col(column))

	for r in list(removed):
		name = prev[r]["name"]
		match = next((a for a in added if cur[a].name == name), None)
		if match is None:
			continue
		node = cur[match]
		new_repeat = node.enclosing_repeat
		old_repeat = _repeat_name(r, prev_meta)
		direction = "into" if new_repeat is not None else "out of"
		repeat_name = new_repeat.name if new_repeat is not None else old_repeat
		issues.append(
			issue("W-MOVE-REPEAT", name=name, direction=direction, repeat=repeat_name, **where(node))
		)
		summary["moved"].append(name)
		removed.remove(r)
		added.remove(match)

	labels = prev_meta.get("labels", {})
	for r in list(removed):
		old_label = labels.get(r, {})
		for a in list(added):
			node = cur[a]
			if node.kind != QUESTION or not old_label:
				continue
			if fieldtype_for(node, analysis.ranges) != prev[r]["fieldtype"]:
				continue
			if node.localized("label", form.default_language) == old_label:
				issues.append(issue("W-RENAME", old=prev[r]["name"], new=node.name, **where(node)))
				summary["renamed"].append({"from": prev[r]["name"], "to": node.name})
				removed.remove(r)
				added.remove(a)
				break

	for r in removed:
		issues.append(issue("W-REMOVED", name=prev[r]["name"]))
		summary["removed"].append(prev[r]["name"])
	summary["added"] = [cur[a].name for a in added]

	for path, node in cur.items():
		old = prev.get(path)
		if old is None or node.kind != QUESTION:
			continue
		new_type = fieldtype_for(node, analysis.ranges)
		list_changed = node.base_type in SELECT_TYPES and old.get("list") != (
			node.type.file_name if node.base_type.endswith("_from_file") else node.type.list_name
		)
		if new_type != old["fieldtype"] or list_changed:
			issues.append(
				issue(
					"W-TYPE-CHANGE",
					name=node.name,
					old=old.get("type"),
					new=node.base_type,
					**where(node, "type"),
				)
			)
			summary["type_changed"].append({"name": node.name, "from": old.get("type"), "to": node.base_type})
	return summary, issues


def _repeat_name(path: str, prev_meta: dict) -> str:
	repeats = [p for p in prev_meta.get("doctypes", {}).get("repeats", {}) if path.startswith(p + "/")]
	return max(repeats, key=len).rsplit("/", 1)[-1] if repeats else ""
