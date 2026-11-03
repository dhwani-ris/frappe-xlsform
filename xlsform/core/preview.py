"""Preview payload: the compiled form as ``frappe.ui.Dialog`` fields (REQUIREMENTS.md section 7).

The preview runs before the first publish, when no DocType exists yet, so it is built from
the compiler's plan. It keeps the real ``depends_on`` / ``mandatory_depends_on`` /
``read_only_depends_on`` strings, so the designer sees exactly the skip logic collectors will.
"""

PREVIEW_CHOICE_LIMIT = 1000
SKIP = {"xf_form", "xf_version", "xf_channel"}


def build(plan: dict) -> dict:
	by_name = {dt["name"]: dt for dt in plan["doctypes"]}
	choices = {
		dt: [{"value": r["choice_name"], "label": r["label"] or r["choice_name"]} for r in rows[:PREVIEW_CHOICE_LIMIT]]
		for dt, rows in plan["choices"].items()
	}
	truncated = sorted(dt for dt, rows in plan["choices"].items() if len(rows) > PREVIEW_CHOICE_LIMIT)
	parent = plan["doctypes"][-1]
	return {
		"title": plan["web_form"]["title"],
		"fields": [_field(f, by_name, choices) for f in parent["fields"] if _keep(f)],
		"truncated_lists": truncated,
	}


def _keep(f: dict) -> bool:
	return f["fieldname"] not in SKIP and not (f.get("hidden") and f["fieldtype"] not in ("Section Break", "Tab Break"))


def _field(f: dict, by_name: dict, choices: dict) -> dict:
	out = {
		k: f[k]
		for k in (
			"fieldname",
			"label",
			"fieldtype",
			"description",
			"depends_on",
			"mandatory_depends_on",
			"read_only_depends_on",
			"read_only",
			"reqd",
			"default",
			"options",
		)
		if f.get(k) not in (None, "")
	}
	ft = f["fieldtype"]
	if ft == "Tab Break":
		out["fieldtype"] = "Section Break"
	elif ft == "Link":
		out["fieldtype"] = "Autocomplete"
		out["options"] = choices.get(f["options"], [])
	elif ft in ("Attach", "Attach Image"):
		out["fieldtype"] = "Data"
		out["read_only"] = 1
		out["description"] = "(file upload in the real form)"
	elif ft == "Table MultiSelect":
		pick = by_name[f["options"]]
		target = pick["fields"][0]["options"]
		out["fieldtype"] = "Table"
		out["data"] = []
		out["fields"] = [
			{
				"fieldname": "choice",
				"label": "Choice",
				"fieldtype": "Autocomplete",
				"options": choices.get(target, []),
				"in_list_view": 1,
				"reqd": 1,
			}
		]
		out.pop("options", None)
	elif ft == "Table":
		child = by_name[f["options"]]
		out["data"] = []
		out["fields"] = [
			{**_field(cf, by_name, choices), "in_list_view": 1}
			for cf in child["fields"]
			if _keep(cf) and cf["fieldtype"] not in ("Section Break", "Tab Break", "Column Break", "HTML", "Table", "Table MultiSelect")
		]
		out.pop("options", None)
	return out
